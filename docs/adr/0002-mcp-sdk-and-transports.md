# ADR 0002: Official MCP SDK and transports

- Status: Accepted
- Date: 2026-07-16

## Context

ProjectMind must work with heterogeneous MCP clients. The master plan names stdio and HTTP+SSE, while protocol transports and SDK APIs evolve.

## Decision

Build on the stable v1 line of the official Python MCP SDK, pinned to `mcp>=1.28.1,<2`. Treat stdio as the compatibility baseline and expose Streamable HTTP at `/mcp`, the current transport from MCP specification `2025-11-25`. Do not expose legacy HTTP+SSE unless a concrete host requires it. Revisit SDK v2 only after its stable release because its API is intentionally different.

## Consequences

Protocol framing stays inside the official SDK and the server avoids writing logs to stdout in stdio mode. HTTP binds to loopback by default, validates Host/Origin, and uses a local bearer token. Transport selection is isolated in the CLI so future protocol changes do not leak into domain services.

## References

- [MCP transport specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Official Python SDK v1 documentation](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/README.md)

