#!/usr/bin/env bash
# Initialize or reset the Memories SQLite database from schema.sql
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
SCHEMA_FILE="${PROJECT_DIR}/memory/schema.sql"
DB_FILE="${PROJECT_DIR}/memory/boid.db"

if [[ ! -f "${SCHEMA_FILE}" ]]; then
    echo "ERROR: schema.sql not found at ${SCHEMA_FILE}"
    exit 1
fi

if [[ -f "${DB_FILE}" ]]; then
    echo "Database already exists at ${DB_FILE}"
    read -r -p "Reset it? [y/N] " confirm
    if [[ "${confirm}" =~ ^[Yy]$ ]]; then
        rm "${DB_FILE}" "${DB_FILE}-wal" "${DB_FILE}-shm" 2>/dev/null || true
        echo "Removed existing database"
    else
        echo "Aborted"
        exit 0
    fi
fi

sqlite3 "${DB_FILE}" < "${SCHEMA_FILE}"
echo "Memories database initialized at ${DB_FILE}"
sqlite3 "${DB_FILE}" "SELECT key, value FROM metadata;"
