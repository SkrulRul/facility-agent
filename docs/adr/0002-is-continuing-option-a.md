# ADR-0002 — `DefaultEvent.is_continuing` uses Option A

**Status:** Accepted

## Decision

`DefaultEvent.is_continuing` = `not (remediation_status == "remedied" or waiver_status == "waived")`. Either remedy OR waiver clears the default.

## Drivers

- PRD-recommended.
- Simpler than Option B (AND logic).
- Dominant LMA market drafting convention.

## Alternatives Considered

- **Option B** — both remedy AND waiver required to clear. Rejected: stricter than market convention, no second consumer today.

## Consequences

- A waiver alone (without formal remediation) clears `is_continuing`. Appropriate for LMA market drafting; document if requirements differ.
