# ProjectMind MCP — Execution Checklist

This checklist is the repository source of truth derived from the v1.0 master plan.
Items are checked only after their acceptance criteria have been verified locally.

## Delivery gates

- [x] Master plan converted into an executable checklist.
- [x] Initial architectural decisions recorded before implementation.
- [x] Every completed phase has passing tests and updated documentation.
- [x] Every completed phase is represented in `CHANGELOG.md`.
- [x] Release checklist is closed only from reproducible evidence.

## Phase 0 — Foundation (P0, blocking)

- [x] Package scaffold and `pyproject.toml`.
- [x] Official MCP SDK server with `stdio` and current HTTP transport.
- [x] Validated `.projectmind/config.toml` with safe defaults.
- [x] Typed `ping` tool and MCP handshake integration test.
- [x] Cline, Cursor, Claude Desktop, and Claude Code integration guides.
- [x] CI for lint, type-check, tests, and package build.

Acceptance gate: a real SDK client lists/calls `ping`; local quality suite passes.

## Phase 1 — Indexing and graph (P0)

- [x] Extensible Python/JS/TS/Go/Rust/Java parsing pipeline.
- [x] Monorepo/workspace detection.
- [x] Files, symbols, imports, routes, tests, and ORM relation extraction.
- [x] SQLite graph store and idempotent graph builder.
- [x] Incremental reindexing/watch support.
- [x] Symbol-aware Git diff intelligence.
- [x] MCP tools: `index_scope`, `reindex_on_git_pull`, `get_graph_summary`.
- [x] Mermaid export baseline.

Acceptance gate: mixed-language monorepo fixture indexes correctly; incremental benchmark and diagram test pass.

## Phase 2 — Advanced graph analysis (P1)

- [x] PageRank/centrality and critical-file ranking.
- [x] Complete dependency-cycle reporting.
- [x] God-class, tight-coupling, and shotgun-surgery heuristics.
- [x] Refactoring suggestions and single/parallel impact analysis.

Acceptance gate: known cycle and god-class fixtures are detected.

## Phase 3 — Structured memory (P0/P1)

- [x] Persistent CRUD with provenance, confidence, branch scope, and soft supersession.
- [x] Decision, learning, search, feedback, and verification tools.
- [x] Deterministic local consolidation with optional LLM adapter boundary.
- [x] JSON/SQLite export and safe import.
- [x] Confidence ageing.

Acceptance gate: restart persistence, traceable consolidation, and export/import round-trip pass.

## Phase 4 — Hybrid retrieval (P0/P1)

- [x] Validated weighted scoring with graceful semantic fallback.
- [x] Hierarchical file/chunk/symbol context assembly.
- [x] Cache with content-aware invalidation.
- [x] `exploratory`, `surgical`, and `debug` context modes.
- [x] Provenance and token-budget enforcement.

Acceptance gate: surgical context is under 30% of exploratory volume in the fixture; cache-hit scenario passes.

## Phase 5 — Structured reasoning (P0)

- [x] Persistent sequential plans and step validation.
- [x] Bounded ReAct state machine.
- [x] Alternative exploration and justified ranking.
- [x] Four-perspective critique, reflection, devil's advocate, and confidence scoring.
- [x] Similar-solution search and post-mortem memory.

Acceptance gate: generated steps have verifiable criteria; at least three distinct alternatives are ranked.

## Phase 6 — Planning and execution (P1)

- [x] Hierarchical plans, risk matrix, and implementation comparison.
- [x] Crash-safe long-running task checkpoints and post-mortem gate.
- [x] Convention-aware boilerplate proposal.

Acceptance gate: interrupted task resumes from persisted state; comparison schema is stable.

## Phase 7 — Debugging and quality (P1)

- [x] Related-bug lookup and graph-backed root-cause analysis.
- [x] Prioritised hypothesis loop and reproduction proposal.
- [x] Linter/mutation bridges and related-test regression analysis.

Acceptance gate: fixture stack trace resolves to the known culprit; proposed regression test demonstrates the fix lifecycle.

## Phase 8 — Security and execution UX (P0, transversal)

- [x] Durable `propose_edit` → explicit `confirm_and_apply` workflow.
- [x] Root-confined, allowlisted subprocess execution with mandatory confirmation.
- [x] Optional no-network Docker boundary.
- [x] Secret and OWASP-pattern scanners.
- [x] Architecture test prevents direct project writes outside execution boundaries.

Acceptance gate: traversal/stale patch/malicious command cases are blocked and audited.

## Phase 9 — Integrations and collaboration (P2)

- [x] Mermaid, PlantUML, and DOT exports.
- [ ] Internal MCP composition adapter boundary.
- [ ] Read-only dashboard API and minimal browser UI.
- [ ] Authenticated read-only team snapshot sharing.

Acceptance gate: all diagram formats validate; dashboard exposes graph and memory search.

## Phase 10 — Differentiators (P2/P3)

- [x] Telemetry-driven self-improvement report (recommendations only).
- [ ] Provider-neutral model-routing suggestions.
- [ ] Static hot-path analysis.
- [x] Documentation update proposals.
- [x] In-memory change simulation with no filesystem writes.

Acceptance gate: simulated change is side-effect-free; report yields three actionable suggestions from fixture telemetry.

## Phase 11 — CLI and operations (P1, transversal)

- [x] `init`, `serve`, `index`, `reindex`, `status`, `doctor`, config validation.
- [x] Memory search/export/import commands.
- [x] Graph impact/cycles/export commands.
- [x] Dashboard launcher and telemetry summary.
- [x] Windows, macOS, and Linux package entry points.

Acceptance gate: `status` and `doctor` work without a running MCP server and diagnose three common faults.

## Release v1.0.0

- [x] Core coverage is at least 80%.
- [x] Ruff and strict type-check pass.
- [x] Wheel and source distribution build reproducibly.
- [x] At least five ADRs document material decisions.
- [x] Tool reference is generated from Pydantic JSON schemas.
- [ ] Manual host smoke-test matrix is recorded.
- [x] Optional dashboard is functional.
- [x] No external data transfer occurs without explicit provider configuration.
- [ ] `pipx` installation is verified; Node wrapper is documented/tested.

