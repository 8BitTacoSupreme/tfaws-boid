# terraform-aws-boid

A Flox Agentic Environment that gives any AI coding agent expert Terraform+AWS knowledge — out of the box, and growing with use.

## Quickstart

```bash
flox activate -r 8BitTacoSupreme/tfaws-boid
# That's it. Your agent has Canon knowledge + Memories + sandbox.
```

## What You Get

When you activate the boid, your AI agent gains:

| Tool | What It Does |
|------|-------------|
| `terraform` | Infrastructure as Code — plan, validate, apply |
| `tflint` | Terraform linter — catches common mistakes before plan |
| `tfsec` | Security scanner — flags IAM, encryption, and network issues |
| `infracost` | Cost estimation — shows $/month impact before you apply |
| `localstack` | Local AWS sandbox — validate plans without touching real AWS |
| `canon_search.py` | Search 133 curated Terraform+AWS pitfalls, limits, and patterns |
| `tf_plan_analyzer.py` | Cross-reference any plan JSON against Canon knowledge |
| `memory_lib.py` | Persistent memory — fixes, conventions, and quirks that grow with use |

## Try It: VPC Review

Use the included VPC demo fixture to see Canon in action. No LocalStack required.

```bash
# Activate the environment
flox activate

# Analyze the demo VPC plan
python3 scripts/tf_plan_analyzer.py tests/e2e/fixtures/vpc/plan.json --format text
```

You'll see the analyzer flag:
- **Inline security group rules** — Canon knows this causes dependency cycles
- **VPC limit warning** — 5 VPCs per region default
- **EIP limit warning** — 3 NAT gateways = 3 of your 5 default EIPs

The VPC fixture (`tests/e2e/fixtures/vpc/main.tf`) is a realistic 3-AZ VPC with public/private subnets, NAT gateways, and an intentional pitfall: inline SG ingress rules that trigger the Canon's SG cycle pattern.

```bash
# Search Canon directly
python3 scripts/canon_search.py --resource aws_security_group
python3 scripts/canon_search.py --error "Cycle: aws_security_group"
```

## Architecture: Three Knowledge Tiers

The boid organizes knowledge into three tiers that solve different problems:

### Tier 1: Canon (Read-Only, Upstream)
Curated Terraform+AWS knowledge that ships with the boid. Error signatures mapped to root causes, AWS service limits, IAM evaluation rules, security group interaction patterns, and provider version compatibility. Updated upstream by the maintainer — you never edit this directly.

### Tier 2: Memories (SQLite, Local)
Earned knowledge that persists across sessions. Validated fixes, naming conventions, infrastructure quirks. Created on first `flox activate`, grows with use. Each entry has a `scope` tag (personal, team, org) that controls what propagates when you fork.

### Tier 3: Mission (CLAUDE.md + docs/)
Active project context. Architecture rules, constraints, current plans. This is the only tier that occupies the LLM context window directly.

**Why three tiers?**
- Canon + Memories prevent context drift — stable upstream truth + persistent local knowledge
- Memories + Mission prevent over-fitting — evidence-based learning + current scope constraints

For architecture decision records, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## How It Learns

The boid's Memories tier uses a session-weighted confidence model:

1. **Record** — You correct the agent's naming: "we use kebab-case for S3 buckets." The convention is stored with confidence = 0.5 and distinct_sessions = 1.
2. **Reinforce** — Next session, the same correction is reinforced. Confidence rises to 0.6, distinct_sessions = 2.
3. **Override** — After 3 sessions of reinforcement: confidence = 0.7, distinct_sessions = 3, effective_confidence = 0.7 + (3-1) * 0.05 = 0.8. At 0.8+, the convention overrides Canon defaults.

The model prevents single-session flukes from dominating. A convention must be reinforced across multiple sessions to earn override authority.

```
effective_confidence = min(raw_confidence + session_bonus, 1.0)
session_bonus = min((distinct_sessions - 1) * 0.05, 0.2)
single_session_ceiling = 0.7
```

The machinery is proven across 52 tests. The seasoning happens through real use — corrections compound over sessions, not minutes.

## Sandbox Validation

Start LocalStack for plan/apply testing:

```bash
# Start the sandbox
podman-compose -f sandbox/localstack-compose.yml up -d

# Validate a Terraform config against LocalStack
sandbox/validate.sh path/to/your/tf-dir --analyze

# Full pipeline: lint + security scan + plan + Canon analysis
sandbox/validate.sh tests/e2e/fixtures/vpc/ --plan-json --analyze

# Apply after validation
sandbox/validate.sh path/to/your/tf-dir --apply

# Clean up
sandbox/validate.sh path/to/your/tf-dir --destroy
```

The validation pipeline runs tflint, tfsec, terraform plan, and Canon analysis in sequence. No suggestion should reach the user without passing through it.

## Forking & Sharing

Export team/org-scoped knowledge for sharing:

```bash
# Export team + org scoped Memories (excludes personal entries)
scripts/fork-memory.sh --scope team --output memory/boid-fork.db

# Export org-only entries
scripts/fork-memory.sh --scope org --output memory/boid-org.db
```

The forked database strips session provenance and resets distinct_sessions to 1. Personal entries never leave your machine. Team members import the fork and their reinforcements build new session history.

## What's Inside (Canon Stats)

| Canon File | Entries | Coverage |
|------------|---------|----------|
| `error-signatures.json` | 50 | Error pattern → root cause → fix mappings |
| `aws-limits.json` | 35 | Service quotas across 15 AWS services |
| `iam-eval-rules.json` | 18 | 10 evaluation order steps + 8 interaction rules |
| `sg-interactions.json` | 15 | Security group dependency and cycle patterns |
| `provider-compat.json` | 15 | Terraform 1.5-1.8 x AWS provider 4.x-6.x compatibility |

Total: **133 curated entries** covering the sharp edges that trip up Terraform+AWS users.

## Running Tests

```bash
# Run all tests
scripts/test-boid.sh

# Run individual suites
python3 -m unittest discover tests/canon/ -v      # 42 Canon retrieval tests
python3 -m unittest discover tests/phase3/ -v      # 24 integration tests
python3 -m unittest discover tests/memory/ -v      # 52 Memories tests
python3 -m unittest discover tests/e2e/ -v         # E2E scenario tests
```

## Roadmap

- **Layer swap** — Activate domain overlays (e.g., `terraform-datadog`) that extend the Canon with vendor-specific knowledge without replacing the base AWS boid
- **Semantic search** — Upgrade Canon retrieval from regex matching to vector similarity for fuzzy error matching
- **FloxHub publish** — Package and publish to FloxHub for `flox activate -r` distribution

## License

MIT
