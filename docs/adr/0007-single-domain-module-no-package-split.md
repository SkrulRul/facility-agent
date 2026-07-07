# ADR-0007 — Single `app/domain.py` (no package split)

**Status:** Accepted

## Decision

All domain models in one file, dependency-ordered top-to-bottom.

## Drivers

- 9 model types, one developer, no existing circular-import pressure.
- Forward refs resolved by `from __future__ import annotations`.

## Alternatives Considered

- `app/domain/` package with one file per entity/group. Rejected: real circular-import risk between union members and the aggregate root; premature for current scope.

## Consequences

- File is ~290 lines. Revisit if the domain exceeds ~15 types or multiple developers contend on the file.
