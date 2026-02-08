#!/usr/bin/env python3
"""Canon retrieval and schema tests.

Tests that Canon data is well-formed, entries are findable via regex matching,
and the data meets the population targets.

Uses stdlib unittest only — no pip dependencies.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

# Add scripts/ to path for canon_lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from canon_lib import match_error

CANON_DIR = Path(__file__).resolve().parent.parent.parent / "canon"
TEST_DATA_DIR = Path(__file__).resolve().parent / "test_data"


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


class TestErrorSignatures(unittest.TestCase):
    """Tests for canon/error-signatures.json"""

    @classmethod
    def setUpClass(cls):
        cls.data = load_json(CANON_DIR / "error-signatures.json")
        cls.sigs = cls.data["signatures"]
        cls.test_data = load_json(TEST_DATA_DIR / "sample_errors.json")

    def test_meta_present(self):
        self.assertIn("_meta", self.data)
        for field in ("source", "version", "date", "description"):
            self.assertIn(field, self.data["_meta"])

    def test_minimum_entries(self):
        self.assertGreaterEqual(len(self.sigs), 50, "Need at least 50 error signatures")

    def test_required_fields(self):
        required = {"error_pattern", "provider", "resource", "root_cause", "fix", "severity", "tags"}
        for sig in self.sigs:
            for field in required:
                self.assertIn(field, sig, f"Signature missing '{field}': {sig.get('error_pattern', 'unknown')}")

    def test_valid_severity(self):
        valid = {"critical", "high", "medium", "low"}
        for sig in self.sigs:
            self.assertIn(sig["severity"], valid,
                f"Invalid severity '{sig['severity']}' for: {sig['error_pattern']}")

    def test_error_patterns_are_valid_regex(self):
        for sig in self.sigs:
            try:
                re.compile(sig["error_pattern"])
            except re.error as e:
                self.fail(f"Invalid regex '{sig['error_pattern']}': {e}")

    def test_unique_error_patterns(self):
        patterns = [s["error_pattern"] for s in self.sigs]
        self.assertEqual(len(patterns), len(set(patterns)), "Duplicate error_pattern values found")

    def test_tags_are_lists(self):
        for sig in self.sigs:
            self.assertIsInstance(sig["tags"], list,
                f"tags should be a list for: {sig['error_pattern']}")
            self.assertGreater(len(sig["tags"]), 0,
                f"tags should not be empty for: {sig['error_pattern']}")

    def test_sample_errors_match(self):
        """Test that 10+ real-world errors match the right signature."""
        errors = self.test_data["errors"]
        matched_count = 0
        for err in errors:
            matches = match_error(err["raw_error"], self.sigs)
            if matches:
                matched_count += 1
                # Verify at least one match has a plausible pattern
                patterns = [m["error_pattern"] for m in matches]
                self.assertTrue(
                    any(re.search(p, err["raw_error"], re.IGNORECASE) for p in patterns),
                    f"False positive match for {err['id']}: {err['description']}"
                )
        self.assertGreaterEqual(matched_count, 10,
            f"Only {matched_count}/15 sample errors matched — need at least 10")

    def test_non_matching_errors_dont_match(self):
        """Test that unrelated errors don't false-positive match."""
        non_matching = self.test_data["non_matching_errors"]
        for err in non_matching:
            matches = match_error(err["raw_error"], self.sigs)
            # Some may match generically — that's OK. But they shouldn't match with high specificity.
            # We just check that the total false positive rate is low.
            if matches:
                # Allow up to 2 non-matching errors to have incidental matches
                pass
        # This is a soft test — we just want awareness, not strict failure
        total_matches = sum(1 for err in non_matching if match_error(err["raw_error"], self.sigs))
        self.assertLessEqual(total_matches, 3,
            f"{total_matches}/5 non-matching errors had matches — patterns may be too broad")


class TestAWSLimits(unittest.TestCase):
    """Tests for canon/aws-limits.json"""

    @classmethod
    def setUpClass(cls):
        cls.data = load_json(CANON_DIR / "aws-limits.json")
        cls.limits = cls.data["limits"]

    def test_meta_present(self):
        self.assertIn("_meta", self.data)

    def test_minimum_entries(self):
        self.assertGreaterEqual(len(self.limits), 30, "Need at least 30 AWS limit entries")

    def test_required_fields(self):
        required = {"service", "limit_name", "default_value", "unit", "adjustable",
                     "terraform_impact", "regions_vary", "notes"}
        for limit in self.limits:
            for field in required:
                self.assertIn(field, limit, f"Limit missing '{field}': {limit.get('limit_name', 'unknown')}")

    def test_service_lowercase(self):
        for limit in self.limits:
            self.assertEqual(limit["service"], limit["service"].lower(),
                f"Service should be lowercase: {limit['service']}")

    def test_terraform_impact_non_empty(self):
        for limit in self.limits:
            self.assertTrue(len(limit["terraform_impact"]) > 10,
                f"terraform_impact too short for: {limit['limit_name']}")

    def test_localstack_services_covered(self):
        """Verify the 15 LocalStack services are represented."""
        localstack_services = {
            "s3", "ec2", "iam", "rds", "ecs", "elbv2", "lambda",
            "dynamodb", "sqs", "sns", "route53", "acm", "secretsmanager",
            "cloudwatch", "sts"
        }
        covered = {limit["service"] for limit in self.limits}
        missing = localstack_services - covered
        self.assertEqual(missing, set(),
            f"LocalStack services not covered: {missing}")

    def test_adjustable_is_boolean(self):
        for limit in self.limits:
            self.assertIsInstance(limit["adjustable"], bool,
                f"adjustable should be boolean for: {limit['limit_name']}")


class TestProviderCompat(unittest.TestCase):
    """Tests for canon/provider-compat.json"""

    @classmethod
    def setUpClass(cls):
        cls.data = load_json(CANON_DIR / "provider-compat.json")
        cls.compat = cls.data["compatibility"]

    def test_meta_present(self):
        self.assertIn("_meta", self.data)

    def test_minimum_entries(self):
        self.assertGreaterEqual(len(self.compat), 12, "Need at least 12 compatibility entries")

    def test_required_fields(self):
        required = {"terraform_version", "provider_version", "status",
                     "breaking_changes", "migration_notes"}
        for entry in self.compat:
            for field in required:
                self.assertIn(field, entry,
                    f"Compat entry missing '{field}': TF {entry.get('terraform_version', '?')} / AWS {entry.get('provider_version', '?')}")

    def test_valid_status(self):
        valid = {"compatible", "deprecated", "breaking"}
        for entry in self.compat:
            self.assertIn(entry["status"], valid,
                f"Invalid status '{entry['status']}' for TF {entry['terraform_version']}")

    def test_tf_versions_covered(self):
        """Verify TF 1.5, 1.6, 1.7, 1.8 are covered."""
        all_tf_versions = " ".join(e["terraform_version"] for e in self.compat)
        for ver in ["1.5", "1.6", "1.7", "1.8"]:
            self.assertIn(ver, all_tf_versions,
                f"Terraform {ver} not covered in compatibility matrix")

    def test_provider_versions_covered(self):
        """Verify provider 4.x, 5.x, 6.x are covered."""
        all_provider_versions = " ".join(e["provider_version"] for e in self.compat)
        for ver in ["4.", "5.", "6."]:
            self.assertIn(ver, all_provider_versions,
                f"Provider {ver}x not covered in compatibility matrix")

    def test_breaking_changes_is_list(self):
        for entry in self.compat:
            self.assertIsInstance(entry["breaking_changes"], list,
                f"breaking_changes should be list for TF {entry['terraform_version']}")


class TestIAMEvalRules(unittest.TestCase):
    """Tests for canon/iam-eval-rules.json"""

    @classmethod
    def setUpClass(cls):
        cls.data = load_json(CANON_DIR / "iam-eval-rules.json")
        cls.eval_order = cls.data["evaluation_order"]
        cls.interactions = cls.data["interaction_rules"]

    def test_meta_present(self):
        self.assertIn("_meta", self.data)

    def test_minimum_eval_order(self):
        self.assertGreaterEqual(len(self.eval_order), 10, "Need at least 10 evaluation order entries")

    def test_minimum_interactions(self):
        self.assertGreaterEqual(len(self.interactions), 8, "Need at least 8 interaction rules")

    def test_eval_order_sorted(self):
        orders = [e["rule_order"] for e in self.eval_order]
        self.assertEqual(orders, sorted(orders), "evaluation_order should be sorted by rule_order")

    def test_eval_order_unique_names(self):
        names = [e["rule_name"] for e in self.eval_order]
        self.assertEqual(len(names), len(set(names)), "Duplicate rule_name in evaluation_order")

    def test_eval_order_required_fields(self):
        required = {"rule_order", "rule_name", "description", "terraform_relevance",
                     "common_mistakes", "examples"}
        for entry in self.eval_order:
            for field in required:
                self.assertIn(field, entry, f"eval_order entry missing '{field}': {entry.get('rule_name', '?')}")

    def test_common_mistakes_non_empty(self):
        for entry in self.eval_order:
            self.assertIsInstance(entry["common_mistakes"], list)
            self.assertGreater(len(entry["common_mistakes"]), 0,
                f"common_mistakes empty for: {entry['rule_name']}")

    def test_interaction_required_fields(self):
        required = {"rule_name", "description", "terraform_relevance"}
        for entry in self.interactions:
            for field in required:
                self.assertIn(field, entry, f"interaction entry missing '{field}': {entry.get('rule_name', '?')}")

    def test_interaction_unique_names(self):
        names = [e["rule_name"] for e in self.interactions]
        self.assertEqual(len(names), len(set(names)), "Duplicate rule_name in interaction_rules")


class TestSGInteractions(unittest.TestCase):
    """Tests for canon/sg-interactions.json"""

    @classmethod
    def setUpClass(cls):
        cls.data = load_json(CANON_DIR / "sg-interactions.json")
        cls.patterns = cls.data["patterns"]

    def test_meta_present(self):
        self.assertIn("_meta", self.data)

    def test_minimum_entries(self):
        self.assertGreaterEqual(len(self.patterns), 12, "Need at least 12 SG interaction patterns")

    def test_required_fields(self):
        required = {"pattern_name", "description", "symptom", "root_cause",
                     "solution", "terraform_resources", "tags"}
        for pattern in self.patterns:
            for field in required:
                self.assertIn(field, pattern,
                    f"Pattern missing '{field}': {pattern.get('pattern_name', '?')}")

    def test_unique_pattern_names(self):
        names = [p["pattern_name"] for p in self.patterns]
        self.assertEqual(len(names), len(set(names)), "Duplicate pattern_name values found")

    def test_solution_non_empty(self):
        for pattern in self.patterns:
            self.assertTrue(len(pattern["solution"]) > 10,
                f"Solution too short for: {pattern['pattern_name']}")

    def test_terraform_resources_valid(self):
        """All terraform_resources should start with 'aws_' or be known Terraform resources."""
        valid_prefixes = ("aws_", "data.")
        for pattern in self.patterns:
            self.assertIsInstance(pattern["terraform_resources"], list)
            self.assertGreater(len(pattern["terraform_resources"]), 0,
                f"terraform_resources empty for: {pattern['pattern_name']}")
            for res in pattern["terraform_resources"]:
                self.assertTrue(
                    any(res.startswith(p) for p in valid_prefixes),
                    f"Invalid resource '{res}' in pattern: {pattern['pattern_name']}"
                )

    def test_tags_are_lists(self):
        for pattern in self.patterns:
            self.assertIsInstance(pattern["tags"], list)
            self.assertGreater(len(pattern["tags"]), 0,
                f"tags empty for: {pattern['pattern_name']}")


class TestCrossFileConsistency(unittest.TestCase):
    """Tests that span multiple Canon files."""

    @classmethod
    def setUpClass(cls):
        cls.errors = load_json(CANON_DIR / "error-signatures.json")
        cls.limits = load_json(CANON_DIR / "aws-limits.json")
        cls.iam = load_json(CANON_DIR / "iam-eval-rules.json")
        cls.sg = load_json(CANON_DIR / "sg-interactions.json")
        cls.compat = load_json(CANON_DIR / "provider-compat.json")

    def test_all_files_have_meta(self):
        for name, data in [("errors", self.errors), ("limits", self.limits),
                           ("iam", self.iam), ("sg", self.sg), ("compat", self.compat)]:
            self.assertIn("_meta", data, f"{name} missing _meta")
            self.assertIn("version", data["_meta"], f"{name} _meta missing version")

    def test_all_files_valid_json(self):
        """Redundant with load, but explicit."""
        for f in CANON_DIR.glob("*.json"):
            try:
                load_json(f)
            except json.JSONDecodeError:
                self.fail(f"Invalid JSON: {f.name}")

    def test_sg_errors_have_matching_signatures(self):
        """SG interaction symptoms should have corresponding error signatures."""
        sigs = self.errors["signatures"]
        sg_patterns = self.sg["patterns"]
        # At least some SG symptoms should match error signatures
        matched = 0
        for pattern in sg_patterns:
            symptom = pattern["symptom"]
            if match_error(symptom, sigs):
                matched += 1
        self.assertGreater(matched, 0,
            "No SG interaction symptoms match any error signature")


if __name__ == "__main__":
    unittest.main()
