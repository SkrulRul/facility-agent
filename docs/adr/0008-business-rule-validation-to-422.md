# ADR-0008 — Business-rule validation in Pydantic models → HTTP 422

**Status:** Accepted

## Decision

All field and cross-field business-rule checks live in `@model_validator` or `@field_validator` in the domain layer. Violations raise `ValueError`; Pydantic wraps to `ValidationError`; FastAPI returns HTTP 422.

## Drivers

- Keeps validation co-located with the model it protects.
- Consistent with [PRD §5](../PRD.md#5-api-behavior-requestresponse-error-handling) "shape/type errors are 422."

## Alternatives Considered

- Service-layer validation returning HTTP 400. Deferred: the 400 vs 422 split for intentional business rejections vs malformed input is refined per-phase (see Phase 2 spec, which explicitly locks all-422 for its scope).

## Consequences

- Current policy: all domain violations are 422.
- The PRD §5 distinction (shape error = 400, business rule = 422) remains a follow-up, re-evaluated each phase rather than resolved outright.
