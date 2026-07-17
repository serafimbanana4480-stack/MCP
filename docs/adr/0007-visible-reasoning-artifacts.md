# ADR 0007: Persist visible plans, not hidden chain-of-thought

- Status: Accepted
- Date: 2026-07-16

## Context

ProjectMind needs durable planning, evidence, critiques, and post-mortems. Persisting private hidden reasoning is unnecessary, privacy-sensitive, and cannot be generated honestly by a deterministic local service.

## Decision

Persist only user-visible engineering artifacts: task decomposition, success criteria, concise rationale, evidence, validation status, alternatives, risks, and lessons. Deterministic mode provides templates and factual checks. An optional LLM adapter may enhance visible artifacts and must label the capability mode.

## Consequences

Plans remain auditable and portable without claiming that the server itself is an LLM. `ThoughtStep` is a public plan step, not a hidden internal thought.

