# Architecture Decision Record

Decisions are recorded as they are made during development.

---

## Decision: Canon Storage Format
**Date:** 2026-02-07
**Status:** Decided
**Context:** Phase 2 requires choosing how Canon data is stored and indexed. The corpus is small (~150 entries across 5 files) and must be fully testable without external services.
**Options considered:**
- Option A: Raw JSON + regex/substring matching — Simple, testable, no dependencies. In-memory search is fast at this scale. Full stdlib compatibility.
- Option B: Embedded vector DB (ChromaDB/LanceDB) — Semantic search, better for fuzzy matching. But adds pip dependencies, complexity, and is harder to test deterministically.
- Option C: SQLite-vec — Combines structured queries with vector search. Good future path but requires the sqlite-vec extension and embedding generation.
**Decision:** Raw JSON + regex/substring matching for Phase 2. The corpus is small enough that in-memory search is instant. Regex patterns provide deterministic, testable matching. ChromaDB/LanceDB remain in the Flox manifest for a future upgrade if retrieval tests reveal gaps in regex matching.
**Consequences:** Canon files are plain JSON, readable by any tool. Retrieval is regex-first (error_pattern field), with structured field filtering (resource, provider, tags) as secondary. No semantic search means exact error messages work great, but paraphrased descriptions won't match. This is acceptable because Canon targets machine-generated error messages, not human descriptions.

---

## Decision: Canon Retrieval Strategy
**Date:** 2026-02-07
**Status:** Decided
**Context:** How the boid agent looks up Canon entries when encountering an error or needing knowledge.
**Options considered:**
- Option A: Regex match on error_pattern first, structured field filter second — Fast, deterministic, good for exact error messages.
- Option B: Semantic similarity search — Better for paraphrased or partial errors. Requires embeddings and a vector store.
- Option C: Hybrid (regex first, semantic fallback) — Best retrieval quality. Most complex.
**Decision:** Regex match on error_pattern first, with structured field filtering (resource, provider, tags) as secondary filters. No semantic search in Phase 2.
**Consequences:** The retrieval path is: (1) regex match error text against error_pattern fields, (2) filter by resource type if known, (3) filter by tags for topical queries. This covers the primary use case (agent encounters error → finds root cause). Semantic search can be layered on later without changing the Canon data format.

---

## Decision: CLI Tools Over Custom MCP Servers
**Date:** 2026-02-08
**Status:** Decided
**Context:** Phase 3 requires integrating Canon lookups into the terraform plan/validate/apply pipeline. The original plan called for custom MCP servers: `terraform-plan-mcp` (plan parser, state reader) and `localstack-mcp` (provision, teardown, validate).
**Options considered:**
- Option A: Custom MCP servers (TypeScript/Go) — Full protocol compliance, discoverable via `.claude/settings.json`, consistent with `terraform-mcp-server`. But: adds Node.js/Go build step, protocol overhead for what are essentially CLI calls, debugging indirection, and zero new capability since the agent already has bash access to `terraform`, `python3`, and every Flox tool.
- Option B: Python CLI tools + enhanced shell script — `tf_plan_analyzer.py` (reads plan JSON, cross-references Canon), `canon_search.py` (thin argparse wrapper around canon_lib), enhanced `validate.sh` (new flags for JSON plan, analysis, apply, destroy). Directly callable via bash, testable with unittest, no protocol overhead.
- Option C: Hybrid — MCP wrappers around the CLI tools. Maximum discoverability but pointless indirection.
**Decision:** Option B — Python CLI tools + enhanced shell script. MCP servers add value when the agent lacks a capability (e.g., `terraform-mcp-server` provides Registry API access). For plan parsing and Canon search, the agent already has the tools — wrapping them in MCP adds complexity with zero new capability.
**Consequences:** The `mcp/` directory contains only a README documenting the `terraform-mcp-server` evaluation and gap analysis. No custom MCP servers to build or maintain. The agent calls `python3 scripts/tf_plan_analyzer.py` and `python3 scripts/canon_search.py` via bash. The `terraform-mcp-server` (registry) remains the only MCP server, providing the one capability the agent doesn't have natively.

---

## Decision: Memory Write Triggers
**Date:** 2026-02-08
**Status:** Decided
**Context:** Phase 4 requires defining when and how earned knowledge is written to the Memories SQLite database (Tier 2). The system needs clear trigger points that tie entries to session provenance.
**Options considered:**
- Option A: Implicit writes — agent automatically records every fix and correction without user involvement. Generates high volume of potentially low-quality entries.
- Option B: Explicit confirmation — require user confirmation before every write. High friction, low adoption.
- Option C: Three-trigger model — specific trigger points tied to distinct user actions (correction, sandbox validation, quirk discovery), each writing to the appropriate table with session provenance.
**Decision:** Option C — Three concrete trigger points, each tied to the current `BOID_SESSION_ID`:
- User corrects agent output (naming, structure, tagging) → `conventions` table, `source='correction'`, confidence starts at 0.5
- Agent validates fix in sandbox + user confirms → `fixes` table, `validated=1` on insert
- Agent encounters quirk not in Canon → `quirks` table with service, region, description
If a matching entry already exists (same `error_hash` for fixes, same `category+pattern` for conventions), the system updates rather than duplicates: bumps `hit_count` or `confidence`, updates `updated_at`, tracks new `session_id` for session spread.
**Consequences:** Write volume stays manageable because each trigger requires a distinct user action or sandbox result. Session tracking enables the confidence model to distinguish single-session flukes from battle-tested knowledge.

---

## Decision: Read Priority — Canon vs Memories
**Date:** 2026-02-08
**Status:** Decided
**Context:** When the agent encounters an error, it must decide which knowledge source to trust — the upstream Canon (Tier 1) or locally-earned Memories (Tier 2). A naive "Memories always wins" approach would let a single casual correction override vetted upstream knowledge.
**Options considered:**
- Option A: Memories always override Canon — Simple but dangerous. One bad correction trumps expert-curated knowledge.
- Option B: Canon always wins — Safe but defeats the purpose of learning. Local knowledge never takes precedence.
- Option C: Scope-aware merge with confidence thresholds — team/org-scoped entries always override (these represent deliberate team decisions); personal entries override only when sufficiently validated.
**Decision:** Option C — Scope-aware merge with explicit override metadata:
1. Query Canon first via `canon_lib.match_error()` / `search_by_resource()` / `search_by_tags()`
2. Query Memories second via `memory_lib.lookup_fix()` / `lookup_conventions()`
3. Merge with scope-aware override rules:
   - **team or org-scoped** Memory entry → ALWAYS overrides Canon (inserted at front of results)
   - **personal-scoped fix** → overrides Canon only if `validated=1`
   - **personal-scoped convention** → overrides Canon only if `effective_confidence >= 0.8`
Each merged result carries explicit `source`, `overrides_canon`, and `override_reason` fields so the agent reads top-to-bottom and trusts the first match.
**Consequences:** The merge is unambiguous and auditable. Personal knowledge earns its way to override status through validation or multi-session reinforcement. Team/org decisions are respected immediately. The `query_with_priority()` function in `memory_lib.py` implements this as the single entry point for combined queries.

---

## Decision: Session-Weighted Confidence Model
**Date:** 2026-02-08
**Status:** Decided
**Context:** Conventions learned from user corrections need a confidence score that distinguishes "learned yesterday in one conversation" from "battle-tested over weeks." Raw confidence alone doesn't capture temporal spread.
**Options considered:**
- Option A: Simple counter — just count how many times a convention was reinforced. Doesn't distinguish 10 reinforcements in one session from 10 across many sessions.
- Option B: Time-based decay — confidence decays over time unless reinforced. Adds complexity (needs periodic updates) and punishes stable conventions.
- Option C: Session-weighted model — raw confidence tracks reinforcement, but effective confidence factors in how many distinct sessions have confirmed the convention. A single-session ceiling prevents premature trust.
**Decision:** Option C — Session-weighted confidence with these constants:
- `CONFIDENCE_BASE = 0.5` (initial on first correction)
- `CORRECTION_DELTA = +0.2` (re-correction of existing)
- `REINFORCE_DELTA = +0.1` (successful use)
- `CONTRADICTION_RESET = 0.3` (user contradicts)
- `SINGLE_SESSION_CEILING = 0.7` (max when `distinct_sessions=1`)
- `SESSION_BONUS_PER = 0.05` per additional session, capped at `SESSION_BONUS_CAP = 0.2`
Effective confidence = `min(raw + session_bonus, 1.0)`, capped at 0.7 for single-session conventions.
**Consequences:** A convention at raw 0.7 in 1 session has effective confidence 0.7 (below the 0.8 Canon override threshold). The same convention confirmed across 5 sessions: effective = 0.7 + 0.2 = 0.9 (overrides Canon). This mechanic ensures the boid trusts its own experience only after that experience is validated across multiple working sessions.
