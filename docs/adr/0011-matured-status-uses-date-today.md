# ADR-0011 — `matured` status uses `date.today()`

**Status:** Accepted

## Decision

`compute_agreement_status()` compares `agreement.maturity_date <= date.today()`. Not injected.

## Drivers

- Simplicity. `date.today()` is a side effect, not a dependency that needs to be swapped for this project.

## Alternatives Considered

- Inject a clock. Rejected: YAGNI; one consumer.

## Consequences

- Tests that exercise `matured` status must freeze time using `freezegun` (`@freeze_time("2030-01-01")`).
