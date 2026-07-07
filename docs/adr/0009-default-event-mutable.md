# ADR-0009 — `DefaultEvent` is mutable (`validate_assignment=True`)

**Status:** Accepted

## Decision

`DefaultEvent.model_config = ConfigDict(strict=True, validate_assignment=True)`. NOT frozen. `remediation_status` and `waiver_status` are updated in-place. `is_continuing` recomputes on access.

## Drivers

- A default event's remediation and waiver status change after the event is recorded. Frozen would prevent this.

## Alternatives Considered

- Immutable event log with new entries for each status change. Rejected: over-engineered for Phase 1 scope; no second consumer.

## Consequences

- Forward-only transition enforcement (e.g., `outstanding → remedied` only) is a service-layer concern (Phase 2).
- The domain model allows direct field assignment — the service layer guards the sequence.
- Pydantic's `@field_validator` with `validate_assignment=True` does not receive the previous value, so direction enforcement cannot be expressed as a domain validator; the service layer checks `if event.remediation_status == "remedied": raise` before any write.
- If stronger domain-level guarding is needed, the pattern from `FacilityAgreement` (`PrivateAttr` + named transition methods) can be applied to `DefaultEvent` in a later phase.
