# Architecture

ProjectMind is a modular monolith. One process serves MCP and one SQLite database under
`.projectmind/` stores project-local state. CLI and optional dashboard adapters call the same
services as MCP; business services do not depend on the protocol SDK.

## Dependency direction

```text
MCP / CLI / dashboard
        ↓
composition root (`AppContext`)
        ↓
indexing · graph · memory · retrieval · reasoning · planning · quality
        ↓
SQLite repositories and optional provider adapters

source mutation ──→ execution boundary only
```

The graph uses stable IDs derived from relative path, node kind, and qualified name. Edges point
from caller/importer/test to callee/imported/target, so impact analysis traverses predecessors.
Unresolved external targets retain a textual reference and confidence/provenance.

Retrieval calculates all available local signals, redistributes unavailable semantic weight, and
returns component scores plus source hashes. Its cache is keyed by project revision and query
parameters, making invalidation deterministic.

Project source changes are immutable proposals stored with an expiry, base hash, and review
digest. Application rechecks all three and writes atomically. ProjectMind's own SQLite state and
explicit `.projectmind` initialization are reversible internal state, not source mutations.

See [`docs/adr`](adr/) for the decisions and [`TODO.md`](../TODO.md) for acceptance gates.

