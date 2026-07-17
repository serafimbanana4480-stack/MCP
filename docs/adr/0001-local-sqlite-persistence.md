# ADR 0001: Local SQLite persistence

- Status: Accepted
- Date: 2026-07-16

## Context

ProjectMind must persist graph, memory, plans, patches, and telemetry without a service dependency, while remaining portable across MCP hosts and operating systems.

## Decision

Use one project-local SQLite database behind repository-owned stores. Enable foreign keys, WAL mode where supported, explicit transactions, schema migrations, and JSON text only for bounded list/metadata fields. Keep vector search optional so the deterministic lexical/graph path always works.

## Consequences

Installation and backup remain simple, concurrent readers are inexpensive, and all state can be inspected locally. Writes must be short and serialised. Distributed multi-user persistence is deferred beyond v1.

