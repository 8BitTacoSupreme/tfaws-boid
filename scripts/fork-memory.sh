#!/usr/bin/env bash
# Fork Memories database — export team/org-scoped entries for sharing.
# Usage: fork-memory.sh [--scope team|org] [--output path]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOID_DIR="$(dirname "${SCRIPT_DIR}")"

# Defaults
SCOPE="team"
OUTPUT="memory/boid-fork.db"
SOURCE_DB="${BOID_MEMORY_DB:-${BOID_DIR}/memory/boid.db}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scope)
            SCOPE="$2"
            if [[ "${SCOPE}" != "team" && "${SCOPE}" != "org" ]]; then
                echo "ERROR: --scope must be 'team' or 'org'" >&2
                exit 1
            fi
            shift 2
            ;;
        --output)
            OUTPUT="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: fork-memory.sh [--scope team|org] [--output path]"
            echo ""
            echo "Export team/org-scoped Memories entries to a new database for forking."
            echo ""
            echo "Options:"
            echo "  --scope   Scope filter: 'team' (team+org) or 'org' (org only). Default: team"
            echo "  --output  Output path for the forked DB. Default: memory/boid-fork.db"
            echo "  -h        Show this help"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

# Validate source DB exists
if [[ ! -f "${SOURCE_DB}" ]]; then
    echo "ERROR: Source database not found at ${SOURCE_DB}" >&2
    echo "Set BOID_MEMORY_DB or ensure memory/boid.db exists." >&2
    exit 1
fi

# Run the export
python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
from memory_lib import export_for_fork
result = export_for_fork('${SOURCE_DB}', '${OUTPUT}', scope_filter='${SCOPE}')
print(f'[boid] Forked database created at {result}')
"

# Report counts from the forked DB
if [[ -f "${OUTPUT}" ]]; then
    FIX_COUNT="$(sqlite3 "${OUTPUT}" "SELECT COUNT(*) FROM fixes;" 2>/dev/null || echo 0)"
    CONV_COUNT="$(sqlite3 "${OUTPUT}" "SELECT COUNT(*) FROM conventions;" 2>/dev/null || echo 0)"
    QUIRK_COUNT="$(sqlite3 "${OUTPUT}" "SELECT COUNT(*) FROM quirks;" 2>/dev/null || echo 0)"
    echo "[boid] Exported ${FIX_COUNT} fixes, ${CONV_COUNT} conventions, ${QUIRK_COUNT} quirks to ${OUTPUT}"
fi
