-- Migrate Memories schema v1 → v2
-- Adds session_id foreign keys, distinct_sessions tracking, and new indexes.

ALTER TABLE fixes ADD COLUMN session_id TEXT REFERENCES sessions(session_id);
ALTER TABLE conventions ADD COLUMN session_id TEXT REFERENCES sessions(session_id);
ALTER TABLE conventions ADD COLUMN distinct_sessions INTEGER NOT NULL DEFAULT 1;
ALTER TABLE quirks ADD COLUMN session_id TEXT REFERENCES sessions(session_id);

CREATE INDEX IF NOT EXISTS idx_fixes_session ON fixes(session_id);
CREATE INDEX IF NOT EXISTS idx_conventions_session ON conventions(session_id);
CREATE INDEX IF NOT EXISTS idx_quirks_session ON quirks(session_id);

UPDATE metadata SET value = '2', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE key = 'schema_version';
