#!/usr/bin/env python3
"""Test suite for the Memories integration (Phase 4).

Tests cover: schema v2, fix CRUD, convention CRUD, quirk CRUD,
confidence model, read priority (Canon vs Memories merge),
fork export, and schema migration.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure scripts/ is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import memory_lib

SCHEMA_FILE = Path(__file__).resolve().parent.parent.parent / "memory" / "schema.sql"
MIGRATE_FILE = Path(__file__).resolve().parent.parent.parent / "memory" / "migrate_v1_to_v2.sql"

# V1 schema for migration tests (without session_id columns)
V1_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS fixes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    error_hash  TEXT NOT NULL,
    error_text  TEXT NOT NULL,
    root_cause  TEXT NOT NULL,
    fix         TEXT NOT NULL,
    resource    TEXT,
    provider    TEXT,
    validated   INTEGER NOT NULL DEFAULT 0,
    scope       TEXT NOT NULL DEFAULT 'personal' CHECK (scope IN ('personal', 'team', 'org')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    hit_count   INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_fixes_error_hash ON fixes(error_hash);
CREATE INDEX IF NOT EXISTS idx_fixes_resource ON fixes(resource);
CREATE INDEX IF NOT EXISTS idx_fixes_scope ON fixes(scope);

CREATE TABLE IF NOT EXISTS conventions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    example     TEXT,
    source      TEXT NOT NULL DEFAULT 'correction',
    scope       TEXT NOT NULL DEFAULT 'personal' CHECK (scope IN ('personal', 'team', 'org')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    confidence  REAL NOT NULL DEFAULT 0.5
);

CREATE INDEX IF NOT EXISTS idx_conventions_category ON conventions(category);
CREATE INDEX IF NOT EXISTS idx_conventions_scope ON conventions(scope);

CREATE TABLE IF NOT EXISTS quirks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    service     TEXT NOT NULL,
    region      TEXT,
    description TEXT NOT NULL,
    workaround  TEXT,
    scope       TEXT NOT NULL DEFAULT 'personal' CHECK (scope IN ('personal', 'team', 'org')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_quirks_service ON quirks(service);
CREATE INDEX IF NOT EXISTS idx_quirks_scope ON quirks(scope);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL UNIQUE,
    started_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ended_at    TEXT,
    summary     TEXT,
    project_dir TEXT
);

CREATE TABLE IF NOT EXISTS metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO metadata (key, value) VALUES
    ('schema_version', '1'),
    ('created_at', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
"""


def _fresh_conn() -> sqlite3.Connection:
    """Create an in-memory SQLite connection with the v2 schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_FILE.read_text())
    return conn


def _insert_session(conn: sqlite3.Connection, session_id: str) -> None:
    """Insert a session row (required for FK constraints)."""
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
        (session_id,),
    )
    conn.commit()


# ── Schema Tests ─────────────────────────────────────────────────────


class TestSchemaV2(unittest.TestCase):
    """Test the v2 schema structure."""

    def test_schema_creates_without_error(self):
        conn = _fresh_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t["name"] for t in tables]
        self.assertIn("fixes", names)
        self.assertIn("conventions", names)
        self.assertIn("quirks", names)
        self.assertIn("sessions", names)
        self.assertIn("metadata", names)
        conn.close()

    def test_fixes_has_session_id(self):
        conn = _fresh_conn()
        cols = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(fixes)").fetchall()
        ]
        self.assertIn("session_id", cols)
        conn.close()

    def test_conventions_has_session_id(self):
        conn = _fresh_conn()
        cols = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(conventions)").fetchall()
        ]
        self.assertIn("session_id", cols)
        conn.close()

    def test_conventions_has_distinct_sessions(self):
        conn = _fresh_conn()
        cols = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(conventions)").fetchall()
        ]
        self.assertIn("distinct_sessions", cols)
        conn.close()

    def test_quirks_has_session_id(self):
        conn = _fresh_conn()
        cols = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(quirks)").fetchall()
        ]
        self.assertIn("session_id", cols)
        conn.close()

    def test_schema_version_is_2(self):
        conn = _fresh_conn()
        ver = conn.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        self.assertEqual(ver["value"], "2")
        conn.close()


# ── Fix CRUD Tests ───────────────────────────────────────────────────


class TestRecordFix(unittest.TestCase):
    """Test fix recording and lookup."""

    def setUp(self):
        self.conn = _fresh_conn()
        _insert_session(self.conn, "sess-001")

    def tearDown(self):
        self.conn.close()

    def test_basic_insert_returns_row_id(self):
        rid = memory_lib.record_fix(
            self.conn, "Error: timeout", "Network issue", "Increase timeout",
            session_id="sess-001",
        )
        self.assertIsInstance(rid, int)
        self.assertGreater(rid, 0)

    def test_duplicate_error_hash_bumps_hit_count(self):
        rid1 = memory_lib.record_fix(
            self.conn, "Error: timeout", "Network issue", "Increase timeout",
        )
        rid2 = memory_lib.record_fix(
            self.conn, "Error: timeout", "Network issue", "Increase timeout",
        )
        self.assertEqual(rid1, rid2)
        row = self.conn.execute(
            "SELECT hit_count FROM fixes WHERE id = ?", (rid1,)
        ).fetchone()
        self.assertEqual(row["hit_count"], 2)

    def test_session_id_is_stored(self):
        rid = memory_lib.record_fix(
            self.conn, "Error: auth", "Bad creds", "Fix creds",
            session_id="sess-001",
        )
        row = self.conn.execute(
            "SELECT session_id FROM fixes WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row["session_id"], "sess-001")

    def test_validated_flag_works(self):
        rid = memory_lib.record_fix(
            self.conn, "Error: perms", "IAM policy", "Add policy",
            validated=1, session_id="sess-001",
        )
        row = self.conn.execute(
            "SELECT validated FROM fixes WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row["validated"], 1)

    def test_scope_constraint_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            memory_lib.record_fix(
                self.conn, "Error: bad", "Bad", "Fix",
                scope="invalid",
            )

    def test_lookup_by_error_hash(self):
        memory_lib.record_fix(
            self.conn, "Error: timeout", "Network", "Increase timeout",
        )
        eh = memory_lib._error_hash("Error: timeout")
        results = memory_lib.lookup_fix(self.conn, error_hash=eh)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["root_cause"], "Network")

    def test_lookup_by_resource_filters(self):
        memory_lib.record_fix(
            self.conn, "Error: sg", "SG issue", "Fix SG",
            resource="aws_security_group",
        )
        memory_lib.record_fix(
            self.conn, "Error: iam", "IAM issue", "Fix IAM",
            resource="aws_iam_role",
        )
        results = memory_lib.lookup_fix(self.conn, resource="aws_iam_role")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource"], "aws_iam_role")


# ── Convention CRUD Tests ────────────────────────────────────────────


class TestRecordConvention(unittest.TestCase):
    """Test convention recording and lookup."""

    def setUp(self):
        self.conn = _fresh_conn()
        _insert_session(self.conn, "sess-001")
        _insert_session(self.conn, "sess-002")

    def tearDown(self):
        self.conn.close()

    def test_basic_insert_with_default_confidence(self):
        rid = memory_lib.record_convention(
            self.conn, "naming", "Use snake_case for resources",
            session_id="sess-001",
        )
        row = self.conn.execute(
            "SELECT confidence FROM conventions WHERE id = ?", (rid,)
        ).fetchone()
        self.assertAlmostEqual(row["confidence"], 0.5)

    def test_duplicate_bumps_confidence(self):
        rid1 = memory_lib.record_convention(
            self.conn, "naming", "Use snake_case for resources",
            session_id="sess-001",
        )
        rid2 = memory_lib.record_convention(
            self.conn, "naming", "Use snake_case for resources",
            session_id="sess-001",
        )
        self.assertEqual(rid1, rid2)
        row = self.conn.execute(
            "SELECT confidence FROM conventions WHERE id = ?", (rid1,)
        ).fetchone()
        self.assertAlmostEqual(row["confidence"], 0.7)  # 0.5 + 0.2

    def test_distinct_sessions_incremented_on_new_session(self):
        rid = memory_lib.record_convention(
            self.conn, "naming", "Use snake_case",
            session_id="sess-001",
        )
        memory_lib.record_convention(
            self.conn, "naming", "Use snake_case",
            session_id="sess-002",
        )
        row = self.conn.execute(
            "SELECT distinct_sessions FROM conventions WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row["distinct_sessions"], 2)

    def test_distinct_sessions_not_incremented_same_session(self):
        rid = memory_lib.record_convention(
            self.conn, "naming", "Use snake_case",
            session_id="sess-001",
        )
        memory_lib.record_convention(
            self.conn, "naming", "Use snake_case",
            session_id="sess-001",
        )
        row = self.conn.execute(
            "SELECT distinct_sessions FROM conventions WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row["distinct_sessions"], 1)

    def test_session_id_stored(self):
        rid = memory_lib.record_convention(
            self.conn, "tagging", "All resources get env tag",
            session_id="sess-001",
        )
        row = self.conn.execute(
            "SELECT session_id FROM conventions WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row["session_id"], "sess-001")

    def test_lookup_by_category(self):
        memory_lib.record_convention(self.conn, "naming", "snake_case")
        memory_lib.record_convention(self.conn, "tagging", "env tag")
        results = memory_lib.lookup_conventions(self.conn, category="naming")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["category"], "naming")

    def test_lookup_with_min_confidence_filter(self):
        memory_lib.record_convention(self.conn, "naming", "snake_case")  # 0.5
        memory_lib.record_convention(
            self.conn, "naming", "snake_case"
        )  # bumped to 0.7
        memory_lib.record_convention(self.conn, "tagging", "env tag")  # 0.5
        results = memory_lib.lookup_conventions(
            self.conn, min_confidence=0.6
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["pattern"], "snake_case")

    def test_scope_constraint_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            memory_lib.record_convention(
                self.conn, "naming", "bad", scope="invalid",
            )


# ── Quirk CRUD Tests ────────────────────────────────────────────────


class TestRecordQuirk(unittest.TestCase):
    """Test quirk recording and lookup."""

    def setUp(self):
        self.conn = _fresh_conn()
        _insert_session(self.conn, "sess-001")

    def tearDown(self):
        self.conn.close()

    def test_basic_insert(self):
        rid = memory_lib.record_quirk(
            self.conn, "ec2", "t2.micro limited to 1 vCPU",
            session_id="sess-001",
        )
        self.assertIsInstance(rid, int)
        self.assertGreater(rid, 0)

    def test_lookup_by_service(self):
        memory_lib.record_quirk(self.conn, "ec2", "t2 limit")
        memory_lib.record_quirk(self.conn, "rds", "aurora issue")
        results = memory_lib.lookup_quirks(self.conn, service="ec2")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["service"], "ec2")

    def test_lookup_by_service_and_region(self):
        memory_lib.record_quirk(
            self.conn, "ec2", "us-east-1 limit", region="us-east-1"
        )
        memory_lib.record_quirk(
            self.conn, "ec2", "eu-west-1 issue", region="eu-west-1"
        )
        results = memory_lib.lookup_quirks(
            self.conn, service="ec2", region="us-east-1"
        )
        self.assertEqual(len(results), 1)
        self.assertIn("us-east-1", results[0]["description"])

    def test_session_id_stored(self):
        rid = memory_lib.record_quirk(
            self.conn, "iam", "eventual consistency",
            session_id="sess-001",
        )
        row = self.conn.execute(
            "SELECT session_id FROM quirks WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row["session_id"], "sess-001")


# ── Confidence Model Tests ───────────────────────────────────────────


class TestConfidenceModel(unittest.TestCase):
    """Test the session-weighted confidence model."""

    def setUp(self):
        self.conn = _fresh_conn()
        _insert_session(self.conn, "sess-001")
        _insert_session(self.conn, "sess-002")
        _insert_session(self.conn, "sess-003")
        _insert_session(self.conn, "sess-004")
        _insert_session(self.conn, "sess-005")

    def tearDown(self):
        self.conn.close()

    def test_reinforce_adds_delta(self):
        rid = memory_lib.record_convention(
            self.conn, "naming", "snake_case", session_id="sess-001",
        )
        new_conf = memory_lib.reinforce_convention(self.conn, rid)
        self.assertAlmostEqual(new_conf, 0.6)  # 0.5 + 0.1

    def test_reinforce_caps_at_1(self):
        rid = memory_lib.record_convention(
            self.conn, "naming", "snake_case", session_id="sess-001",
        )
        # Manually set confidence high
        self.conn.execute(
            "UPDATE conventions SET confidence = 0.95 WHERE id = ?", (rid,)
        )
        self.conn.commit()
        new_conf = memory_lib.reinforce_convention(self.conn, rid)
        self.assertAlmostEqual(new_conf, 1.0)

    def test_contradict_resets_to_0_3(self):
        rid = memory_lib.record_convention(
            self.conn, "naming", "snake_case", session_id="sess-001",
        )
        memory_lib.reinforce_convention(self.conn, rid)  # 0.6
        new_conf = memory_lib.contradict_convention(self.conn, rid)
        self.assertAlmostEqual(new_conf, 0.3)

    def test_effective_confidence_single_session_ceiling(self):
        eff = memory_lib.effective_confidence(0.9, 1)
        self.assertAlmostEqual(eff, 0.7)  # capped

    def test_effective_confidence_3_sessions(self):
        eff = memory_lib.effective_confidence(0.7, 3)
        # bonus = (3-1) * 0.05 = 0.1
        self.assertAlmostEqual(eff, 0.8)

    def test_effective_confidence_5_sessions(self):
        eff = memory_lib.effective_confidence(0.7, 5)
        # bonus = min((5-1)*0.05, 0.2) = 0.2
        self.assertAlmostEqual(eff, 0.9)

    def test_effective_confidence_caps_at_1(self):
        eff = memory_lib.effective_confidence(0.95, 10)
        # bonus = 0.2 (capped), 0.95 + 0.2 = 1.15 → capped at 1.0
        self.assertAlmostEqual(eff, 1.0)

    def test_reinforce_from_new_session_bumps_distinct(self):
        rid = memory_lib.record_convention(
            self.conn, "naming", "snake_case", session_id="sess-001",
        )
        memory_lib.reinforce_convention(self.conn, rid, session_id="sess-002")
        row = self.conn.execute(
            "SELECT distinct_sessions FROM conventions WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row["distinct_sessions"], 2)

    def test_reinforce_from_same_session_no_bump(self):
        rid = memory_lib.record_convention(
            self.conn, "naming", "snake_case", session_id="sess-001",
        )
        memory_lib.reinforce_convention(self.conn, rid, session_id="sess-001")
        row = self.conn.execute(
            "SELECT distinct_sessions FROM conventions WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row["distinct_sessions"], 1)

    def test_full_lifecycle(self):
        """correction → reinforce ×3 from different sessions → verify effective."""
        rid = memory_lib.record_convention(
            self.conn, "naming", "snake_case", session_id="sess-001",
        )  # conf=0.5, sessions=1

        memory_lib.reinforce_convention(self.conn, rid, session_id="sess-002")
        # conf=0.6, sessions=2
        memory_lib.reinforce_convention(self.conn, rid, session_id="sess-003")
        # conf=0.7, sessions=3
        memory_lib.reinforce_convention(self.conn, rid, session_id="sess-004")
        # conf=0.8, sessions=4

        row = self.conn.execute(
            "SELECT confidence, distinct_sessions FROM conventions WHERE id = ?",
            (rid,),
        ).fetchone()

        self.assertAlmostEqual(row["confidence"], 0.8)
        self.assertEqual(row["distinct_sessions"], 4)

        eff = memory_lib.effective_confidence(
            row["confidence"], row["distinct_sessions"]
        )
        # bonus = (4-1)*0.05 = 0.15, eff = 0.8 + 0.15 = 0.95
        self.assertAlmostEqual(eff, 0.95)


# ── Read Priority Tests ─────────────────────────────────────────────


class TestReadPriority(unittest.TestCase):
    """Test Canon vs Memories merge priority logic."""

    def setUp(self):
        self.conn = _fresh_conn()
        _insert_session(self.conn, "sess-001")
        _insert_session(self.conn, "sess-002")

    def tearDown(self):
        self.conn.close()

    def test_team_scoped_overrides_canon(self):
        fix = {
            "scope": "team",
            "validated": 0,
            "confidence": 0.3,
        }
        override, reason = memory_lib._should_override(fix)
        self.assertTrue(override)
        self.assertEqual(reason, "team-scoped")

    def test_org_scoped_overrides_canon(self):
        fix = {"scope": "org", "validated": 0}
        override, reason = memory_lib._should_override(fix)
        self.assertTrue(override)
        self.assertEqual(reason, "org-scoped")

    def test_personal_unvalidated_does_not_override(self):
        fix = {"scope": "personal", "validated": 0}
        override, reason = memory_lib._should_override(fix)
        self.assertFalse(override)
        self.assertIsNone(reason)

    def test_personal_validated_overrides(self):
        fix = {"scope": "personal", "validated": 1}
        override, reason = memory_lib._should_override(fix)
        self.assertTrue(override)
        self.assertEqual(reason, "validated fix")

    def test_convention_below_threshold_does_not_override(self):
        conv = {
            "scope": "personal",
            "confidence": 0.7,
            "distinct_sessions": 1,
        }
        override, reason = memory_lib._should_override_convention(conv)
        # effective = min(0.7, 0.7) = 0.7 < 0.8
        self.assertFalse(override)

    def test_convention_at_threshold_overrides(self):
        conv = {
            "scope": "personal",
            "confidence": 0.7,
            "distinct_sessions": 3,
        }
        override, reason = memory_lib._should_override_convention(conv)
        # effective = 0.7 + (3-1)*0.05 = 0.8 >= 0.8
        self.assertTrue(override)
        self.assertIn("0.80", reason)

    def test_convention_just_below_threshold(self):
        conv = {
            "scope": "personal",
            "confidence": 0.69,
            "distinct_sessions": 3,
        }
        override, reason = memory_lib._should_override_convention(conv)
        # effective = 0.69 + 0.10 = 0.79 < 0.8
        self.assertFalse(override)

    def test_merged_output_structure(self):
        """Verify merged output has correct structure with both sources."""
        # Insert a team-scoped fix that will override
        memory_lib.record_fix(
            self.conn, "Error creating S3 bucket", "Bucket name taken",
            "Use unique prefix", scope="team", session_id="sess-001",
        )
        # Insert a personal unvalidated fix that won't override
        memory_lib.record_fix(
            self.conn, "Error in IAM policy", "Bad ARN", "Fix ARN",
            scope="personal", validated=0, session_id="sess-001",
        )

        # Test the _should_override logic on actual DB rows
        fixes = memory_lib.lookup_fix(self.conn)
        self.assertEqual(len(fixes), 2)

        team_fix = [f for f in fixes if f["scope"] == "team"][0]
        personal_fix = [f for f in fixes if f["scope"] == "personal"][0]

        override_t, reason_t = memory_lib._should_override(team_fix)
        override_p, reason_p = memory_lib._should_override(personal_fix)

        self.assertTrue(override_t)
        self.assertEqual(reason_t, "team-scoped")
        self.assertFalse(override_p)
        self.assertIsNone(reason_p)


# ── Fork Export Tests ────────────────────────────────────────────────


class TestForkExport(unittest.TestCase):
    """Test fork export filtering and structure."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src_path = os.path.join(self.tmpdir, "source.db")
        self.dst_path = os.path.join(self.tmpdir, "fork.db")

        # Create source DB with v2 schema
        src = sqlite3.connect(self.src_path)
        src.executescript(SCHEMA_FILE.read_text())
        src.execute(
            "INSERT INTO sessions (session_id) VALUES ('sess-src')"
        )

        # Insert entries across all scopes
        src.execute(
            """INSERT INTO fixes (error_hash, error_text, root_cause, fix, scope, session_id)
               VALUES ('h1', 'personal fix', 'rc1', 'f1', 'personal', 'sess-src')"""
        )
        src.execute(
            """INSERT INTO fixes (error_hash, error_text, root_cause, fix, scope, session_id)
               VALUES ('h2', 'team fix', 'rc2', 'f2', 'team', 'sess-src')"""
        )
        src.execute(
            """INSERT INTO fixes (error_hash, error_text, root_cause, fix, scope, session_id)
               VALUES ('h3', 'org fix', 'rc3', 'f3', 'org', 'sess-src')"""
        )
        src.execute(
            """INSERT INTO conventions (category, pattern, scope, confidence, session_id, distinct_sessions)
               VALUES ('naming', 'personal conv', 'personal', 0.8, 'sess-src', 3)"""
        )
        src.execute(
            """INSERT INTO conventions (category, pattern, scope, confidence, session_id, distinct_sessions)
               VALUES ('naming', 'team conv', 'team', 0.9, 'sess-src', 5)"""
        )
        src.execute(
            """INSERT INTO quirks (service, description, scope, session_id)
               VALUES ('ec2', 'personal quirk', 'personal', 'sess-src')"""
        )
        src.execute(
            """INSERT INTO quirks (service, description, scope, session_id)
               VALUES ('rds', 'org quirk', 'org', 'sess-src')"""
        )
        src.commit()
        src.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_fork_team_includes_team_and_org(self):
        memory_lib.export_for_fork(self.src_path, self.dst_path, "team")
        dst = sqlite3.connect(self.dst_path)
        fixes = dst.execute("SELECT * FROM fixes").fetchall()
        self.assertEqual(len(fixes), 2)  # team + org
        dst.close()

    def test_fork_org_includes_only_org(self):
        memory_lib.export_for_fork(self.src_path, self.dst_path, "org")
        dst = sqlite3.connect(self.dst_path)
        fixes = dst.execute("SELECT * FROM fixes").fetchall()
        self.assertEqual(len(fixes), 1)  # org only
        dst.close()

    def test_fork_excludes_personal(self):
        memory_lib.export_for_fork(self.src_path, self.dst_path, "team")
        dst = sqlite3.connect(self.dst_path)
        dst.row_factory = sqlite3.Row
        all_fixes = dst.execute("SELECT scope FROM fixes").fetchall()
        scopes = [r["scope"] for r in all_fixes]
        self.assertNotIn("personal", scopes)

        all_convs = dst.execute("SELECT scope FROM conventions").fetchall()
        conv_scopes = [r["scope"] for r in all_convs]
        self.assertNotIn("personal", conv_scopes)

        all_quirks = dst.execute("SELECT scope FROM quirks").fetchall()
        quirk_scopes = [r["scope"] for r in all_quirks]
        self.assertNotIn("personal", quirk_scopes)
        dst.close()

    def test_fork_does_not_copy_sessions(self):
        memory_lib.export_for_fork(self.src_path, self.dst_path, "team")
        dst = sqlite3.connect(self.dst_path)
        sessions = dst.execute(
            "SELECT * FROM sessions"
        ).fetchall()
        self.assertEqual(len(sessions), 0)
        dst.close()

    def test_forked_db_has_v2_schema(self):
        memory_lib.export_for_fork(self.src_path, self.dst_path, "team")
        dst = sqlite3.connect(self.dst_path)
        dst.row_factory = sqlite3.Row
        ver = dst.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        self.assertEqual(ver["value"], "2")

        cols = [
            r["name"] for r in dst.execute("PRAGMA table_info(conventions)").fetchall()
        ]
        self.assertIn("distinct_sessions", cols)
        self.assertIn("session_id", cols)
        dst.close()

    def test_forked_conventions_reset_distinct_sessions(self):
        memory_lib.export_for_fork(self.src_path, self.dst_path, "team")
        dst = sqlite3.connect(self.dst_path)
        dst.row_factory = sqlite3.Row
        convs = dst.execute("SELECT * FROM conventions").fetchall()
        for c in convs:
            self.assertEqual(c["distinct_sessions"], 1)
            self.assertIsNone(c["session_id"])
        dst.close()


# ── Migration Tests ──────────────────────────────────────────────────


class TestMigration(unittest.TestCase):
    """Test schema migration from v1 to v2."""

    def test_v1_migrated_has_session_id_columns(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(V1_SCHEMA)
        conn.executescript(MIGRATE_FILE.read_text())

        for table in ("fixes", "conventions", "quirks"):
            cols = [
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            self.assertIn("session_id", cols, f"{table} missing session_id")

        # conventions should also have distinct_sessions
        conv_cols = [
            row[1]
            for row in conn.execute("PRAGMA table_info(conventions)").fetchall()
        ]
        self.assertIn("distinct_sessions", conv_cols)
        conn.close()

    def test_v1_data_preserved_after_migration(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(V1_SCHEMA)

        # Insert v1 data
        conn.execute(
            "INSERT INTO sessions (session_id) VALUES ('old-sess')"
        )
        conn.execute(
            """INSERT INTO fixes (error_hash, error_text, root_cause, fix)
               VALUES ('hash1', 'old error', 'old cause', 'old fix')"""
        )
        conn.execute(
            """INSERT INTO conventions (category, pattern)
               VALUES ('naming', 'old convention')"""
        )
        conn.commit()

        # Migrate
        conn.executescript(MIGRATE_FILE.read_text())

        # Verify data still there
        fix = conn.execute("SELECT * FROM fixes WHERE error_hash='hash1'").fetchone()
        self.assertIsNotNone(fix)

        conv = conn.execute(
            "SELECT * FROM conventions WHERE pattern='old convention'"
        ).fetchone()
        self.assertIsNotNone(conv)
        conn.close()

    def test_schema_version_updated_to_2(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(V1_SCHEMA)
        conn.row_factory = sqlite3.Row

        ver_before = conn.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        self.assertEqual(ver_before["value"], "1")

        conn.executescript(MIGRATE_FILE.read_text())

        ver_after = conn.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        self.assertEqual(ver_after["value"], "2")
        conn.close()


if __name__ == "__main__":
    unittest.main()
