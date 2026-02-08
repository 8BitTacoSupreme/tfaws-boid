#!/usr/bin/env bash
set -euo pipefail

# seed-canon.sh — Orchestrator: validate all Canon JSON and report entry counts
# Usage: ./scripts/seed-canon.sh [--validate-only]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANON_DIR="$SCRIPT_DIR/../canon"

validate_only=false
if [[ "${1:-}" == "--validate-only" ]]; then
    validate_only=true
fi

echo "═══════════════════════════════════════════════════"
echo "  terraform-aws-boid Canon Seeder"
echo "═══════════════════════════════════════════════════"

# Step 1: Validate all JSON files
echo ""
echo "Validating Canon JSON files..."
errors=0
for f in "$CANON_DIR"/*.json; do
    if jq . "$f" > /dev/null 2>&1; then
        echo "  ✓ $(basename "$f") — valid JSON"
    else
        echo "  ✗ $(basename "$f") — INVALID JSON"
        errors=$((errors + 1))
    fi
done

if [[ $errors -gt 0 ]]; then
    echo ""
    echo "ERROR: $errors file(s) have invalid JSON. Fix before seeding."
    exit 1
fi

# Step 2: Report entry counts
echo ""
echo "Entry counts:"
echo "─────────────────────────────────────────────────"

count_array() {
    local file="$1" key="$2"
    jq ".$key | length" "$file" 2>/dev/null || echo 0
}

sigs=$(count_array "$CANON_DIR/error-signatures.json" "signatures")
limits=$(count_array "$CANON_DIR/aws-limits.json" "limits")
eval_order=$(count_array "$CANON_DIR/iam-eval-rules.json" "evaluation_order")
interactions=$(count_array "$CANON_DIR/iam-eval-rules.json" "interaction_rules")
patterns=$(count_array "$CANON_DIR/sg-interactions.json" "patterns")
compat=$(count_array "$CANON_DIR/provider-compat.json" "compatibility")

printf "  %-30s %4s  (target: 50+)\n" "error-signatures.json:" "$sigs"
printf "  %-30s %4s  (target: 30+)\n" "aws-limits.json:" "$limits"
printf "  %-30s %4s  (target: 10+)\n" "iam-eval-rules (eval_order):" "$eval_order"
printf "  %-30s %4s  (target: 8+)\n" "iam-eval-rules (interactions):" "$interactions"
printf "  %-30s %4s  (target: 12+)\n" "sg-interactions.json:" "$patterns"
printf "  %-30s %4s  (target: 12+)\n" "provider-compat.json:" "$compat"
echo "─────────────────────────────────────────────────"

if [[ "$validate_only" == true ]]; then
    echo ""
    echo "Validation-only mode. Done."
    exit 0
fi

# Step 3: Run Python report
echo ""
python3 "$SCRIPT_DIR/canon_lib.py"
echo ""
echo "Done."
