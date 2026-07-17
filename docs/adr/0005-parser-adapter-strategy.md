# ADR 0005: Parser adapters with AST fallbacks

- Status: Accepted
- Date: 2026-07-16

## Context

The system targets five language families, but native tree-sitter grammars can be unavailable or difficult to package consistently on every platform.

## Decision

Expose one parser-adapter contract. Prefer tree-sitter adapters when an installed grammar is available; use Python's standard AST for Python and conservative lexical adapters for supported languages as deterministic fallbacks. Store parser provenance and never pretend a fallback relation is high confidence.

## Consequences

Indexing degrades gracefully and remains installable. Advanced extraction accuracy varies by adapter, so fixture tests cover the guaranteed common subset and optional grammar extras can strengthen it.

