# ADR-0005 — No pytest in Phase 1

**Status:** Accepted

## Decision

Phase 1 exit gate is `uv run poe typecheck` (mypy strict + pyright strict) and `uv run poe lint` only. No pytest.

## Drivers

- Tests are the Phase 2 learning focus.
- Phase 1 focuses on Pydantic v2 model patterns.

## Alternatives Considered

- Add validator tests in Phase 1. Rejected: scope boundary deliberate.
- Note: the type checker verifies structural correctness only — behavioral correctness of `@model_validator` runtime logic is the Phase 2 pytest scope.

## Consequences

- ~10 runtime validators are structurally sound but behaviorally unverified until Phase 2.
