-- terraform-aws-boid Memories Schema (Tier 2)
-- SQLite database for earned knowledge that persists across sessions.
-- Created on first `flox activate`, grows with use.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Validated fixes: error → resolution mappings learned from experience
CREATE TABLE IF NOT EXISTS fixes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    error_hash  TEXT NOT NULL,               -- SHA-256 of normalized error text
    error_text  TEXT NOT NULL,               -- Original error message
    root_cause  TEXT NOT NULL,               -- Diagnosed root cause
    fix         TEXT NOT NULL,               -- The fix that worked
    resource    TEXT,                         -- Terraform resource type (e.g. aws_iam_role)
    provider    TEXT,                         -- Provider name (e.g. aws)
    validated   INTEGER NOT NULL DEFAULT 0,  -- 1 if validated in sandbox
    scope       TEXT NOT NULL DEFAULT 'personal' CHECK (scope IN ('personal', 'team', 'org')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    hit_count   INTEGER NOT NULL DEFAULT 1,  -- Times this fix was applied
    session_id  TEXT REFERENCES sessions(session_id) -- Session that created this entry
);

CREATE INDEX IF NOT EXISTS idx_fixes_error_hash ON fixes(error_hash);
CREATE INDEX IF NOT EXISTS idx_fixes_resource ON fixes(resource);
CREATE INDEX IF NOT EXISTS idx_fixes_scope ON fixes(scope);
CREATE INDEX IF NOT EXISTS idx_fixes_session ON fixes(session_id);

-- Conventions: naming, structure, and tagging rules learned from corrections
CREATE TABLE IF NOT EXISTS conventions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,               -- e.g. 'naming', 'tagging', 'structure', 'module'
    pattern     TEXT NOT NULL,               -- The convention (e.g. "s3 buckets use {project}-{env}-{purpose}")
    example     TEXT,                        -- Concrete example
    source      TEXT NOT NULL DEFAULT 'correction', -- 'correction' | 'explicit' | 'inferred'
    scope       TEXT NOT NULL DEFAULT 'personal' CHECK (scope IN ('personal', 'team', 'org')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    confidence  REAL NOT NULL DEFAULT 0.5,   -- 0.0-1.0, increases with repeated use
    session_id  TEXT REFERENCES sessions(session_id), -- Session that created this entry
    distinct_sessions INTEGER NOT NULL DEFAULT 1  -- Number of distinct sessions confirming this
);

CREATE INDEX IF NOT EXISTS idx_conventions_category ON conventions(category);
CREATE INDEX IF NOT EXISTS idx_conventions_scope ON conventions(scope);
CREATE INDEX IF NOT EXISTS idx_conventions_session ON conventions(session_id);

-- Infrastructure quirks: local/team-specific AWS or Terraform gotchas
CREATE TABLE IF NOT EXISTS quirks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    service     TEXT NOT NULL,               -- AWS service (e.g. 'ec2', 'iam', 'rds')
    region      TEXT,                        -- AWS region if region-specific
    description TEXT NOT NULL,               -- What the quirk is
    workaround  TEXT,                        -- How to work around it
    scope       TEXT NOT NULL DEFAULT 'personal' CHECK (scope IN ('personal', 'team', 'org')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    session_id  TEXT REFERENCES sessions(session_id) -- Session that created this entry
);

CREATE INDEX IF NOT EXISTS idx_quirks_service ON quirks(service);
CREATE INDEX IF NOT EXISTS idx_quirks_scope ON quirks(scope);
CREATE INDEX IF NOT EXISTS idx_quirks_session ON quirks(session_id);

-- Session log: tracks what the agent did across sessions for continuity
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL UNIQUE,        -- UUID per activation
    started_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ended_at    TEXT,
    summary     TEXT,                        -- Brief summary of what was accomplished
    project_dir TEXT                         -- Working directory for this session
);

-- Metadata: key-value store for boid state
CREATE TABLE IF NOT EXISTS metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Seed metadata
INSERT OR IGNORE INTO metadata (key, value) VALUES
    ('schema_version', '2'),
    ('created_at', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
