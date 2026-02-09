#!/usr/bin/env bash
# Validate a Terraform configuration against LocalStack sandbox.
#
# Usage: sandbox/validate.sh <path-to-tf-dir> [flags]
#
# Flags:
#   --plan-json   Output plan as JSON (terraform show -json)
#   --analyze     Run plan JSON through tf_plan_analyzer.py (implies --plan-json)
#   --apply       Apply the plan after successful validation
#   --destroy     Destroy resources instead of planning
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TF_DIR="${1:?Usage: validate.sh <path-to-terraform-dir> [--plan-json] [--analyze] [--apply] [--destroy]}"
shift

# Parse flags
PLAN_JSON=false
ANALYZE=false
APPLY=false
DESTROY=false

for arg in "$@"; do
    case "${arg}" in
        --plan-json) PLAN_JSON=true ;;
        --analyze)   ANALYZE=true; PLAN_JSON=true ;;
        --apply)     APPLY=true ;;
        --destroy)   DESTROY=true ;;
        *) echo "Unknown flag: ${arg}"; exit 1 ;;
    esac
done

LOCALSTACK_URL="${LOCALSTACK_URL:-http://localhost:4566}"

# --- Check LocalStack is running ---
if ! curl -sf "${LOCALSTACK_URL}/_localstack/health" > /dev/null 2>&1; then
    echo "ERROR: LocalStack is not running at ${LOCALSTACK_URL}"
    echo "Start it with: podman-compose -f sandbox/localstack-compose.yml up -d"
    exit 1
fi
echo "[validate] LocalStack is healthy"

# --- Check LocalStack tier and warn about limitations ---
check_localstack_tier() {
    local info_response
    info_response=$(curl -sf "${LOCALSTACK_URL}/_localstack/info" 2>/dev/null || echo '{}')
    local tier
    tier=$(echo "$info_response" | jq -r '.edition // "community"')

    echo "[validate] LocalStack edition: ${tier}"

    if [[ "$tier" == "community" ]]; then
        echo "[validate] WARNING: LocalStack Community (free) tier detected"
        echo "[validate]   - EKS not supported: use enable_eks=false"
        echo "[validate]   - EIP DescribeAddressesAttribute not implemented: use enable_nat_gateway=false"
        echo "[validate]   - Organizations, ElastiCache, MSK require Pro tier"
        echo "[validate]   See Canon: localstack-limitations.json for full matrix"
    fi
}
check_localstack_tier

# --- Run tflint ---
echo "[validate] Running tflint..."
if tflint --chdir="${TF_DIR}" 2>&1; then
    echo "[validate] tflint: PASS"
else
    echo "[validate] tflint: WARNINGS (see above)"
fi

# --- Run tfsec ---
echo "[validate] Running tfsec..."
if tfsec "${TF_DIR}" --soft-fail 2>&1; then
    echo "[validate] tfsec: PASS"
else
    echo "[validate] tfsec: WARNINGS (see above)"
fi

# --- Run terraform init + plan against LocalStack ---
echo "[validate] Running terraform init..."
(
    cd "${TF_DIR}"

    # Configure AWS provider to use LocalStack
    export AWS_ACCESS_KEY_ID="test"
    export AWS_SECRET_ACCESS_KEY="test"
    export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

    terraform init -input=false -no-color 2>&1

    if ${DESTROY}; then
        echo "[validate] Running terraform destroy..."
        terraform destroy -auto-approve -no-color 2>&1
        echo "[validate] Destroy complete"
        exit 0
    fi

    echo "[validate] Running terraform plan..."
    if ${PLAN_JSON}; then
        terraform plan -input=false -no-color -out=tfplan 2>&1
        echo "[validate] terraform plan: PASS"

        echo "[validate] Generating plan JSON..."
        terraform show -json tfplan > tfplan.json

        if ${ANALYZE}; then
            echo "[validate] Running Canon analysis..."
            python3 "${PROJECT_ROOT}/scripts/tf_plan_analyzer.py" tfplan.json --format text
        else
            cat tfplan.json
        fi

        if ${APPLY}; then
            echo "[validate] Applying plan..."
            terraform apply -auto-approve tfplan 2>&1
            echo "[validate] Apply complete"
        fi

        rm -f tfplan tfplan.json
    else
        if terraform plan -input=false -no-color 2>&1; then
            echo "[validate] terraform plan: PASS"
        else
            echo "[validate] terraform plan: FAIL"
            exit 1
        fi

        if ${APPLY}; then
            echo "[validate] Applying..."
            terraform apply -auto-approve -no-color 2>&1
            echo "[validate] Apply complete"
        fi
    fi
)

echo "[validate] Validation complete"
