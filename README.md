# terraform-aws-boid

A Flox Agentic Environment that gives any AI coding agent expert Terraform+AWS knowledge — out of the box, and growing with use.

## Quickstart

```bash
flox activate -r 8BitTacoSupreme/tfaws-boid
claude
# That's it. The boid skill is auto-linked, Canon is loaded, Memories persist locally.
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

## What Happens on Activate

When you run `flox activate`, the environment automatically:

1. **Links the boid skill** — Symlinks `SKILL.md` into `.claude/skills/tfaws-boid/` so Claude Code discovers it as a slash command (`/tfaws-boid`)
2. **Deploys MCP servers** — Copies `settings.json` into `.claude/` with three pre-configured MCP servers (Terraform Registry, SQLite, Fetch). Merges additively with existing settings — never clobbers.
3. **Initializes Memories** — Creates `memory/boid.db` from the shipped schema on first activate. Subsequent activates skip this step.
4. **Runs schema migrations** — Detects schema version and applies migrations if needed (e.g., v1 → v2 session tracking).
5. **Validates Canon** — Checks that all 5 Canon JSON files are present and reports the count.
6. **Starts session tracking** — Generates a UUID session ID, records it in the Memories DB for confidence scoring across sessions.
7. **Exports environment** — Sets `BOID_HOME`, `BOID_CANON_DIR`, `BOID_MEMORY_DB`, `BOID_SESSION_ID` for scripts and the agent to use.

No manual configuration required. Run `flox activate` and `claude` — the agent is primed.

## What Claude Sees

After activation, Claude Code has access to:

| Category | What's Available |
|----------|-----------------|
| **Skill** | `SKILL.md` — the full Terraform+AWS agent playbook (Tier 3 Mission template) |
| **MCP: terraform-mcp-server** | Terraform Registry lookups — provider docs, resource schemas, module search |
| **MCP: sqlite** | Structured Memories queries — read/write to `memory/boid.db` |
| **MCP: fetch** | HTTP fetching for pulling external documentation |
| **Shell tools** | `terraform`, `tflint`, `tfsec`, `infracost`, `localstack`, `aws`, `sqlite3`, `jq`, `yq` |
| **Python scripts** | `canon_search.py`, `tf_plan_analyzer.py`, `memory_lib.py` |
| **Environment vars** | `BOID_HOME`, `BOID_CANON_DIR`, `BOID_MEMORY_DB`, `BOID_SESSION_ID` |

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

### Tier 3: Mission (SKILL.md + your CLAUDE.md)
Active project context. The boid ships `SKILL.md` as a Claude Code skill — it's auto-linked on activate and provides the agent's Terraform+AWS playbook. You add your own `CLAUDE.md` in your project for per-project architecture rules, constraints, and plans.

**Why three tiers?**
- Canon + Memories prevent context drift — stable upstream truth + persistent local knowledge
- Memories + Mission prevent over-fitting — evidence-based learning + current scope constraints

For architecture decision records, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## How It Works

```
                        flox activate -r 8BitTacoSupreme/tfaws-boid
                                          │
                ┌─────────────────────────────────────────────────┐
                │              Nix Store ($FLOX_ENV)              │
                │                                                 │
                │  Packages: terraform, tflint, tfsec, infracost, │
                │  localstack, aws-cli, sqlite3, python3,         │
                │  claude-code, nodejs                             │
                │                                                 │
                │  tfaws-boid package:                             │
                │  $FLOX_ENV/share/                                │
                │  ├── claude/                                     │
                │  │   ├── skills/tfaws-boid/SKILL.md  (Tier 3)   │
                │  │   └── settings.json               (MCP cfg)  │
                │  └── boid/                                       │
                │      ├── canon/*.json  (5 files)     (Tier 1)   │
                │      ├── scripts/*.py  (4 files)                │
                │      ├── memory/schema.sql           (Tier 2)   │
                │      └── sandbox/validate.sh                    │
                └────────────────────┬────────────────────────────┘
                                     │
                               on-activate
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              Symlink skill    Deploy settings   Init Memories DB
              into .claude/    .json (merge)     + migrate + session
                    │                │                │
                    ▼                ▼                ▼
                ┌─────────────────────────────────────────────────┐
                │           Your Project Directory                │
                │                                                 │
                │  .claude/skills/tfaws-boid/ → (Nix store link)  │
                │  .claude/settings.json      ← (merged MCP cfg)  │
                │  memory/boid.db             ← (Tier 2, local)   │
                │  CLAUDE.md                  ← (your Tier 3)     │
                └────────────────────┬────────────────────────────┘
                                     │
                                   claude
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
                SKILL.md         3 MCP servers    Shell tools
               (auto-loaded     (sqlite, fetch,  (terraform, tflint,
                as skill)        terraform)       tfsec, infracost...)
                    │                │                │
                    └────────┬───────┘                │
                             ▼                        │
                ┌─────────────────────┐               │
                │   Agent Context     │◄──────────────┘
                │                     │
                │  Tier 3: SKILL.md   │  ← in context window
                │  + your CLAUDE.md   │
                │                     │
                │  Tier 1: Canon      │  ← via scripts/MCP
                │  Tier 2: Memories   │  ← via scripts/MCP
                └─────────────────────┘
```

## Using with Claude Code

The boid ships with Claude Code. Activate and go:

```bash
# From any project directory:
flox activate -r 8BitTacoSupreme/tfaws-boid
claude
# That's it. The boid skill is auto-linked, Canon is loaded, Memories persist locally.
```

Once Claude is running, just ask:

```
> I need a 3-AZ VPC with private subnets, NAT gateway, and an EKS cluster
```

The agent has the skill, the Canon, the linters, and the sandbox tools — it knows what to do.

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

## Sandbox Validation (Optional)

If you have Podman running, you can start a LocalStack sandbox for local plan/apply testing:

```bash
# Start LocalStack (requires Podman)
podman-compose -f sandbox/localstack-compose.yml up -d

# Validate a Terraform config
sandbox/validate.sh path/to/your/tf-dir --analyze

# Full pipeline: lint + security scan + plan + Canon analysis
sandbox/validate.sh tests/e2e/fixtures/vpc/ --plan-json --analyze
```

This is not required for normal use. The Canon, linters, and plan analyzer all work without LocalStack.

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

## License

MIT
