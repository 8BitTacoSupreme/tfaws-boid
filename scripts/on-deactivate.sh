#!/usr/bin/env bash
# terraform-aws-boid deactivation hook
# Runs on environment exit — checkpoints session, cleans up.
set -euo pipefail

MEMORY_DB="${BOID_MEMORY_DB:-${FLOX_ENV_PROJECT:-.}/memory/boid.db}"

# --- Record session end ---
if [[ -n "${BOID_SESSION_ID:-}" ]] && [[ -f "${MEMORY_DB}" ]]; then
    sqlite3 "${MEMORY_DB}" \
        "UPDATE sessions SET ended_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE session_id = '${BOID_SESSION_ID}';" \
        2>/dev/null || true
    echo "[boid] Session ${BOID_SESSION_ID:0:8}... ended"
fi

# --- SQLite WAL checkpoint ---
if [[ -f "${MEMORY_DB}" ]]; then
    sqlite3 "${MEMORY_DB}" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null || true
fi

echo "[boid] Deactivated"
