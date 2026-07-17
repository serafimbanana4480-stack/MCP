# ADR 0008: Restricted subprocess runner and optional Docker sandbox

- Status: Accepted
- Date: 2026-07-16

## Context

Portable subprocess controls cannot reliably block network access or impose identical resource limits on Windows, macOS, and Linux.

## Decision

Name the default capability a restricted runner: explicit confirmation, argv only, no shell, executable allowlist, root-confined cwd, filtered environment, timeout, and bounded output. Reserve the term sandbox for the optional Docker mode with a pinned image, no network, and explicit mounts.

## Consequences

The product does not overstate subprocess isolation. High-risk commands can require Docker policy, while common local test and lint workflows stay cross-platform.

