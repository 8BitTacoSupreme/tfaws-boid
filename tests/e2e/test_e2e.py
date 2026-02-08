#!/usr/bin/env python3
"""End-to-end scenario tests for terraform-aws-boid.

Validates the full pipeline: demo fixtures → plan analyzer → Canon matches,
multi-session convention lifecycle, and fork-memory.sh script.

Uses stdlib unittest only — no pip dependencies. No LocalStack dependency.
All tests use mock plan JSON fixtures and in-memory SQLite.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
VPC_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vpc"
ECS_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ecs"

sys.path.insert(0, str(SCRIPTS_DIR))

from canon_lib import load_canon, match_error, search_by_resource
from tf_plan_analyzer import analyze, parse_plan, find_canon_matches, check_limit_warnings
from memory_lib import (
    connect, init_schema, record_convention, reinforce_convention,
    lookup_conventions, effective_confidence, _should_override_convention,
    record_fix, record_quirk, export_for_fork,
)


class TestVPCScenario(unittest.TestCase):
    """Scenario 1: VPC + Subnets + NAT — Canon-powered analysis."""

    @classmethod
    def setUpClass(cls):
        with open(VPC_FIXTURES / "plan.json") as f:
            cls.plan_data = json.load(f)
        cls.analysis = analyze(cls.plan_data)

    def test_plan_summary_resource_count(self):
        """Plan should contain 16 resources (1 VPC + 1 IGW + 6 subnets + 3 EIPs + 3 NATs + 2 SGs)."""
        summary = self.analysis["plan_summary"]
        self.assertEqual(summary["total_changes"], 16)

    def test_plan_summary_resource_types(self):
        """Plan should contain the expected resource types."""
        types = set(self.analysis["plan_summary"]["resource_types"])
        expected = {
            "aws_vpc", "aws_internet_gateway", "aws_subnet",
            "aws_eip", "aws_nat_gateway", "aws_security_group",
        }
        self.assertEqual(types, expected)

    def test_canon_findings_include_sg_patterns(self):
        """Canon findings should include SG-related entries from sg-interactions.json."""
        findings = self.analysis["canon_findings"]
        sg_sources = [f for f in findings if f["source"] == "sg-interactions.json"]
        self.assertGreater(len(sg_sources), 0, "Expected sg-interactions.json findings")

    def test_diagnostic_matches_cycle(self):
        """Cycle diagnostic in plan should match Canon error signature."""
        diag_matches = self.analysis["diagnostic_matches"]
        self.assertGreater(len(diag_matches), 0, "Expected diagnostic matches")
        summaries = [d["diagnostic"]["summary"] for d in diag_matches]
        self.assertTrue(
            any("Cycle" in s for s in summaries),
            f"Expected Cycle diagnostic match, got: {summaries}",
        )

    def test_limit_warnings_include_vpc(self):
        """Limit warnings should flag VPCs per region."""
        limits = self.analysis["limit_warnings"]
        limit_names = [w["limit"] for w in limits]
        self.assertIn("VPCs per region", limit_names)

    def test_limit_warnings_include_eip(self):
        """Limit warnings should flag Elastic IPs (3 NAT gateways = 3 of 5 EIPs)."""
        limits = self.analysis["limit_warnings"]
        limit_names = [w["limit"] for w in limits]
        self.assertIn("Elastic IPs per region", limit_names)

    def test_canon_search_resource_vpc(self):
        """canon_search --resource aws_vpc should return results."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "canon_search.py"),
             "--resource", "aws_vpc"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertGreater(output["count"], 0)

    def test_canon_search_error_cycle(self):
        """canon_search --error with SG cycle text should find signature."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "canon_search.py"),
             "--error", "Cycle: aws_security_group.web, aws_security_group.app"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertGreater(output["count"], 0)


class TestECSScenario(unittest.TestCase):
    """Scenario 2: ECS Fargate — Canon findings for ECS + ALB patterns."""

    @classmethod
    def setUpClass(cls):
        with open(ECS_FIXTURES / "plan.json") as f:
            cls.plan_data = json.load(f)
        cls.analysis = analyze(cls.plan_data)

    def test_canon_findings_for_ecs_service(self):
        """Canon findings should include ECS service entries."""
        findings = self.analysis["canon_findings"]
        ecs_findings = [f for f in findings if f["triggered_by"] == "aws_ecs_service"]
        self.assertGreater(len(ecs_findings), 0, "Expected aws_ecs_service Canon findings")

    def test_diagnostic_match_steady_state(self):
        """ECS steady state diagnostic should match Canon error signature."""
        diag_matches = self.analysis["diagnostic_matches"]
        summaries = [d["diagnostic"]["summary"] for d in diag_matches]
        self.assertTrue(
            any("steady state" in s.lower() for s in summaries),
            f"Expected steady state diagnostic match, got: {summaries}",
        )

    def test_diagnostic_match_alb_subnets(self):
        """ALB 2-AZ subnet requirement should match Canon error signature."""
        diag_matches = self.analysis["diagnostic_matches"]
        summaries = [d["diagnostic"]["summary"] for d in diag_matches]
        self.assertTrue(
            any("subnets" in s.lower() and "availability zones" in s.lower() for s in summaries),
            f"Expected ALB subnet diagnostic match, got: {summaries}",
        )

    def test_canon_search_ecs_service(self):
        """canon_search --resource aws_ecs_service should return results."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "canon_search.py"),
             "--resource", "aws_ecs_service"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertGreater(output["count"], 0)

    def test_canon_search_error_health_check(self):
        """Error search with ECS health check text should find signature."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "canon_search.py"),
             "--error", "Error waiting for ECS service to reach a steady state: health check failure"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertGreater(output["count"], 0)

    def test_canon_search_error_cluster_not_found(self):
        """Error search with ClusterNotFound text should find signature."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "canon_search.py"),
             "--error", "Error creating ECS service ClusterNotFoundException"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertGreater(output["count"], 0)


class TestNamingPersistence(unittest.TestCase):
    """Scenario 3: Convention confidence grows across sessions until it overrides Canon."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        # Pre-insert session rows for FK constraints
        for sid in ("session-A", "session-B", "session-C"):
            self.conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)", (sid,)
            )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_session1_record_convention(self):
        """Session 1: record_convention → confidence = 0.5, distinct_sessions = 1."""
        cid = record_convention(
            self.conn, category="naming", pattern="s3-buckets-use-kebab-case",
            example="my-project-prod-logs", session_id="session-A",
        )
        convs = lookup_conventions(self.conn, category="naming")
        self.assertEqual(len(convs), 1)
        self.assertAlmostEqual(convs[0]["confidence"], 0.5)
        self.assertEqual(convs[0]["distinct_sessions"], 1)

    def test_session2_reinforce(self):
        """Session 2: reinforce from new session → confidence = 0.6, distinct_sessions = 2."""
        cid = record_convention(
            self.conn, category="naming", pattern="s3-buckets-use-kebab-case",
            session_id="session-A",
        )
        new_conf = reinforce_convention(self.conn, cid, session_id="session-B")
        self.assertAlmostEqual(new_conf, 0.6)
        convs = lookup_conventions(self.conn, category="naming")
        self.assertEqual(convs[0]["distinct_sessions"], 2)

    def test_session3_reinforce(self):
        """Session 3: reinforce again → confidence = 0.7, distinct_sessions = 3."""
        cid = record_convention(
            self.conn, category="naming", pattern="s3-buckets-use-kebab-case",
            session_id="session-A",
        )
        reinforce_convention(self.conn, cid, session_id="session-B")
        new_conf = reinforce_convention(self.conn, cid, session_id="session-C")
        self.assertAlmostEqual(new_conf, 0.7)
        convs = lookup_conventions(self.conn, category="naming")
        self.assertEqual(convs[0]["distinct_sessions"], 3)

    def test_effective_confidence_reaches_override(self):
        """After 3 sessions: effective_confidence = 0.7 + 0.1 = 0.8 (overrides Canon)."""
        cid = record_convention(
            self.conn, category="naming", pattern="s3-buckets-use-kebab-case",
            session_id="session-A",
        )
        reinforce_convention(self.conn, cid, session_id="session-B")
        reinforce_convention(self.conn, cid, session_id="session-C")

        convs = lookup_conventions(self.conn, category="naming")
        eff = convs[0]["effective_confidence"]
        # 0.7 + (3-1)*0.05 = 0.7 + 0.1 = 0.8
        self.assertAlmostEqual(eff, 0.8)

    def test_should_override_at_threshold(self):
        """_should_override_convention returns True at effective_confidence >= 0.8."""
        cid = record_convention(
            self.conn, category="naming", pattern="s3-buckets-use-kebab-case",
            session_id="session-A",
        )
        reinforce_convention(self.conn, cid, session_id="session-B")
        reinforce_convention(self.conn, cid, session_id="session-C")

        convs = lookup_conventions(self.conn, category="naming")
        should_override, reason = _should_override_convention(convs[0])
        self.assertTrue(should_override, f"Expected override at eff_conf=0.8, reason={reason}")
        self.assertIn("0.8", reason)


class TestForkE2E(unittest.TestCase):
    """Scenario 5: Fork with team-scoped Memories via fork-memory.sh."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source_db = os.path.join(self.tmpdir, "source.db")
        self.output_db = os.path.join(self.tmpdir, "fork.db")
        self._populate_source()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _populate_source(self):
        """Create a source DB with mixed-scope entries."""
        conn = sqlite3.connect(self.source_db)
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        # Personal entries (should NOT appear in fork)
        record_fix(conn, "personal error", "cause", "fix",
                    scope="personal", session_id=None)
        record_convention(conn, "naming", "personal-pattern",
                          scope="personal", session_id=None)

        # Team entries (should appear in fork with scope=team)
        record_fix(conn, "team error", "team cause", "team fix",
                    scope="team", session_id=None)
        record_convention(conn, "naming", "team-pattern",
                          scope="team", session_id=None)
        record_quirk(conn, "ec2", "team quirk",
                      scope="team", session_id=None)

        # Org entries (should appear in fork)
        record_fix(conn, "org error", "org cause", "org fix",
                    scope="org", session_id=None)

        conn.close()

    def test_fork_script_runs(self):
        """fork-memory.sh should execute successfully."""
        result = subprocess.run(
            [str(SCRIPTS_DIR / "fork-memory.sh"),
             "--scope", "team", "--output", self.output_db],
            capture_output=True, text=True,
            env={**os.environ, "BOID_MEMORY_DB": self.source_db},
            cwd=str(PROJECT_ROOT),
        )
        self.assertEqual(result.returncode, 0, f"fork-memory.sh failed: {result.stderr}")

    def test_fork_output_exists(self):
        """Forked database file should be created."""
        subprocess.run(
            [str(SCRIPTS_DIR / "fork-memory.sh"),
             "--scope", "team", "--output", self.output_db],
            capture_output=True, text=True,
            env={**os.environ, "BOID_MEMORY_DB": self.source_db},
            cwd=str(PROJECT_ROOT),
        )
        self.assertTrue(os.path.exists(self.output_db), "Fork output DB not created")

    def test_fork_excludes_personal(self):
        """Forked DB should not contain personal-scoped entries."""
        subprocess.run(
            [str(SCRIPTS_DIR / "fork-memory.sh"),
             "--scope", "team", "--output", self.output_db],
            capture_output=True, text=True,
            env={**os.environ, "BOID_MEMORY_DB": self.source_db},
            cwd=str(PROJECT_ROOT),
        )
        conn = sqlite3.connect(self.output_db)
        fix_count = conn.execute("SELECT COUNT(*) FROM fixes WHERE scope = 'personal'").fetchone()[0]
        conv_count = conn.execute("SELECT COUNT(*) FROM conventions WHERE scope = 'personal'").fetchone()[0]
        conn.close()
        self.assertEqual(fix_count, 0, "Personal fixes should be excluded")
        self.assertEqual(conv_count, 0, "Personal conventions should be excluded")

    def test_fork_includes_team_and_org(self):
        """Forked DB should contain team and org entries with correct counts."""
        subprocess.run(
            [str(SCRIPTS_DIR / "fork-memory.sh"),
             "--scope", "team", "--output", self.output_db],
            capture_output=True, text=True,
            env={**os.environ, "BOID_MEMORY_DB": self.source_db},
            cwd=str(PROJECT_ROOT),
        )
        conn = sqlite3.connect(self.output_db)
        fix_count = conn.execute("SELECT COUNT(*) FROM fixes").fetchone()[0]
        conv_count = conn.execute("SELECT COUNT(*) FROM conventions").fetchone()[0]
        quirk_count = conn.execute("SELECT COUNT(*) FROM quirks").fetchone()[0]
        conn.close()
        # 1 team fix + 1 org fix = 2 fixes
        self.assertEqual(fix_count, 2, "Expected 2 fixes (team + org)")
        # 1 team convention
        self.assertEqual(conv_count, 1, "Expected 1 convention (team)")
        # 1 team quirk
        self.assertEqual(quirk_count, 1, "Expected 1 quirk (team)")


if __name__ == "__main__":
    unittest.main()
