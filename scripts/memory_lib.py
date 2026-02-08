#!/usr/bin/env python3
"""Memories CRUD library for the terraform-aws-boid Tier 2 knowledge store.

Provides write/read/confidence/merge/fork operations against the Memories SQLite DB.
Stdlib only — no pip dependencies. Mirrors canon_lib.py patterns.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

# ── Confidence model constants ───────────────────────────────────────

CONFIDENCE_BASE = 0.5
CORRECTION_DELTA = 0.2
REINFORCE_DELTA = 0.1
CONTRADICTION_RESET = 0.3
SINGLE_SESSION_CEILING = 0.7
SESSION_BONUS_PER = 0.05
SESSION_BONUS_CAP = 0.2
CONFIDENCE_CAP = 1.0

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "memory" / "schema.sql"


# ── Connection ───────────────────────────────────────────────────────

def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a connection to the Memories SQLite database.

    Reads BOID_MEMORY_DB env var if no path given.
    """
    if db_path is None:
        db_path = os.environ.get("BOID_MEMORY_DB", "memory/boid.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize the v2 schema on a connection (useful for :memory: databases)."""
    conn.executescript(SCHEMA_FILE.read_text())


# ── Helpers ──────────────────────────────────────────────────────────

def _normalize_error(error_text: str) -> str:
    """Normalize error text for hashing: lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", error_text.strip().lower())


def _error_hash(error_text: str) -> str:
    """SHA-256 hex digest of normalized error text."""
    return hashlib.sha256(_normalize_error(error_text).encode()).hexdigest()


def _now() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


# ── Write operations ─────────────────────────────────────────────────

def record_fix(
    conn: sqlite3.Connection,
    error_text: str,
    root_cause: str,
    fix: str,
    resource: Optional[str] = None,
    provider: Optional[str] = None,
    validated: int = 0,
    scope: str = "personal",
    session_id: Optional[str] = None,
) -> int:
    """Record a fix in Memories. Returns the row id.

    If a matching error_hash exists: bumps hit_count, updates updated_at.
    Otherwise inserts a new row.
    """
    eh = _error_hash(error_text)
    cur = conn.execute("SELECT id, hit_count FROM fixes WHERE error_hash = ?", (eh,))
    existing = cur.fetchone()

    if existing:
        row_id = existing["id"]
        conn.execute(
            "UPDATE fixes SET hit_count = ?, updated_at = ? WHERE id = ?",
            (existing["hit_count"] + 1, _now(), row_id),
        )
        conn.commit()
        return row_id

    cur = conn.execute(
        """INSERT INTO fixes
           (error_hash, error_text, root_cause, fix, resource, provider,
            validated, scope, session_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (eh, error_text, root_cause, fix, resource, provider,
         validated, scope, session_id),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def record_convention(
    conn: sqlite3.Connection,
    category: str,
    pattern: str,
    example: Optional[str] = None,
    source: str = "correction",
    scope: str = "personal",
    session_id: Optional[str] = None,
) -> int:
    """Record a convention in Memories. Returns the row id.

    If matching (category, pattern) exists: bumps confidence by CORRECTION_DELTA,
    updates distinct_sessions if session_id differs.
    Otherwise inserts a new row with confidence=CONFIDENCE_BASE.
    """
    cur = conn.execute(
        "SELECT id, confidence, session_id, distinct_sessions FROM conventions WHERE category = ? AND pattern = ?",
        (category, pattern),
    )
    existing = cur.fetchone()

    if existing:
        row_id = existing["id"]
        new_confidence = min(existing["confidence"] + CORRECTION_DELTA, CONFIDENCE_CAP)
        new_distinct = existing["distinct_sessions"]
        if session_id and session_id != existing["session_id"]:
            new_distinct += 1
        conn.execute(
            """UPDATE conventions
               SET confidence = ?, distinct_sessions = ?, session_id = ?, updated_at = ?
               WHERE id = ?""",
            (new_confidence, new_distinct, session_id, _now(), row_id),
        )
        conn.commit()
        return row_id

    cur = conn.execute(
        """INSERT INTO conventions
           (category, pattern, example, source, scope, confidence, session_id, distinct_sessions)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
        (category, pattern, example, source, scope, CONFIDENCE_BASE, session_id),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def record_quirk(
    conn: sqlite3.Connection,
    service: str,
    description: str,
    region: Optional[str] = None,
    workaround: Optional[str] = None,
    scope: str = "personal",
    session_id: Optional[str] = None,
) -> int:
    """Record an infrastructure quirk in Memories. Returns the row id."""
    cur = conn.execute(
        """INSERT INTO quirks
           (service, description, region, workaround, scope, session_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (service, description, region, workaround, scope, session_id),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


# ── Read operations ──────────────────────────────────────────────────

def lookup_fix(
    conn: sqlite3.Connection,
    error_text: Optional[str] = None,
    error_hash: Optional[str] = None,
    resource: Optional[str] = None,
    scope_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Look up fixes by error_hash (exact) or error_text (substring), optionally filtered by scope."""
    conditions: list[str] = []
    params: list[Any] = []

    if error_hash:
        conditions.append("error_hash = ?")
        params.append(error_hash)
    elif error_text:
        eh = _error_hash(error_text)
        conditions.append("error_hash = ?")
        params.append(eh)

    if resource:
        conditions.append("resource = ?")
        params.append(resource)

    if scope_filter:
        conditions.append("scope = ?")
        params.append(scope_filter)

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(f"SELECT * FROM fixes WHERE {where} ORDER BY hit_count DESC", params).fetchall()
    return [_row_to_dict(r) for r in rows]


def lookup_conventions(
    conn: sqlite3.Connection,
    category: Optional[str] = None,
    scope_filter: Optional[str] = None,
    min_confidence: float = 0.0,
) -> list[dict[str, Any]]:
    """Return conventions matching filters, with effective_confidence computed."""
    conditions: list[str] = []
    params: list[Any] = []

    if category:
        conditions.append("category = ?")
        params.append(category)

    if scope_filter:
        conditions.append("scope = ?")
        params.append(scope_filter)

    if min_confidence > 0.0:
        conditions.append("confidence >= ?")
        params.append(min_confidence)

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"SELECT * FROM conventions WHERE {where} ORDER BY confidence DESC", params
    ).fetchall()

    results = []
    for r in rows:
        d = _row_to_dict(r)
        d["effective_confidence"] = effective_confidence(d["confidence"], d["distinct_sessions"])
        results.append(d)
    return results


def lookup_quirks(
    conn: sqlite3.Connection,
    service: Optional[str] = None,
    region: Optional[str] = None,
    scope_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Look up quirks by service and/or region."""
    conditions: list[str] = []
    params: list[Any] = []

    if service:
        conditions.append("service = ?")
        params.append(service)

    if region:
        conditions.append("region = ?")
        params.append(region)

    if scope_filter:
        conditions.append("scope = ?")
        params.append(scope_filter)

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(f"SELECT * FROM quirks WHERE {where}", params).fetchall()
    return [_row_to_dict(r) for r in rows]


# ── Confidence model ─────────────────────────────────────────────────

def effective_confidence(raw: float, distinct_sessions: int) -> float:
    """Compute effective confidence factoring in session spread.

    Single-session conventions are capped at SINGLE_SESSION_CEILING.
    Multi-session conventions get a bonus up to SESSION_BONUS_CAP.
    """
    if distinct_sessions <= 1:
        return min(raw, SINGLE_SESSION_CEILING)
    session_bonus = min((distinct_sessions - 1) * SESSION_BONUS_PER, SESSION_BONUS_CAP)
    return min(raw + session_bonus, CONFIDENCE_CAP)


def reinforce_convention(
    conn: sqlite3.Connection,
    convention_id: int,
    session_id: Optional[str] = None,
) -> float:
    """Reinforce a convention: +0.1 confidence. Returns new raw confidence.

    If session_id is new for this convention, bumps distinct_sessions.
    """
    row = conn.execute(
        "SELECT confidence, session_id, distinct_sessions FROM conventions WHERE id = ?",
        (convention_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Convention {convention_id} not found")

    new_confidence = min(row["confidence"] + REINFORCE_DELTA, CONFIDENCE_CAP)
    new_distinct = row["distinct_sessions"]
    update_session_id = row["session_id"]

    if session_id and session_id != row["session_id"]:
        new_distinct += 1
        update_session_id = session_id

    conn.execute(
        """UPDATE conventions
           SET confidence = ?, distinct_sessions = ?, session_id = ?, updated_at = ?
           WHERE id = ?""",
        (new_confidence, new_distinct, update_session_id, _now(), convention_id),
    )
    conn.commit()
    return new_confidence


def contradict_convention(
    conn: sqlite3.Connection,
    convention_id: int,
) -> float:
    """Contradict a convention: reset confidence to CONTRADICTION_RESET.

    Does NOT reset distinct_sessions.
    """
    conn.execute(
        "UPDATE conventions SET confidence = ?, updated_at = ? WHERE id = ?",
        (CONTRADICTION_RESET, _now(), convention_id),
    )
    conn.commit()
    return CONTRADICTION_RESET


# ── Integrated query (Canon + Memories merge) ────────────────────────

def query_with_priority(
    error_text: str,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Query both Canon and Memories, return merged results with override metadata.

    Returns:
        {
            "canon_results": [...],
            "memory_results": [...],
            "merged": [
                {
                    "source": "canon" | "memory",
                    "overrides_canon": bool,
                    "override_reason": str | None,
                    "entry": <the actual data>
                },
                ...
            ]
        }

    Ordering in merged: overriding Memory entries first, then Canon results,
    then non-overriding Memory entries.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from canon_lib import load_canon, match_error

    # Canon lookup
    canon_results: list[dict[str, Any]] = []
    try:
        sigs = load_canon("error-signatures.json")
        canon_results = match_error(error_text, sigs.get("signatures", []))
    except (FileNotFoundError, Exception):
        pass

    # Memory lookup
    conn = connect(db_path)
    memory_fixes = lookup_fix(conn, error_text=error_text)
    conn.close()

    # Classify memory results
    overriding: list[dict[str, Any]] = []
    non_overriding: list[dict[str, Any]] = []

    for fix in memory_fixes:
        override, reason = _should_override(fix)
        entry = {
            "source": "memory",
            "overrides_canon": override,
            "override_reason": reason,
            "entry": fix,
        }
        if override:
            overriding.append(entry)
        else:
            non_overriding.append(entry)

    # Canon entries
    canon_entries = [
        {
            "source": "canon",
            "overrides_canon": False,
            "override_reason": None,
            "entry": c,
        }
        for c in canon_results
    ]

    merged = overriding + canon_entries + non_overriding

    return {
        "canon_results": canon_results,
        "memory_results": memory_fixes,
        "merged": merged,
    }


def _should_override(fix: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Determine if a Memory fix should override Canon results.

    Returns (should_override, reason).
    """
    scope = fix.get("scope", "personal")

    if scope in ("team", "org"):
        return True, f"{scope}-scoped"

    # Personal scope: must be validated
    if scope == "personal":
        if fix.get("validated") == 1:
            return True, "validated fix"
        return False, None

    return False, None


def _should_override_convention(conv: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Determine if a Memory convention should override Canon results.

    Returns (should_override, reason).
    """
    scope = conv.get("scope", "personal")

    if scope in ("team", "org"):
        return True, f"{scope}-scoped"

    if scope == "personal":
        eff = effective_confidence(
            conv.get("confidence", 0.0),
            conv.get("distinct_sessions", 1),
        )
        if eff >= 0.8 - 1e-9:
            return True, f"confidence {eff:.2f} >= 0.8"
        return False, None

    return False, None


# ── Fork export ──────────────────────────────────────────────────────

def export_for_fork(
    db_path: str,
    output_path: str,
    scope_filter: str = "team",
) -> Path:
    """Export entries matching scope filter to a new DB for forking.

    scope_filter='team' includes team + org entries.
    scope_filter='org' includes only org entries.

    Strips session provenance. Does not copy sessions table rows.
    Conventions retain confidence but reset distinct_sessions to 1.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing output if present
    if out.exists():
        out.unlink()

    # Create new DB with v2 schema
    dst = sqlite3.connect(str(out))
    dst.executescript(SCHEMA_FILE.read_text())

    # Determine qualifying scopes
    if scope_filter == "org":
        scopes = ("org",)
    else:
        scopes = ("team", "org")

    src = sqlite3.connect(db_path)
    src.row_factory = sqlite3.Row

    # Copy fixes
    placeholders = ",".join("?" for _ in scopes)
    fixes = src.execute(
        f"SELECT * FROM fixes WHERE scope IN ({placeholders})", scopes
    ).fetchall()
    fix_count = 0
    for f in fixes:
        dst.execute(
            """INSERT INTO fixes
               (error_hash, error_text, root_cause, fix, resource, provider,
                validated, scope, created_at, updated_at, hit_count, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (f["error_hash"], f["error_text"], f["root_cause"], f["fix"],
             f["resource"], f["provider"], f["validated"], f["scope"],
             f["created_at"], f["updated_at"], f["hit_count"]),
        )
        fix_count += 1

    # Copy conventions (reset distinct_sessions to 1)
    convs = src.execute(
        f"SELECT * FROM conventions WHERE scope IN ({placeholders})", scopes
    ).fetchall()
    conv_count = 0
    for c in convs:
        dst.execute(
            """INSERT INTO conventions
               (category, pattern, example, source, scope, created_at, updated_at,
                confidence, session_id, distinct_sessions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)""",
            (c["category"], c["pattern"], c["example"], c["source"], c["scope"],
             c["created_at"], c["updated_at"], c["confidence"]),
        )
        conv_count += 1

    # Copy quirks
    quirks = src.execute(
        f"SELECT * FROM quirks WHERE scope IN ({placeholders})", scopes
    ).fetchall()
    quirk_count = 0
    for q in quirks:
        dst.execute(
            """INSERT INTO quirks
               (service, description, region, workaround, scope, created_at, updated_at, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (q["service"], q["description"], q["region"], q["workaround"],
             q["scope"], q["created_at"], q["updated_at"]),
        )
        quirk_count += 1

    dst.commit()
    src.close()
    dst.close()

    return out
