# Changelog

All notable changes to ProjectMind MCP are documented here. The project follows Semantic Versioning.

## [1.0.0] - 2025-01-01

### Added

- Full MCP tool catalog (54 tools) registered via the official MCP SDK `FastMCP` server.
- CLI (`projectmind` / `projectmind-mcp`) with `version`, `init`, `index`, `status`, `doctor`, `memory`, `graph`, `dashboard`, and `config` commands.
- Optional no-network Docker sandbox execution boundary (`DockerSandbox`) wired into `safe_subprocess`.
- In-memory change simulation (`ChangeSimulator`) reporting blast radius without filesystem writes.
- Documentation update proposals (`DocsUpdater`) that never write to disk.
- Generated tool reference (`docs/tools_reference.md`) from the live tool catalog.
- Node (`npx`) wrapper (`package.json` + `index.js`) resolving `python`/`uvx`/`pipx`.
- CI workflow (`.github/workflows/ci.yml`) running ruff, mypy, tests with ≥80% coverage, build, and benchmarks across OS/Python matrices.
- Benchmark script (`scripts/benchmark.py`) for indexing, graph, retrieval, and impact analysis.
- Version bump to `1.0.0` and `Development Status :: 5 - Production/Stable`.

### Fixed

- Pre-existing ruff `E501` line-length violations across telemetry, quality, execution, and database modules.
- Pre-existing mypy strict-mode type errors (networkx overrides, unreachable code, `object`→typed casts, `AnyHttpUrl` auth settings, shadowed `context` parameters).
- `ActionRecord` import path corrected to `projectmind.reasoning.react_loop`.
- `consolidate` tool call aligned with `DeterministicConsolidator.consolidate` signature.

## [Unreleased]

### Added

- Executable implementation checklist derived from the v1.0 master plan.
- Initial ADRs for persistence, MCP transports, safe mutation, retrieval, and parser adapters.

