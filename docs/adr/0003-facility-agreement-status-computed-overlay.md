# ADR-0003 — `FacilityAgreement.status` uses `_base_status` + `@computed_field` overlay (Option A)

**Status:** Accepted

## Decision

`_base_status: PrivateAttr` stores `Literal["draft","active","terminated"]`. `status` computed field overlays `"defaulted"` (any continuing default event) and `"matured"` (`maturity_date < date.today()`). Defaulted takes priority over matured.

## Drivers

- Mixed lifecycle: `draft → active → terminated` are manual transitions; `defaulted` and `matured` are derived from events and dates.
- Can't model all five states as purely computed without injection.

## Alternatives Considered

- **Option C** — module-level `compute_agreement_status()` function (present in codebase as a contrast pattern; `status` delegates to it).

## Consequences

- `status` cannot be set to `"defaulted"` or `"matured"` from outside the model.
- `_base_status` accepts only `draft/active/terminated`.
- `matured` uses `date.today()` — see [ADR-0011](0011-matured-status-uses-date-today.md) for the time-freezing implication on tests.
