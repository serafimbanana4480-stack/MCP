# ADR 0003: Capability-based mutation boundary

- Status: Accepted
- Date: 2026-07-16

## Context

The strongest product invariant is that generated code changes are reviewable and cannot be applied by surprise.

## Decision

Domain tools may create immutable patch proposals but cannot write target project files. Only the execution package may apply a stored proposal, and only with an exact patch id, explicit confirmation, unchanged base digest, and root-confined paths. Command execution likewise requires explicit confirmation, an allowlisted executable, a fixed project working directory, timeout, and bounded output.

## Consequences

Mutation paths are auditable and testable. Some workflows require an extra client round trip by design. Generated exports and ProjectMind's own internal database are classified separately as reversible local state and are still root-confined.

