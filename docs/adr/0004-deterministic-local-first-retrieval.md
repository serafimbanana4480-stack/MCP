# ADR 0004: Deterministic local-first retrieval

- Status: Accepted
- Date: 2026-07-16

## Context

Retrieval must remain useful when an embedding model, native SQLite extension, network, or external provider is unavailable.

## Decision

Always compute graph, lexical, recency, architectural, coverage, and feedback signals locally. Semantic similarity is an adapter-provided optional signal whose unavailable weight is redistributed across available signals before normalisation. Every result includes component scores and provenance.

## Consequences

Fresh installs work offline and ranking remains explainable. Semantic quality may be lower until a provider is configured, but failure is graceful and observable.

