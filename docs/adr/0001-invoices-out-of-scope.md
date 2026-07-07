# ADR-0001 — Invoices out of scope for v1

**Status:** Accepted

## Decision

Invoices are not modeled as a domain entity in v1. `FacilityAgreement` tracks the facility itself (terms, covenants, defaults) but not invoicing/billing records.

## Drivers

- [PRD §7](../PRD.md#7-explicitly-out-of-scope-for-v1) explicitly excludes invoices.
- Invoicing is a distinct domain (billing/accounts-receivable) from debt facility administration; conflating them would blur the aggregate root's responsibility.

## Alternatives Considered

- Model a minimal `Invoice` entity referencing `FacilityAgreement`. Rejected: no consumer or requirement drives it in v1; would be speculative scope.

## Consequences

- No `Invoice` model exists in `app/domain.py`.
- Adding invoicing later requires a new ADR superseding this one, plus a PRD update.
