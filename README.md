# ProjectMind MCP

ProjectMind is a local-first Model Context Protocol server that builds a persistent
architectural graph, keeps provenance-aware engineering memory, retrieves bounded
project context, and exposes structured planning and safety workflows.

The repository is under active v1 implementation. The executable scope and verified
phase gates live in [`TODO.md`](TODO.md); material decisions live in [`docs/adr`](docs/adr).

## Design invariants

- Source code stays local unless an external provider is explicitly configured.
- Source-file mutations use a durable propose → confirm → apply protocol.
- Retrieval remains useful without embeddings or network access.
- Every factual result carries provenance and, where meaningful, confidence.
- `stdio` is the universal transport; Streamable HTTP is the modern remote transport.

## Development quick start

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev,parsing,dashboard]"
projectmind init
projectmind index
projectmind status
projectmind serve --stdio
```

On Windows, activate `.venv\\Scripts\\python.exe` instead of `.venv/bin/python`.

The published package exposes both `projectmind` (canonical) and a compatibility
`projectmind-mcp` console entry point. For isolated execution with uv:

```bash
uvx --from projectmind-mcp projectmind serve --stdio
```

## Status

This is currently an alpha package (`0.1.0`). Do not infer completion from a scaffold:
check the acceptance evidence in `TODO.md` and the test suite.

