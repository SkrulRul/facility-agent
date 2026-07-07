# ADR-0004 — `CovenantTestResult` referenced on `FacilityAgreement`, not embedded in `Covenant`

**Status:** Accepted

## Decision

`FacilityAgreement.covenant_test_results: list[CovenantTestResult]`, each with `covenant_id: UUID`. Compliance derived via `is_in_covenant_breach` computed field.

## Drivers

- PRD field naming (`covenant_id`) implies separate storage.
- Cleaner for future normalization.
- `Covenant` has no stored pass/fail state ([PRD §3.5](../PRD.md#35-covenant)).

## Alternatives Considered

- Embed test results in `Covenant`. Rejected: couples the value object to mutable test history; harder to normalize.

## Consequences

- `is_in_covenant_breach` iterates `covenant_test_results` keyed by `covenant_id`, returning the latest result per covenant.
- Same-date ties: strictly-later semantics (`test_date >` previous), so a same-date pass does not clear a same-date fail (to be reviewed when result recording is implemented in Phase 2).
