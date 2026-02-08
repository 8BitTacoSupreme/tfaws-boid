# terraform-aws-boid Development Plan

## Current Phase: 5 — E2E Validation & Polish

## North Star
A developer runs `flox activate -r floxhub/terraform-aws` and gets an
expert Terraform+AWS agent with zero setup. The agent validates its
suggestions against LocalStack before presenting them. Over time, the
agent learns the user's conventions and infrastructure quirks.

## Key Milestones
- [x] Phase 1: Foundation (Flox env, SQLite schema, activation hooks, LocalStack)
- [x] Phase 2: Canon Population (50 error sigs, 35 AWS limits, 10+8 IAM rules, 15 SG patterns, 15 compat entries)
- [x] Phase 3: CLI Tools (plan analyzer, Canon search, enhanced validate.sh)
- [x] Phase 4: Memories Integration (write/read path, conventions, fork)
- [x] Phase 5: E2E Validation (5 demo scenarios, README, test-boid.sh)

## Phase 1 Deliverables (Complete)
- `memory/schema.sql` — 5 tables: fixes, conventions, quirks, sessions, metadata
- `canon/*.json` — 5 schema-defined Canon files with `_meta` headers
- `scripts/on-activate.sh` — Initializes DB, validates Canon, records session
- `scripts/on-deactivate.sh` — Checkpoints session, WAL truncate
- `scripts/init-memory.sh` — Manual DB init/reset tool
- `sandbox/localstack-compose.yml` — Podman-compose for LocalStack with health check
- `sandbox/validate.sh` — Lint + security scan + plan validation pipeline
- `boid-claude.md` — Mission template (Tier 3) for shipped boid

## Phase 2 Deliverables (Complete)
- `canon/error-signatures.json` — 50 entries from 3 channels (GitHub issues, CHANGELOG, tribal knowledge)
- `canon/aws-limits.json` — 35 entries across 15 LocalStack services
- `canon/iam-eval-rules.json` — 10 evaluation order steps + 8 interaction rules
- `canon/sg-interactions.json` — 15 security group interaction patterns
- `canon/provider-compat.json` — 15 entries covering TF 1.5-1.8 × AWS provider 4.x-6.x + OpenTofu
- `scripts/canon_lib.py` — Shared Python lib for Canon JSON ops
- `scripts/seed-*.py` — 5 seeder scripts (one per Canon file)
- `scripts/seed-canon.sh` — Orchestrator for validation and reporting
- `tests/canon/test_canon_retrieval.py` — 42 tests across 6 test classes
- `tests/canon/test_data/sample_errors.json` — 15 real errors + 5 negative cases
- `scripts/test-canon.sh` — Test runner
- `docs/ARCHITECTURE.md` — Canon storage format + retrieval strategy decisions

## Phase 3 Deliverables (Complete)
- `mcp/README.md` — terraform-mcp-server evaluation + gap analysis (keeps registry server, no custom MCP)
- `scripts/canon_lib.py` — Added `match_error()`, `search_by_resource()`, `search_by_tags()` search functions
- `scripts/canon_search.py` — Canon search CLI (--error, --resource, --tags → JSON output)
- `scripts/tf_plan_analyzer.py` — Plan JSON → Canon cross-reference analyzer (plan_summary, canon_findings, diagnostic_matches, limit_warnings, compat_warnings)
- `sandbox/validate.sh` — Enhanced with --plan-json, --analyze, --apply, --destroy flags
- `tests/phase3/test_integration.py` — 24 integration tests (TestCanonSearch, TestPlanAnalyzer, TestCanonLibSearchFunctions, TestIntegrationPipeline)
- `tests/phase3/fixtures/sg-cycle/` — Terraform fixture with intentional SG cycle
- `tests/phase3/fixtures/mock-plan.json` — Mock terraform plan JSON for analyzer testing
- `docs/ARCHITECTURE.md` — ADR: CLI Tools Over Custom MCP Servers

## Phase 4 Deliverables (Complete)
- `memory/schema.sql` — v2 schema: session_id FKs on fixes/conventions/quirks, distinct_sessions on conventions, new indexes, schema_version=2
- `memory/migrate_v1_to_v2.sql` — ALTER TABLE migration script from v1 to v2
- `scripts/memory_lib.py` — Memories CRUD library: record_fix, record_convention, record_quirk, lookup_fix, lookup_conventions, lookup_quirks, reinforce_convention, contradict_convention, effective_confidence, query_with_priority, export_for_fork
- `scripts/fork-memory.sh` — Shell wrapper for fork export (--scope team|org, --output path)
- `scripts/on-activate.sh` — Added migration detection block (v1 → v2 auto-migrate)
- `tests/memory/test_memories.py` — 52 tests across 8 classes (TestSchemaV2, TestRecordFix, TestRecordConvention, TestRecordQuirk, TestConfidenceModel, TestReadPriority, TestForkExport, TestMigration)
- `docs/ARCHITECTURE.md` — 3 ADRs: Memory Write Triggers, Read Priority, Session-Weighted Confidence Model

## Phase 5 Deliverables (Complete)
- `README.md` — User-facing getting-started guide with quickstart, architecture, how-it-learns, sandbox, canon stats, and roadmap
- `tests/e2e/fixtures/vpc/` — 3-AZ VPC demo with main.tf, providers.tf, plan.json (triggers SG cycle, VPC/EIP limits)
- `tests/e2e/fixtures/ecs/` — ECS Fargate demo with main.tf, providers.tf, plan.json (triggers steady state timeout, ALB 2-AZ requirement)
- `tests/e2e/test_e2e.py` — 23 E2E tests: TestVPCScenario (8), TestECSScenario (6), TestNamingPersistence (5), TestForkE2E (4)
- `scripts/test-boid.sh` — Top-level test orchestrator: 141 total tests (42 Canon + 24 Phase 3 + 52 Memory + 23 E2E)
- `.claude/settings.json` — Fixed MCP SQLite path: dev.db → boid.db
- Scenario 4 (layer swap) documented as roadmap item — building a second boid is out of scope for PoC

## Next: Phase 6 Roadmap
1. Layer swap — Activate domain overlays (e.g., terraform-datadog) that extend Canon
2. Semantic search — Upgrade Canon retrieval from regex to vector similarity
3. FloxHub publish — Package and publish for `flox activate -r` distribution
