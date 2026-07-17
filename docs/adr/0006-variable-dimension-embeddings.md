# ADR 0006: Provider-qualified variable-dimension embeddings

- Status: Accepted
- Date: 2026-07-16

## Context

The master schema proposed a fixed `FLOAT[768]` vector, while the default MiniLM model has a different dimension and future providers may change dimensions or models.

## Decision

Store embeddings by owner, provider, model, dimension, content hash, and a portable vector blob. Treat `sqlite-vec` as an optional acceleration index rebuilt from those canonical records. Disabled embeddings are the default.

## Consequences

Provider/model changes cannot silently corrupt similarity search. Local lexical and graph retrieval always remains available, while native vector indexing can be added without a schema-breaking fixed dimension.

