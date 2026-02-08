# TODO — terraform-aws-boid

## Phase 1: Foundation
- [x] Initialize Flox environment with manifest.toml
- [x] Design and implement SQLite schema for Memories (memory/schema.sql)
- [x] Write activation hooks (scripts/on-activate.sh, scripts/on-deactivate.sh)
- [x] Create Canon JSON schemas (5 files in canon/)
- [x] Set up LocalStack sandbox (sandbox/localstack-compose.yml, sandbox/validate.sh)
- [x] Write boid-claude.md (Mission template for end users)
- [x] Create scripts/init-memory.sh
- [x] Configure MCP servers in .claude/settings.json

## Phase 2: Canon Population
- [x] Research and compile error-signatures.json (50 entries from 3 channels)
- [x] Research and compile aws-limits.json (35 entries across 15 services)
- [x] Research and compile provider-compat.json (15 entries: TF 1.5-1.8 × AWS 4.x-6.x)
- [x] Research and compile iam-eval-rules.json (10 eval_order + 8 interaction_rules)
- [x] Research and compile sg-interactions.json (15 patterns)
- [x] Write Canon retrieval tests (42 tests across 6 test classes)

## Phase 3: MCP Servers → CLI Tools
- [x] Evaluate terraform-mcp-server — documented in mcp/README.md
- [x] Build CLI tools instead of custom MCP servers (ADR in ARCHITECTURE.md)
- [x] Promote match_error + add search_by_resource, search_by_tags to canon_lib.py
- [x] Build scripts/canon_search.py — Canon search CLI
- [x] Build scripts/tf_plan_analyzer.py — plan JSON → Canon cross-reference
- [x] Enhance sandbox/validate.sh — --plan-json, --analyze, --apply, --destroy
- [x] Integration test: plan JSON → analyzer → Canon matches (24 tests)

## Phase 4: Memories Integration
- [x] Implement memory write path (validated fix → SQLite)
- [x] Implement memory read path (error → Memories → Canon fallback)
- [x] Implement convention learning (correction → convention entry)
- [x] Implement scope tagging and fork filtering
- [x] Write Memories test suite (52 tests across 8 test classes)
- [x] Schema migration v1 → v2 (session_id FKs, distinct_sessions, indexes)
- [x] Session-weighted confidence model
- [x] Fork export script (scripts/fork-memory.sh)

## Phase 5: E2E Validation & Polish
- [x] Write README.md (quickstart, architecture, how-it-learns, sandbox, canon stats, roadmap)
- [x] Demo scenario 1: VPC + subnets + NAT (fixture + 8 E2E tests)
- [x] Demo scenario 2: ECS Fargate service (fixture + 6 E2E tests)
- [x] Demo scenario 3: Naming correction persists across sessions (5 E2E tests)
- [x] Demo scenario 4: Layer swap — documented as roadmap item in README and PLAN.md
- [x] Demo scenario 5: Fork with team-scoped Memories (4 E2E tests)
- [x] Write scripts/test-boid.sh (top-level test orchestrator, 141 total tests)
- [x] Fix MCP settings: dev.db → boid.db in .claude/settings.json
- [ ] Publish to FloxHub
