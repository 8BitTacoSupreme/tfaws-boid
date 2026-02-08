#!/usr/bin/env bash
set -euo pipefail

# test-canon.sh — Run Canon retrieval and schema tests

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/.."

echo "═══════════════════════════════════════════════════"
echo "  Canon Retrieval & Schema Tests"
echo "═══════════════════════════════════════════════════"
echo ""

# Validate JSON first
echo "Step 1: Validating Canon JSON..."
for f in "$PROJECT_DIR"/canon/*.json; do
    if jq . "$f" > /dev/null 2>&1; then
        echo "  ✓ $(basename "$f")"
    else
        echo "  ✗ $(basename "$f") — INVALID JSON"
        exit 1
    fi
done

# Run Python tests
echo ""
echo "Step 2: Running Python test suite..."
echo ""
python3 -m unittest discover -s "$PROJECT_DIR/tests/canon" -p "test_*.py" -v

echo ""
echo "═══════════════════════════════════════════════════"
echo "  All Canon tests passed!"
echo "═══════════════════════════════════════════════════"
