#!/usr/bin/env python3
"""Shared library for Canon JSON operations.

Provides load/save/validate, _meta handling, dedup, and fetch helpers.
Stdlib only — no pip dependencies.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANON_DIR = Path(os.environ["BOID_CANON_DIR"]) if os.environ.get("BOID_CANON_DIR") else Path(__file__).resolve().parent.parent / "canon"


# ── JSON I/O ──────────────────────────────────────────────────────────

def load_canon(filename: str) -> dict[str, Any]:
    """Load a Canon JSON file and return the parsed dict."""
    path = CANON_DIR / filename
    with open(path) as f:
        return json.load(f)


def save_canon(filename: str, data: dict[str, Any]) -> Path:
    """Save a Canon JSON file with consistent formatting."""
    path = CANON_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def validate_canon(filename: str) -> list[str]:
    """Validate a Canon JSON file, return list of errors (empty = valid)."""
    errors: list[str] = []
    path = CANON_DIR / filename
    if not path.exists():
        return [f"File not found: {path}"]

    try:
        data = load_canon(filename)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    if "_meta" not in data:
        errors.append("Missing _meta field")
    else:
        meta = data["_meta"]
        for field in ("source", "version", "date", "description"):
            if field not in meta:
                errors.append(f"_meta missing '{field}'")

    return errors


# ── _meta helpers ─────────────────────────────────────────────────────

def make_meta(
    description: str,
    version: str = "0.2.0",
    source: str = "terraform-aws-boid Canon",
) -> dict[str, str]:
    """Create a _meta block with current date."""
    return {
        "source": source,
        "version": version,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "description": description,
    }


def update_meta(data: dict[str, Any], **overrides: str) -> dict[str, Any]:
    """Update _meta fields in place."""
    if "_meta" not in data:
        data["_meta"] = {}
    data["_meta"]["date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for k, v in overrides.items():
        data["_meta"][k] = v
    return data


# ── Deduplication ─────────────────────────────────────────────────────

def dedup_by_field(entries: list[dict], field: str) -> list[dict]:
    """Remove duplicate entries based on a specific field value."""
    seen: set[str] = set()
    result: list[dict] = []
    for entry in entries:
        key = entry.get(field, "")
        if key and key not in seen:
            seen.add(key)
            result.append(entry)
    return result


def entry_hash(entry: dict, fields: list[str]) -> str:
    """Create a stable hash of an entry based on specific fields."""
    parts = [str(entry.get(f, "")) for f in sorted(fields)]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


# ── Fetch helpers ─────────────────────────────────────────────────────

def fetch_url(url: str, timeout: int = 30) -> str:
    """Fetch a URL and return the response body as text."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "terraform-aws-boid/0.1 (Canon seeder)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        print(f"  WARN: Failed to fetch {url}: {e}", file=sys.stderr)
        return ""


def fetch_json(url: str, timeout: int = 30) -> Any:
    """Fetch a URL and parse the response as JSON."""
    body = fetch_url(url, timeout=timeout)
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        print(f"  WARN: Invalid JSON from {url}: {e}", file=sys.stderr)
        return None


# ── Validation helpers ────────────────────────────────────────────────

def validate_regex(pattern: str) -> bool:
    """Check if a string is a valid regex."""
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def count_entries(filename: str) -> dict[str, int]:
    """Count entries in each array in a Canon file."""
    data = load_canon(filename)
    counts: dict[str, int] = {}
    for key, value in data.items():
        if key != "_meta" and isinstance(value, list):
            counts[key] = len(value)
    return counts


# ── Search / Retrieval ────────────────────────────────────────────────

def match_error(error_text: str, signatures: list[dict]) -> list[dict]:
    """Find matching Canon signatures for a given error text."""
    matches = []
    for sig in signatures:
        pattern = sig.get("error_pattern", "")
        try:
            if re.search(pattern, error_text, re.IGNORECASE):
                matches.append(sig)
        except re.error:
            if pattern.lower() in error_text.lower():
                matches.append(sig)
    return matches


def search_by_resource(resource_type: str) -> list[dict]:
    """Search error-signatures, sg-interactions, and aws-limits for entries matching a resource type.

    Returns a list of dicts, each with 'source' (filename) and 'entry' (the matched entry).
    """
    results: list[dict] = []
    rt = resource_type.lower()

    # error-signatures: match on 'resource' field
    try:
        sigs = load_canon("error-signatures.json")
        for sig in sigs.get("signatures", []):
            if rt in sig.get("resource", "").lower():
                results.append({"source": "error-signatures.json", "entry": sig})
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # sg-interactions: match on 'terraform_resources' list
    try:
        sg = load_canon("sg-interactions.json")
        for pattern in sg.get("patterns", []):
            for res in pattern.get("terraform_resources", []):
                if rt in res.lower():
                    results.append({"source": "sg-interactions.json", "entry": pattern})
                    break
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # aws-limits: match on 'service' field (strip aws_ prefix for comparison)
    try:
        limits = load_canon("aws-limits.json")
        # aws_security_group → ec2, aws_s3_bucket → s3, etc.
        service_hint = rt.replace("aws_", "").split("_")[0]
        for limit in limits.get("limits", []):
            if service_hint == limit.get("service", "").lower():
                results.append({"source": "aws-limits.json", "entry": limit})
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return results


def search_by_tags(tags: list[str]) -> list[dict]:
    """Search all Canon files for entries matching any of the given tags.

    Returns a list of dicts, each with 'source' (filename) and 'entry' (the matched entry).
    """
    results: list[dict] = []
    tags_lower = {t.lower() for t in tags}

    # Files and their list keys + tag field name
    search_targets = [
        ("error-signatures.json", "signatures", "tags"),
        ("sg-interactions.json", "patterns", "tags"),
    ]

    for filename, list_key, tag_field in search_targets:
        try:
            data = load_canon(filename)
            for entry in data.get(list_key, []):
                entry_tags = {t.lower() for t in entry.get(tag_field, [])}
                if tags_lower & entry_tags:
                    results.append({"source": filename, "entry": entry})
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    return results


# ── Reporting ─────────────────────────────────────────────────────────

def report_canon_status() -> None:
    """Print a summary of all Canon files."""
    files = sorted(CANON_DIR.glob("*.json"))
    print("Canon Status Report")
    print("=" * 50)
    for path in files:
        name = path.name
        errors = validate_canon(name)
        if errors:
            print(f"  ✗ {name}: {', '.join(errors)}")
        else:
            counts = count_entries(name)
            parts = [f"{k}={v}" for k, v in counts.items()]
            print(f"  ✓ {name}: {', '.join(parts) if parts else 'empty'}")
    print("=" * 50)


if __name__ == "__main__":
    report_canon_status()
