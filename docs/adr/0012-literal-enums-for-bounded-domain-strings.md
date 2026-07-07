# ADR-0012 — `Literal` enums for all bounded domain strings

**Status:** Accepted

## Decision

Every string field with a finite set of valid values uses `Literal[...]` instead of `str`. Applied to: `day_count_convention` (both interest terms), `reference_rate`, `reset_frequency`, `financial_metric`, `FinancialCovenant.operator`, `FinancialCovenant.frequency`, `NonFinancialCovenant.category`, `DefaultEvent.event_type`, `FacilityAgreement.facility_type`.

## Drivers

- Consistency with how `Currency`, `AgreementStatus`, `Party.role`, and all discriminator `type` fields are already typed.
- Under `strict=True`, a `str` field accepts any string — `FloatingInterestTerms(reference_rate="banana")` would pass all static and runtime checks. `Literal` gives invalid-value rejection at the shape-validation level (HTTP 422) with zero additional code.

## Alternatives Considered

- `str` + `@field_validator` — runtime-only, loses static exhaustiveness, duplicates the constraint.
- `Enum` class — more verbose, no added value for pure-string labels with one consumer.
- Both rejected: YAGNI.

## Consequences

- Adding a new valid value (new reference rate, new event type) is a one-line `Literal` change.
- `FinancialCovenant.operator` is stored as informational metadata — no auto-evaluation of threshold conditions occurs in v1 (test results are manually recorded by analysts per PRD §3.6); the field is available for UI display and future auto-evaluation.
