# ADR-0006 — CLAUDE.md v1: comprehensive layering doc

**Status:** Accepted

## Decision

CLAUDE.md includes full domain/service/repository boundary intent, per-layer Claude restrictions, naming conventions, and error type policy.

## Drivers

- Phase 1 training objective: Claude drafts layering constraints that will govern all subsequent phases.

## Consequences

- CLAUDE.md's layering section grows as each phase is implemented.
- Service-layer and repository-layer restrictions were intentionally forward-looking stubs in Phase 1; filled in during Phase 2 implementation.
