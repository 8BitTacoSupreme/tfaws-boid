#!/usr/bin/env python3
"""Terraform plan JSON analyzer — cross-references plan output against Canon.

Reads `terraform show -json <planfile>` output from stdin or a file argument.
Parses resource_changes and diagnostics, cross-references Canon knowledge,
and outputs structured findings.

Usage:
    terraform show -json tfplan | python3 tf_plan_analyzer.py
    python3 tf_plan_analyzer.py plan.json
    python3 tf_plan_analyzer.py plan.json --format text
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canon_lib import load_canon, match_error, search_by_resource


def parse_plan(plan_data: dict[str, Any]) -> dict[str, Any]:
    """Extract structured summary from terraform plan JSON."""
    resource_changes = plan_data.get("resource_changes", [])
    diagnostics = plan_data.get("diagnostics", [])

    actions: dict[str, list[str]] = {
        "create": [],
        "update": [],
        "delete": [],
        "no-op": [],
        "read": [],
    }

    resource_types: set[str] = set()

    for rc in resource_changes:
        rtype = rc.get("type", "unknown")
        address = rc.get("address", "unknown")
        resource_types.add(rtype)

        change = rc.get("change", {})
        rc_actions = change.get("actions", [])

        for action in rc_actions:
            if action in actions:
                actions[action].append(address)

    return {
        "total_changes": len(resource_changes),
        "actions": {k: v for k, v in actions.items() if v},
        "resource_types": sorted(resource_types),
        "diagnostics_count": len(diagnostics),
        "terraform_version": plan_data.get("terraform_version", "unknown"),
    }


def find_canon_matches(plan_data: dict[str, Any]) -> dict[str, Any]:
    """Cross-reference plan contents against Canon knowledge."""
    resource_changes = plan_data.get("resource_changes", [])
    diagnostics = plan_data.get("diagnostics", [])

    # Collect unique resource types
    resource_types: set[str] = set()
    for rc in resource_changes:
        resource_types.add(rc.get("type", ""))

    # Search Canon by resource type
    canon_findings: list[dict] = []
    seen_entries: set[str] = set()
    for rtype in sorted(resource_types):
        if not rtype:
            continue
        results = search_by_resource(rtype)
        for r in results:
            key = json.dumps(r["entry"], sort_keys=True)
            if key not in seen_entries:
                seen_entries.add(key)
                canon_findings.append({
                    "triggered_by": rtype,
                    "source": r["source"],
                    "entry": r["entry"],
                })

    # Match diagnostics against error signatures
    diagnostic_matches: list[dict] = []
    try:
        sigs_data = load_canon("error-signatures.json")
        sigs = sigs_data.get("signatures", [])
    except (FileNotFoundError, json.JSONDecodeError):
        sigs = []

    for diag in diagnostics:
        error_text = f"{diag.get('summary', '')} {diag.get('detail', '')}"
        matches = match_error(error_text, sigs)
        if matches:
            diagnostic_matches.append({
                "diagnostic": {
                    "severity": diag.get("severity", "unknown"),
                    "summary": diag.get("summary", ""),
                    "address": diag.get("address", ""),
                },
                "canon_matches": matches,
            })

    return {
        "canon_findings": canon_findings,
        "diagnostic_matches": diagnostic_matches,
    }


def check_provider_compat(plan_data: dict[str, Any]) -> list[dict]:
    """Check provider versions in the plan against provider-compat.json."""
    warnings: list[dict] = []

    try:
        compat_data = load_canon("provider-compat.json")
        compat_entries = compat_data.get("compatibility", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return warnings

    tf_version = plan_data.get("terraform_version", "")
    if not tf_version:
        return warnings

    # Extract provider versions from configuration
    config = plan_data.get("configuration", {})
    provider_config = config.get("provider_config", {})

    for provider_key, pconfig in provider_config.items():
        if "aws" not in provider_key.lower():
            continue
        # Provider version might be in version_constraint
        version_constraint = pconfig.get("version_constraint", "")
        if not version_constraint:
            continue

        # Check against compat entries for breaking combinations
        for entry in compat_entries:
            if entry.get("status") == "breaking":
                # Check if TF version matches
                tf_range = entry.get("terraform_version", "")
                if _version_in_range(tf_version, tf_range):
                    warnings.append({
                        "terraform_version": tf_version,
                        "provider_constraint": version_constraint,
                        "compat_entry": entry,
                    })

    return warnings


def check_limit_warnings(plan_data: dict[str, Any]) -> list[dict]:
    """Check if resource creates might hit known AWS limits."""
    warnings: list[dict] = []

    try:
        limits_data = load_canon("aws-limits.json")
        limits = limits_data.get("limits", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return warnings

    resource_changes = plan_data.get("resource_changes", [])

    # Count creates per resource type
    create_counts: dict[str, int] = {}
    for rc in resource_changes:
        change = rc.get("change", {})
        if "create" in change.get("actions", []):
            rtype = rc.get("type", "")
            create_counts[rtype] = create_counts.get(rtype, 0) + 1

    # Map resource types to services
    service_map = {
        "aws_vpc": "ec2",
        "aws_subnet": "ec2",
        "aws_security_group": "ec2",
        "aws_instance": "ec2",
        "aws_eip": "ec2",
        "aws_s3_bucket": "s3",
        "aws_iam_role": "iam",
        "aws_iam_policy": "iam",
        "aws_iam_user": "iam",
        "aws_db_instance": "rds",
        "aws_rds_cluster": "rds",
        "aws_ecs_cluster": "ecs",
        "aws_ecs_service": "ecs",
        "aws_ecs_task_definition": "ecs",
        "aws_lambda_function": "lambda",
        "aws_dynamodb_table": "dynamodb",
        "aws_sqs_queue": "sqs",
        "aws_sns_topic": "sns",
        "aws_lb": "elbv2",
        "aws_alb": "elbv2",
    }

    services_creating: set[str] = set()
    for rtype in create_counts:
        service = service_map.get(rtype)
        if service:
            services_creating.add(service)

    for limit in limits:
        if limit.get("service", "") in services_creating:
            warnings.append({
                "service": limit["service"],
                "limit": limit["limit_name"],
                "default_value": limit["default_value"],
                "terraform_impact": limit["terraform_impact"],
            })

    return warnings


def _version_in_range(version: str, range_str: str) -> bool:
    """Simple check if a version string falls within a constraint range.

    Handles ranges like ">=1.5.0, <1.6.0". Not a full semver solver —
    just enough for our compat matrix.
    """
    parts = [p.strip() for p in range_str.split(",")]
    for part in parts:
        match = re.match(r"([><=!]+)\s*([\d.]+)", part)
        if not match:
            continue
        op, target = match.group(1), match.group(2)
        cmp = _compare_versions(version, target)
        if op == ">=" and cmp < 0:
            return False
        if op == ">" and cmp <= 0:
            return False
        if op == "<" and cmp >= 0:
            return False
        if op == "<=" and cmp > 0:
            return False
        if op == "=" and cmp != 0:
            return False
    return True


def _compare_versions(a: str, b: str) -> int:
    """Compare two dotted version strings. Returns -1, 0, or 1."""
    def parts(v: str) -> list[int]:
        return [int(x) for x in v.split(".") if x.isdigit()]
    pa, pb = parts(a), parts(b)
    for i in range(max(len(pa), len(pb))):
        va = pa[i] if i < len(pa) else 0
        vb = pb[i] if i < len(pb) else 0
        if va < vb:
            return -1
        if va > vb:
            return 1
    return 0


def analyze(plan_data: dict[str, Any]) -> dict[str, Any]:
    """Run full analysis on a terraform plan JSON."""
    return {
        "plan_summary": parse_plan(plan_data),
        **find_canon_matches(plan_data),
        "compat_warnings": check_provider_compat(plan_data),
        "limit_warnings": check_limit_warnings(plan_data),
    }


def format_text(result: dict[str, Any]) -> str:
    """Format analysis result as human-readable text."""
    lines: list[str] = []
    summary = result.get("plan_summary", {})

    lines.append("=== Terraform Plan Analysis ===")
    lines.append(f"Terraform version: {summary.get('terraform_version', 'unknown')}")
    lines.append(f"Total resource changes: {summary.get('total_changes', 0)}")

    for action, resources in summary.get("actions", {}).items():
        lines.append(f"  {action}: {len(resources)} ({', '.join(resources[:5])}{'...' if len(resources) > 5 else ''})")

    canon = result.get("canon_findings", [])
    if canon:
        lines.append(f"\n=== Canon Findings ({len(canon)}) ===")
        for f in canon:
            entry = f["entry"]
            name = entry.get("error_pattern") or entry.get("pattern_name") or entry.get("limit_name", "?")
            lines.append(f"  [{f['source']}] {name}")
            if "root_cause" in entry:
                lines.append(f"    Root cause: {entry['root_cause'][:120]}...")
            if "fix" in entry:
                lines.append(f"    Fix: {entry['fix'][:120]}...")
            if "solution" in entry:
                lines.append(f"    Solution: {entry['solution'][:120]}...")

    diag = result.get("diagnostic_matches", [])
    if diag:
        lines.append(f"\n=== Diagnostic Matches ({len(diag)}) ===")
        for d in diag:
            lines.append(f"  [{d['diagnostic']['severity']}] {d['diagnostic']['summary']}")
            for m in d["canon_matches"]:
                lines.append(f"    Canon match: {m.get('error_pattern', '?')}")
                lines.append(f"    Fix: {m.get('fix', '?')[:120]}...")

    compat = result.get("compat_warnings", [])
    if compat:
        lines.append(f"\n=== Compatibility Warnings ({len(compat)}) ===")
        for w in compat:
            lines.append(f"  TF {w['terraform_version']} + provider {w['provider_constraint']}: BREAKING")

    limits = result.get("limit_warnings", [])
    if limits:
        lines.append(f"\n=== Limit Warnings ({len(limits)}) ===")
        for w in limits:
            lines.append(f"  [{w['service']}] {w['limit']}: default {w['default_value']}")
            lines.append(f"    Impact: {w['terraform_impact'][:120]}...")

    if not any([canon, diag, compat, limits]):
        lines.append("\nNo Canon findings for this plan.")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze terraform plan JSON against Canon knowledge",
    )
    parser.add_argument(
        "plan_file", nargs="?", default="-",
        help="Path to plan JSON file (default: stdin)",
    )
    parser.add_argument(
        "--format", choices=["json", "text"], default="json",
        help="Output format (default: json)",
    )

    args = parser.parse_args()

    if args.plan_file == "-":
        plan_data = json.load(sys.stdin)
    else:
        with open(args.plan_file) as f:
            plan_data = json.load(f)

    result = analyze(plan_data)

    if args.format == "text":
        print(format_text(result))
    else:
        json.dump(result, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
