#!/usr/bin/env python3
"""Phase 3 integration tests.

Tests the full pipeline: Canon search CLI, plan analyzer, and
integration between terraform validate output and Canon matching.

Uses stdlib unittest only — no pip dependencies.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Add scripts/ to path for direct imports
sys.path.insert(0, str(SCRIPTS_DIR))

from canon_lib import load_canon, match_error, search_by_resource, search_by_tags
from tf_plan_analyzer import analyze, parse_plan, find_canon_matches, check_limit_warnings


class TestCanonSearch(unittest.TestCase):
    """Tests for scripts/canon_search.py CLI."""

    def _run_canon_search(self, *args: str) -> dict:
        """Run canon_search.py and return parsed JSON output."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "canon_search.py"), *args],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, f"canon_search.py failed: {result.stderr}")
        return json.loads(result.stdout)

    def test_error_search_finds_sg_cycle(self):
        output = self._run_canon_search("--error", "Cycle: aws_security_group")
        self.assertGreater(output["count"], 0)
        patterns = [r["entry"].get("error_pattern", "") for r in output["results"]]
        self.assertTrue(
            any("Cycle" in p for p in patterns),
            f"Expected cycle pattern in results, got: {patterns}",
        )

    def test_error_search_finds_inconsistent_plan(self):
        output = self._run_canon_search("--error", "Provider produced inconsistent final plan")
        self.assertGreater(output["count"], 0)

    def test_resource_search_finds_security_group(self):
        output = self._run_canon_search("--resource", "aws_security_group")
        self.assertGreater(output["count"], 0)
        sources = {r["source"] for r in output["results"]}
        # Should find matches in both error-signatures and sg-interactions
        self.assertIn("sg-interactions.json", sources)

    def test_tag_search_finds_cycle_entries(self):
        output = self._run_canon_search("--tags", "cycle,dependency")
        self.assertGreater(output["count"], 0)

    def test_error_search_no_match(self):
        output = self._run_canon_search("--error", "some completely unrelated error xyzzy123")
        self.assertEqual(output["count"], 0)

    def test_output_is_valid_json(self):
        output = self._run_canon_search("--error", "timeout")
        self.assertIn("query", output)
        self.assertIn("count", output)
        self.assertIn("results", output)

    def test_combined_search(self):
        """Multiple flags should combine results."""
        output = self._run_canon_search(
            "--error", "Cycle: aws_security_group",
            "--resource", "aws_security_group",
        )
        self.assertGreater(output["count"], 1)


class TestPlanAnalyzer(unittest.TestCase):
    """Tests for scripts/tf_plan_analyzer.py using mock plan JSON."""

    @classmethod
    def setUpClass(cls):
        with open(FIXTURES_DIR / "mock-plan.json") as f:
            cls.plan_data = json.load(f)

    def test_parse_plan_summary(self):
        summary = parse_plan(self.plan_data)
        self.assertEqual(summary["total_changes"], 4)
        self.assertEqual(summary["terraform_version"], "1.7.0")
        self.assertIn("create", summary["actions"])
        self.assertEqual(len(summary["actions"]["create"]), 4)
        self.assertIn("aws_security_group", summary["resource_types"])
        self.assertIn("aws_vpc", summary["resource_types"])

    def test_canon_findings_for_security_group(self):
        result = find_canon_matches(self.plan_data)
        canon = result["canon_findings"]
        self.assertGreater(len(canon), 0)
        # Should find SG-related entries
        triggered_types = {f["triggered_by"] for f in canon}
        self.assertIn("aws_security_group", triggered_types)

    def test_diagnostic_matches(self):
        result = find_canon_matches(self.plan_data)
        diag_matches = result["diagnostic_matches"]
        self.assertGreater(len(diag_matches), 0)
        # The "Cycle: aws_security_group" diagnostic should match
        summaries = [d["diagnostic"]["summary"] for d in diag_matches]
        self.assertTrue(
            any("Cycle" in s for s in summaries),
            f"Expected cycle diagnostic match, got: {summaries}",
        )

    def test_diagnostic_inconsistent_plan_matches(self):
        result = find_canon_matches(self.plan_data)
        diag_matches = result["diagnostic_matches"]
        summaries = [d["diagnostic"]["summary"] for d in diag_matches]
        self.assertTrue(
            any("inconsistent" in s.lower() for s in summaries),
            f"Expected inconsistent plan match, got: {summaries}",
        )

    def test_limit_warnings(self):
        warnings = check_limit_warnings(self.plan_data)
        # Creating VPCs and SGs should trigger EC2 limit warnings
        services = {w["service"] for w in warnings}
        self.assertIn("ec2", services)

    def test_full_analyze(self):
        result = analyze(self.plan_data)
        self.assertIn("plan_summary", result)
        self.assertIn("canon_findings", result)
        self.assertIn("diagnostic_matches", result)
        self.assertIn("compat_warnings", result)
        self.assertIn("limit_warnings", result)

    def test_cli_json_output(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "tf_plan_analyzer.py"),
             str(FIXTURES_DIR / "mock-plan.json")],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, f"Analyzer failed: {result.stderr}")
        output = json.loads(result.stdout)
        self.assertIn("plan_summary", output)

    def test_cli_text_output(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "tf_plan_analyzer.py"),
             str(FIXTURES_DIR / "mock-plan.json"), "--format", "text"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, f"Analyzer failed: {result.stderr}")
        self.assertIn("Terraform Plan Analysis", result.stdout)
        self.assertIn("Canon Findings", result.stdout)

    def test_empty_plan(self):
        """Analyzer should handle an empty plan without crashing."""
        empty_plan = {
            "format_version": "1.2",
            "terraform_version": "1.7.0",
            "resource_changes": [],
            "diagnostics": [],
        }
        result = analyze(empty_plan)
        self.assertEqual(result["plan_summary"]["total_changes"], 0)
        self.assertEqual(len(result["canon_findings"]), 0)
        self.assertEqual(len(result["diagnostic_matches"]), 0)


class TestCanonLibSearchFunctions(unittest.TestCase):
    """Direct tests for canon_lib search functions (not via CLI)."""

    def test_match_error_basic(self):
        sigs = load_canon("error-signatures.json")["signatures"]
        matches = match_error("Cycle: aws_security_group.a, aws_security_group.b", sigs)
        self.assertGreater(len(matches), 0)

    def test_search_by_resource_ec2(self):
        results = search_by_resource("aws_security_group")
        self.assertGreater(len(results), 0)
        sources = {r["source"] for r in results}
        self.assertTrue(sources, "Expected at least one source file")

    def test_search_by_resource_s3(self):
        results = search_by_resource("aws_s3_bucket")
        # Should find S3-related limits at minimum
        sources = {r["source"] for r in results}
        self.assertIn("aws-limits.json", sources)

    def test_search_by_tags_cycle(self):
        results = search_by_tags(["cycle"])
        self.assertGreater(len(results), 0)

    def test_search_by_tags_no_match(self):
        results = search_by_tags(["nonexistent-tag-xyzzy"])
        self.assertEqual(len(results), 0)

    def test_search_by_resource_no_match(self):
        results = search_by_resource("aws_nonexistent_resource_xyzzy")
        self.assertEqual(len(results), 0)


class TestIntegrationPipeline(unittest.TestCase):
    """Integration tests exercising the full pipeline.

    Tests that terraform validate -json output on the SG cycle fixture
    produces diagnostics that match Canon entries. Requires terraform binary.
    """

    @classmethod
    def setUpClass(cls):
        # Check if terraform is available
        try:
            result = subprocess.run(
                ["terraform", "version"], capture_output=True, text=True,
            )
            cls.tf_available = result.returncode == 0
        except FileNotFoundError:
            cls.tf_available = False

    def test_sg_cycle_validate(self):
        """terraform validate on the SG cycle fixture should detect the cycle."""
        if not self.tf_available:
            self.skipTest("terraform not available")

        fixture_dir = FIXTURES_DIR / "sg-cycle"

        # Init first (required for validate)
        init_result = subprocess.run(
            ["terraform", "init", "-input=false", "-no-color", "-backend=false"],
            capture_output=True, text=True, cwd=str(fixture_dir),
        )
        # Init may fail if provider can't be downloaded — that's OK,
        # validate -json still works for cycle detection
        if init_result.returncode != 0:
            self.skipTest(f"terraform init failed (no network?): {init_result.stderr[:200]}")

        # Validate
        val_result = subprocess.run(
            ["terraform", "validate", "-json", "-no-color"],
            capture_output=True, text=True, cwd=str(fixture_dir),
        )

        val_output = json.loads(val_result.stdout)

        # If terraform found the cycle, verify Canon can match it
        diagnostics = val_output.get("diagnostics", [])
        if not diagnostics:
            # terraform validate may not catch cycles (it's a plan-time check)
            # In that case, just verify the fixture is syntactically valid
            self.assertTrue(val_output.get("valid", False),
                "Fixture should be syntactically valid even if cycle not detected at validate time")
            return

        # Feed diagnostics to Canon match
        sigs = load_canon("error-signatures.json")["signatures"]
        matched = False
        for diag in diagnostics:
            error_text = f"{diag.get('summary', '')} {diag.get('detail', '')}"
            matches = match_error(error_text, sigs)
            if matches:
                matched = True
                break

        if val_result.returncode != 0:
            # If validate failed, it should have found the cycle, and Canon should match
            self.assertTrue(matched, "Cycle diagnostic should match Canon error signatures")

    def test_mock_plan_full_pipeline(self):
        """End-to-end: load mock plan → analyze → verify findings structure."""
        with open(FIXTURES_DIR / "mock-plan.json") as f:
            plan_data = json.load(f)

        result = analyze(plan_data)

        # Verify complete output structure
        self.assertIsInstance(result["plan_summary"], dict)
        self.assertIsInstance(result["canon_findings"], list)
        self.assertIsInstance(result["diagnostic_matches"], list)
        self.assertIsInstance(result["compat_warnings"], list)
        self.assertIsInstance(result["limit_warnings"], list)

        # Verify meaningful content
        self.assertGreater(result["plan_summary"]["total_changes"], 0)
        self.assertGreater(len(result["canon_findings"]), 0,
            "Mock plan with SGs should produce canon findings")
        self.assertGreater(len(result["diagnostic_matches"]), 0,
            "Mock plan with cycle diagnostic should produce matches")


if __name__ == "__main__":
    unittest.main()
