# ADR-0010 — Audit timestamps in model layer

**Status:** Accepted

## Decision

`FacilityAgreement.created_at: datetime` and `DefaultEvent.recorded_at: datetime` required at construction time, per [PRD §6](../PRD.md#6-non-functional-behavior) audit trail requirement.

## Drivers

- PRD §6 requires an audit trail for all domain events.

## Alternatives Considered

- Add timestamps in the service layer. Rejected: moves a model-level invariant out of the model.

## Consequences

- Both fields are required (no default). Caller supplies the timestamp.
- Tests that exercise these fields may use `datetime.now(UTC)` or a fixed datetime for reproducibility.
