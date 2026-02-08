#!/usr/bin/env bash
# terraform-aws-boid activation hook
# Runs on `flox activate` — initializes Memories DB, validates Canon, sets env vars.
set -euo pipefail

BOID_DIR="${BOID_HOME:-${FLOX_ENV_PROJECT:-.}}"
MEMORY_DB="${BOID_MEMORY_DB:-${BOID_DIR}/memory/boid.db}"
CANON_DIR="${BOID_CANON_DIR:-${BOID_DIR}/canon}"
SCHEMA_FILE="${BOID_DIR}/memory/schema.sql"

# --- Initialize Memories SQLite DB (Tier 2) ---
if [[ ! -f "${MEMORY_DB}" ]]; then
    echo "[boid] Initializing Memories database..."
    if [[ -f "${SCHEMA_FILE}" ]]; then
        sqlite3 "${MEMORY_DB}" < "${SCHEMA_FILE}"
        echo "[boid] Memories database created at ${MEMORY_DB}"
    else
        echo "[boid] WARNING: schema.sql not found at ${SCHEMA_FILE}"
    fi
else
    echo "[boid] Memories database loaded ($(sqlite3 "${MEMORY_DB}" "SELECT value FROM metadata WHERE key='schema_version';" 2>/dev/null || echo 'unknown') schema)"
fi

# --- Migrate schema if needed ---
if [[ -f "${MEMORY_DB}" ]]; then
    SCHEMA_VER="$(sqlite3 "${MEMORY_DB}" "SELECT value FROM metadata WHERE key='schema_version';" 2>/dev/null || echo '0')"
    if [[ "${SCHEMA_VER}" == "1" ]]; then
        echo "[boid] Migrating Memories schema v1 → v2..."
        sqlite3 "${MEMORY_DB}" < "${BOID_DIR}/memory/migrate_v1_to_v2.sql"
        echo "[boid] Migration complete"
    fi
fi

# --- Validate Canon files exist (Tier 1) ---
canon_files=("error-signatures.json" "aws-limits.json" "provider-compat.json" "iam-eval-rules.json" "sg-interactions.json")
canon_count=0
for f in "${canon_files[@]}"; do
    if [[ -f "${CANON_DIR}/${f}" ]]; then
        canon_count=$((canon_count + 1))
    fi
done
echo "[boid] Canon: ${canon_count}/${#canon_files[@]} knowledge files loaded"

# --- Record session start ---
SESSION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
if [[ -f "${MEMORY_DB}" ]]; then
    sqlite3 "${MEMORY_DB}" "INSERT INTO sessions (session_id, project_dir) VALUES ('${SESSION_ID}', '${BOID_DIR}');" 2>/dev/null || true
fi

# --- Export env vars for the session ---
export BOID_HOME="${BOID_DIR}"
export BOID_SESSION_ID="${SESSION_ID}"
export BOID_MEMORY_DB="${MEMORY_DB}"
export BOID_CANON_DIR="${CANON_DIR}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_ENDPOINT_URL="${AWS_ENDPOINT_URL:-}"

echo "[boid] Session ${SESSION_ID:0:8}... started"
echo "[boid] terraform-aws-boid ready"
