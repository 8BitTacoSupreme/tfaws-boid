#!/usr/bin/env bash
# test-boid.sh — Run all boid test suites
#
# Usage: scripts/test-boid.sh [-v] [--suite SUITE]
#   -v          Verbose output
#   --suite     Run a specific suite: canon, phase3, memory, e2e
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

VERBOSE=""
SUITE="all"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v) VERBOSE="-v"; shift ;;
        --suite) SUITE="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: scripts/test-boid.sh [-v] [--suite SUITE]"
            echo "  -v          Verbose output"
            echo "  --suite     Run a specific suite: canon, phase3, memory, e2e"
            exit 0
            ;;
        *) echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
done

PASS=0
FAIL=0

run_step() {
    local label="$1"
    shift
    echo ""
    echo "=== ${label} ==="
    if "$@"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        echo "FAILED: ${label}"
    fi
}

# Step 1: Canon JSON validation
if [[ "${SUITE}" == "all" || "${SUITE}" == "canon" ]]; then
    run_step "Canon JSON validation" bash -c '
        for f in canon/*.json; do
            jq . "$f" > /dev/null || exit 1
        done
        echo "All Canon JSON files are valid"
    '
fi

# Step 2: Canon retrieval tests
if [[ "${SUITE}" == "all" || "${SUITE}" == "canon" ]]; then
    run_step "Canon retrieval tests" python3 -m unittest discover tests/canon/ ${VERBOSE}
fi

# Step 3: Phase 3 integration tests
if [[ "${SUITE}" == "all" || "${SUITE}" == "phase3" ]]; then
    run_step "Phase 3 integration tests" python3 -m unittest discover tests/phase3/ ${VERBOSE}
fi

# Step 4: Memories tests
if [[ "${SUITE}" == "all" || "${SUITE}" == "memory" ]]; then
    run_step "Memories tests" python3 -m unittest discover tests/memory/ ${VERBOSE}
fi

# Step 5: E2E scenario tests
if [[ "${SUITE}" == "all" || "${SUITE}" == "e2e" ]]; then
    run_step "E2E scenario tests" python3 -m unittest discover tests/e2e/ ${VERBOSE}
fi

echo ""
echo "================================"
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ ${FAIL} -gt 0 ]]; then
    echo "SOME TESTS FAILED"
    exit 1
fi
echo "All tests passed!"
