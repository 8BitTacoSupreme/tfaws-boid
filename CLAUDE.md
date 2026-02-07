# CLAUDE.md — terraform-aws-boid PoC

## Project Identity

You are building the **terraform-aws-boid**: the first Flox Agentic Environment proof-of-concept. This is a portable, shareable, self-seasoning AI development environment for Terraform + AWS infrastructure work.

**What ships:** A complete Flox environment published to FloxHub that any developer can activate with `flox activate -r floxhub/terraform-aws` and immediately get an expert Terraform+AWS AI agent — sandboxed, constrained, and loaded with domain knowledge.

**This is a meta-project.** You are an AI agent building the packaging and knowledge system for AI agents. Stay aware of that recursion — decisions you make about how the boid works will affect agents like you.

---

## Architecture: The Hybrid Knowledge Architecture

This project implements three knowledge tiers. Understand these deeply — they are the core innovation.

### Tier 1: Canon (Read-Only RAG)
- **Storage:** Versioned vector store, distributed via FloxHub
- **Mutability:** Read-only. Updated upstream by the boid maintainer.
- **Purpose:** Upstream truth — the sharp edges of Terraform + AWS that trip people up
- **Contents:** Error signatures → root causes, IAM policy evaluation rules, provider version compatibility, AWS service limits, security group interaction patterns
- **Anti-pattern:** Do NOT put general Terraform or AWS documentation here. Only encode knowledge that is (a) not obvious from the docs, (b) represents tribal knowledge, or (c) maps errors to root causes.

### Tier 2: Memories (SQLite, Local)
- **Storage:** SQLite database, created on first `flox activate`, persists across sessions
- **Mutability:** Read-write. Grows with use.
- **Purpose:** Earned knowledge — what this specific user/team has learned through experience
- **Contents:** Validated fixes, naming conventions, local infra quirks, error resolution history
- **Key property:** Each entry has a `scope` tag (personal | team | org) that controls what propagates on fork

### Tier 3: Mission (CLAUDE.md + docs/)
- **Storage:** Flat files in the project directory
- **Mutability:** Ephemeral. Per-project.
- **Purpose:** Active context — architecture rules, constraints, current plans for the project at hand
- **Key property:** This is the ONLY tier that occupies the LLM context window directly

### Problem Mapping
- **Canon + Memories prevent context drift.** Stable upstream truth + persistent local knowledge = anchors that don't degrade over time.
- **Memories + Mission prevent over-fitting.** Evidence-based local learning + current scope constraints = agent stays grounded in reality.

---

## Project Structure

```
terraform-aws-boid/
├── .flox/                          # Flox environment definition
│   └── env/
│       ├── manifest.toml           # Package declarations
│       └── hooks/
│           ├── on-activate.sh      # Mount SQLite, start MCP, load Canon
│           └── on-deactivate.sh    # Checkpoint, stop sidecars
├── .claude/                        # Claude Code agent configuration
│   └── settings.json               # MCP server declarations + permissions
├── boid-claude.md                  # The CLAUDE.md that SHIPS with the boid
│                                   #   (the Mission template for end users)
├── docs/                           # Architecture & planning (our Mission)
│   ├── PLAN.md                     # Current development plan + task tracking
│   ├── ARCHITECTURE.md             # System design decisions
│   ├── TODO.md                     # Actionable task list
│   ├── patterns.md                 # Terraform+AWS canonical patterns
│   ├── anti-patterns.md            # Known pitfalls and why they fail
│   └── conventions.md              # Naming, structure, tagging rules
├── canon/                          # Tier 1: The Canon (RAG seed data)
│   ├── error-signatures.json       # Error → root cause mappings
│   ├── aws-limits.json             # Service quotas & gotchas
│   ├── provider-compat.json        # Version compatibility matrix
│   ├── iam-eval-rules.json         # IAM policy evaluation order
│   └── sg-interactions.json        # Security group interaction patterns
├── memory/                         # Tier 2: Memories
│   ├── schema.sql                  # SQLite schema definition
│   └── .gitkeep                    # DB created on first activate
├── mcp/                            # MCP server configs
│   ├── terraform-mcp/              # Terraform plan/state server
│   └── localstack-mcp/             # LocalStack provisioning server
├── sandbox/                        # Sandbox orchestration
│   ├── localstack-compose.yml      # LocalStack docker-compose
│   └── validate.sh                 # Run agent's proposed fix in sandbox
├── scripts/                        # Build and utility scripts
│   ├── seed-canon.sh               # Populate Canon vector store
│   ├── init-memory.sh              # Initialize Memories SQLite
│   └── test-boid.sh                # End-to-end boid validation
├── tests/                          # Validation tests
│   ├── canon/                      # Canon retrieval accuracy tests
│   ├── memory/                     # SQLite CRUD + scope tests
│   └── e2e/                        # Full activate → task → validate tests
└── README.md                       # Usage, examples, contribution guide
```

**IMPORTANT:** This project contains TWO Claude configurations:
1. **This file (CLAUDE.md)** — instructions for YOU, the developer agent building the boid
2. **boid-claude.md** — the Mission template that ships WITH the boid for end users

Do not confuse them. When working on agent behavior for the shipped product, edit `boid-claude.md`. This file governs YOUR behavior during development.

---

## Available Tools & MCP Servers

### Flox Environment (packages available in your shell)
Use these directly. They are your primary tools.

- **terraform** — IaC tool; you'll be writing HCL configs, testing plans, building module patterns
- **aws-cli** — AWS interaction; used against LocalStack for sandbox validation
- **localstack** — Local AWS mock; this IS the sandbox for the Disposable Tool pattern
- **tflint** — Terraform linter; integrate into the validation pipeline
- **tfsec** — Terraform security scanner; part of the validate-before-suggest flow
- **infracost** — Cost estimation; boid should run this before presenting solutions
- **sqlite3** — Direct SQLite access; use for schema development, testing Memories tier
- **jq, yq** — JSON/YAML processing; essential for Canon data preparation
- **curl** — HTTP requests; API testing, fetching upstream data for Canon
- **python3** — Scripting; Canon seeding, data processing, test harness
- **podman** — Container runtime; LocalStack runs in containers
- **shellcheck** — Validate activation hook scripts

### MCP Servers (configured in .claude/settings.json)
These extend your capabilities beyond the shell.

- **filesystem MCP** — Read/write project files with structured access
- **terraform-mcp-server** — Terraform Registry operations: provider docs, module search, resource schemas. This is a community server already installed. Use it for looking up provider capabilities, resource argument references, and seeding the Canon. It does NOT parse plans or inspect state — you will build a lightweight complement for that in Phase 3.
- **sqlite MCP** — Query and manipulate the Memories SQLite database directly; use this for schema iteration, testing memory CRUD operations, and validating scope filtering
- **fetch MCP** — HTTP fetching for pulling upstream documentation to seed the Canon

### What You Should Use When
- **Shell (bash):** Running terraform, localstack, tflint, tfsec, infracost, building/testing
- **Terraform MCP (registry):** Looking up provider docs, resource schemas, module references — use for Canon seeding
- **SQLite MCP:** Schema design, Memories tier testing, scope filtering queries
- **Filesystem MCP:** Structured file reading when you need to analyze large configs
- **Fetch MCP:** Pulling AWS docs, Terraform provider changelogs, GitHub issues for Canon seeding

---

## Development Rules

### Code Standards
- **No pip.** All Python dependencies go through Flox (`flox install python3Packages.foo`). If a package does not exist in Nixpkgs, evaluate alternatives that do. The shipped boid must be fully reproducible with zero pip installs.
- **Shell scripts:** Bash, shellcheck-clean, set -euo pipefail
- **Python:** 3.11+, type hints, no external dependencies unless in manifest.toml
- **HCL (Terraform):** Canonical formatting via `terraform fmt`, modules over monoliths
- **JSON (Canon data):** Validate with jq before committing. Schema-first design.
- **SQL:** SQLite-compatible. Test all queries against the actual schema.

### Documentation Standards
- Every non-trivial decision goes in `docs/ARCHITECTURE.md` with rationale
- Task tracking lives in `docs/TODO.md` — update it as you complete work
- The plan lives in `docs/PLAN.md` — consult it before starting new work
- Canon data files must include a `_meta` field with source, version, and date

### Testing Standards
- Canon: Every error signature must have a test that retrieves it given the error text
- Memories: Full CRUD test suite, scope filtering tests, fork simulation
- E2E: `scripts/test-boid.sh` must pass — activate → task → validate → memory persists
- Sandbox: LocalStack provisioning must succeed for the 5 demo patterns (VPC, ECS, S3, IAM, RDS)

### Git Standards
- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`
- One logical change per commit
- `docs/` changes can be bundled

---

## Development Phases

### Phase 1: Foundation
- [ ] Initialize Flox environment with manifest.toml (all packages)
- [ ] Design and implement SQLite schema for Memories (schema.sql)
- [ ] Write activation hooks (on-activate.sh, on-deactivate.sh)
- [ ] Create Canon JSON schemas (define the shape of each data file)
- [ ] Set up LocalStack sandbox (docker-compose, health check)
- [ ] Write `boid-claude.md` (the Mission template for end users)

### Phase 2: Canon Population
- [ ] Research and compile error-signatures.json (target: 50+ entries)
- [ ] Research and compile aws-limits.json (target: top 30 services)
- [ ] Research and compile provider-compat.json (Terraform 1.5-1.8 × AWS provider 4.x-5.x)
- [ ] Research and compile iam-eval-rules.json (full evaluation order)
- [ ] Research and compile sg-interactions.json (common circular deps)
- [ ] Write Canon retrieval tests

### Phase 3: MCP Servers
- [ ] Evaluate terraform-mcp-server (already installed) — test registry lookups, identify gaps
- [ ] Build terraform-plan-mcp (plan parser, state reader — complements the registry server)
- [ ] Build localstack-mcp (provision, teardown, validate)
- [ ] Configure .claude/settings.json with all MCP declarations
- [ ] Integration test: agent queries registry → generates HCL → parses plan → identifies issue → queries Canon

### Phase 4: Memories Integration
- [ ] Implement memory write path (validated fix → SQLite)
- [ ] Implement memory read path (error → check Memories before Canon)
- [ ] Implement convention learning (correction → convention entry)
- [ ] Implement scope tagging and fork filtering
- [ ] Write Memories test suite

### Phase 5: E2E Validation & Polish
- [ ] Demo scenario 1: VPC + subnets + NAT (Canon-powered, avoids known pitfalls)
- [ ] Demo scenario 2: ECS Fargate service (validates against LocalStack)
- [ ] Demo scenario 3: Naming correction persists across sessions
- [ ] Demo scenario 4: Layer swap (activate terraform-datadog overlay)
- [ ] Demo scenario 5: Fork with team-scoped Memories
- [ ] Write README.md
- [ ] Publish to FloxHub

---

## Key Design Decisions (Record These in ARCHITECTURE.md)

When you encounter a fork in the road, document the decision in `docs/ARCHITECTURE.md` using this format:

```markdown
## Decision: [Title]
**Date:** YYYY-MM-DD
**Status:** Decided | Proposed | Superseded
**Context:** What prompted this decision
**Options considered:** List with pros/cons
**Decision:** What we chose and why
**Consequences:** What this means going forward
```

Decisions to make early:
1. **Canon storage format:** Raw JSON vs. embedded vector DB (ChromaDB, LanceDB, SQLite-vec)?
2. **Canon retrieval:** Exact match on error hash vs. semantic similarity vs. hybrid?
3. **Memory write trigger:** Explicit user confirmation vs. implicit after sandbox validation?
4. **Plan/state MCP language:** Go vs. Python vs. TypeScript for the terraform-plan-mcp complement?
5. **LocalStack lifecycle:** Per-session vs. persistent vs. on-demand?

---

## What NOT to Build

- Do not build a general-purpose AI agent framework. This is one boid for one stack.
- Do not build a custom LLM. We use Claude (or any MCP-compatible model) as-is.
- Do not build a RAG engine from scratch. Use an existing embeddable solution.
- Do not over-engineer the Canon. JSON files with good indexing beat a complex pipeline.
- Do not add packages to the Flox environment that are not needed for Terraform+AWS work. Constraint is the feature.

---

## Communication Style

- When you create or modify a doc in `docs/`, say what changed and why in one line.
- When you complete a phase milestone, update `docs/TODO.md` and `docs/PLAN.md`.
- If you hit an architectural decision point, write the options to `docs/ARCHITECTURE.md` and ask for input before proceeding.
- If a Canon entry requires research you cannot do from available tools, flag it explicitly: "RESEARCH NEEDED: [topic]"
- Prefer working code over perfect plans. Get something running, then iterate.
