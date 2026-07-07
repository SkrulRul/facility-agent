# Facility Agent API — Functional Specification
*DRAFT — behavior and business rules only. Task breakdown, sequencing, and prioritization are Raúl's to define; not covered here.*

**Domain sources:** LMA (Loan Market Association) market convention. Consulted: LexisNexis (Events of Default), ACT Borrower's Guide to LMA Documentation, Lexology (analysis of "continuing" defaults), Law Insider (real credit agreement clauses) — real legal/financial practice sources, not SEO content. Not legal or financial advice; a simplification for a learning project, not a real contract.

---

## 1. Purpose

An operational system of record for a facility agent administering debt facility agreements on behalf of one or more lenders: agreement terms, repayment tracking, covenant monitoring, default event history.

## 2. Actors

- **Loan Operations Analyst** — creates and maintains agreements, records repayments, covenant test results, and default events. The only actor with write access in v1.
- **Credit Risk Officer** — read-only consumer of covenant/default status for risk decisions. No write behavior defined for this actor in v1.
- No authentication/authorization is implemented in v1 — see §7.

---

## 3. Domain entities and their behavior

### 3.1 Party
Represents a legal entity that can act as borrower, lender, or facility agent across different agreements — **not** embedded in an agreement; referenced by ID, because the same entity can hold different roles in different agreements over time.

**Fields:** `id`, `legal_name`, `role` (`borrower` | `lender` | `facility_agent`), `jurisdiction`, `lei` (optional).

**Behavior:**
- A Party is created independently of any agreement.
- A Party's `role` is a label of intended use, not an access-control mechanism — nothing prevents referencing the same Party ID as both `lender_id` in one agreement and `borrower_id` in another. This is intentional (real entities do play multiple roles across a portfolio), but see the same-agreement self-lending rule below.

### 3.2 FacilityAgreement (aggregate root)
**Fields:** `id`, `agreement_date`, `effective_date`, `maturity_date`, `currency` (ISO 4217), `facility_amount` (`Decimal`), `facility_type` (`term_loan` | `revolving_credit`), `borrower_id`, `lender_ids: list[UUID]`, `facility_agent_id: UUID | None`, `interest_terms`, `repayment_schedule`, `covenants: list[Covenant]`, `default_events: list[DefaultEvent]`, `status`.

**Creation-time validation behavior:**
- `lender_ids` must contain at least one entry.
- If `len(lender_ids) > 1`, `facility_agent_id` must not be null. **Rejected otherwise** — a lender syndicate without a coordinating agent has no operational coordination mechanism; this is a business rule, not a market-standard requirement copied verbatim.
- `borrower_id` must not appear in `lender_ids` — an entity cannot lend to itself within the same agreement.
- `facility_amount` must be strictly positive.
- `agreement_date <= effective_date < maturity_date`. Reject otherwise.
- `currency` must be a valid ISO 4217 code — rejected at shape-validation level (this is a type/format error, not a business error; see §5 on error classification).

### 3.3 Interest terms (discriminated union — analogous to a Kotlin sealed class)
Two variants, discriminated on a `type` field:

- **`fixed`**: `rate_pct: Decimal` (must be positive), `day_count_convention` (`ACT/360` | `ACT/365` | `30/360`).
- **`floating`**: `reference_rate` (`SOFR` | `EURIBOR` | `ESTR`), `margin_pct: Decimal`, `reset_frequency` (`monthly` | `quarterly`), `day_count_convention`.

**Behavior:**
- All rate/margin values are `Decimal`. `float` is never used for money or rates — binary floating-point rounding error on financial quantities is not acceptable at any layer.
- `margin_pct` may be negative (rare but real in aggressive repricing scenarios) — **allowed, not rejected**, but this is a debatable design choice, not settled market fact.
- No external reference-rate feed exists in v1. `reference_rate` is stored as an informational enum only; no live SOFR/EURIBOR value is fetched or resolved.

### 3.4 RepaymentSchedule
Two variants:
- **`bullet`**: implicitly a single installment equal to `facility_amount`, due on `maturity_date`.
- **`amortizing`**: an explicit list of installments, each with `due_date` and `principal_amount`.

**Validation behavior:**
- For `amortizing`: `sum(principal_amount for all installments) == facility_amount`, enforced as a cross-field invariant at the model level (not a per-field constraint — this requires a model-level validator, since it depends on the relationship between multiple fields).
- Installment `due_date` values must be strictly increasing and each `<= maturity_date`. Duplicate dates are rejected.
- The schedule is supplied as input at creation time. **The system does not generate a schedule from tenor/frequency parameters** — this generation behavior is explicitly out of scope for v1 (see §7).
- Partial prepayment outside the defined schedule is **not represented** in v1 — there is no behavior for recording an out-of-schedule repayment event. Explicitly deferred, not silently missing.

### 3.5 Covenant
Two variants:
- **`financial`**: `metric` (`leverage_ratio` | `interest_cover_ratio` | `dscr`), `operator` (`<=`|`>=`|`<`|`>`), `threshold: Decimal`, `test_frequency` (`quarterly` | `annually`).
- **`non_financial`**: `category` (`reporting` | `negative_pledge` | `change_of_control` | `restricted_payments`), free-text `description`.

**Behavior:**
- A covenant is defined once, at agreement creation (or added later — no restriction against adding covenants to an already-`active` agreement).
- A covenant carries **no live pass/fail state of its own**. Compliance state is entirely derived from its history of `CovenantTestResult` records (§3.6) — there is no boolean flag on the covenant that gets flipped.

### 3.6 CovenantTestResult
**Fields:** `covenant_id`, `test_date`, `result` (`pass` | `fail` | `waived`), `tested_by` (identifier of the analyst who recorded it).

**Behavior:**
- Recorded manually by an analyst — there is no automatic evaluation against real financial statements (no financial-data feed exists in v1).
- A covenant accumulates multiple test results over its life. **The covenant's current compliance state is defined as the `result` of its most recent `test_date`** — never a mutable single-value field. This means "is this covenant currently breached" is always a computed read, not a stored value.
- An agreement is considered "in covenant breach" if **any** of its covenants' current compliance state (as defined above) is `fail`. A `waived` result at a later date clears the breach state for that covenant.

### 3.7 DefaultEvent
**Fields:** `event_type` (`payment_default` | `covenant_breach` | `cross_default` | `insolvency` | `misrepresentation` | `change_of_control`), `occurred_date`, `related_covenant_id: UUID | None`, `related_external_reference: str | None`, `remediation_status` (`unremedied` | `remedied`), `waiver_status` (`not_waived` | `waived`).

**Behavior:**
- If `event_type == covenant_breach`, `related_covenant_id` **must** be set — enforced as a conditional validation, not a plain optional field.
- If `event_type == cross_default`, `related_external_reference` may be set as free text describing the external agreement/instrument that triggered it. No integration with external systems exists in v1; this is a manually entered reference.
- **`is_continuing` is a derived value, never stored directly.** Two possible derivation rules exist, and the choice between them is a real, unresolved business decision (not a modeling detail):
  - **Option A** (market majority): `continuing = not (remediation_status == "remedied" OR waiver_status == "waived")`. Remedying the underlying issue alone is enough to clear "continuing" status.
  - **Option B** (more lender-protective): `continuing = not (remediation_status == "remedied" AND waiver_status == "waived")`. Remedy alone is insufficient; an express waiver is required regardless of remediation.
  - **v1 recommendation: Option A**, for lower modeling complexity and because it reflects the dominant market drafting choice — but this must be a decision Raúl makes and records (candidate for its own ADR entry), not an assumption baked in silently.
- `remediation_status` and `waiver_status` transition independently and only ever move forward (`unremedied → remedied`, `not_waived → waived`) — no behavior exists for reverting either status once set.

---

## 4. FacilityAgreement lifecycle behavior

`status` is never directly settable to an arbitrary value — it only changes through the transitions below.

| From | To | Trigger / condition |
|---|---|---|
| `draft` | `active` | Manual analyst action. Requires: `effective_date` not in the future, and a repayment schedule that passes its invariant (§3.4). |
| `active` | `defaulted` | Automatic, derived: at least one `DefaultEvent` exists whose `is_continuing` (§3.7) evaluates true. |
| `active` | `matured` | Automatic, derived: `today >= maturity_date` AND no `DefaultEvent` is currently continuing. |
| any | `terminated` | Manual analyst action (e.g. full early repayment, refinancing). Prepayment mechanics themselves are out of scope (§7); only the resulting terminal state is modeled. |

**Behavior notes:**
- `defaulted` and `matured` are **not** independently settable — they are computed from underlying event/date data. A read of an agreement's status always reflects current derived state, not a value someone could set inconsistently with the underlying events.
- An agreement can move from `defaulted` back to `active` if the condition that made it `defaulted` no longer holds (i.e., no `DefaultEvent` remains continuing) — this follows directly from the derivation rule above, not from a separate manual transition.

---

## 5. API behavior (request/response, error handling)

- **Style:** REST/JSON. Synchronous request/response; no async workflows or webhooks in v1.
- **Error classification — two distinct kinds, not conflated:**
  - **Shape/type errors** (missing fields, wrong types, invalid enum values, malformed currency code): HTTP `422`, produced natively by Pydantic validation.
  - **Business rule violations** (invalid state transition, `borrower_id` in `lender_ids`, principal sum mismatch): HTTP `400` with a structured body — `{"error_code": "...", "message": "...", "field": "..."}`. These are violations Pydantic's shape validation cannot express because they depend on relationships between fields or on stored state, not on a single field's format.
- **Read behavior:** fetching a Facility Agreement returns the full nested structure — interest terms, repayment schedule, covenants (each with its test-result history), default events. No partial/lazy loading behavior defined for v1.
- **List/filter behavior:** listing supports filtering by `status`, `borrower_id`, and a derived `in_covenant_breach` boolean (computed per §3.6, not stored). All list endpoints are paginated (`limit`/`offset`) regardless of expected data volume.
- **Not-found behavior:** requesting a non-existent ID returns `404` uniformly across resource types.

---

## 6. Non-functional behavior

- **Monetary precision:** every amount, rate, and threshold is `Decimal`. No `float` anywhere in the money/rate path.
- **Auditability:** every mutation that records a judgment call (`tested_by` on covenant test results; creation/modification timestamps on any mutable record) is attributed and timestamped. A financial system of record without this trail is not defensible.
- **No authentication/authorization** in v1 — a deliberate, documented omission, not a silent gap.
- **No performance requirement** — this is a low-volume portfolio project; behavior should not be shaped by hypothetical scale it will never see.

---

## 7. Explicitly out of scope for v1

- Guarantors as a modeled party type.
- Automatic repayment schedule generation from tenor/frequency.
- Partial/out-of-schedule prepayment recording.
- Automatic covenant evaluation against real financial statements (no financial-data feed).
- Live reference-rate resolution (SOFR/EURIBOR/ESTR values).
- Invoices (per ADR-001).
- Authentication/authorization.

---
*Open decision requiring Raúl's explicit resolution before Phase 1 modeling proceeds: §3.7 Option A vs Option B for `is_continuing`. This is the single business decision with the most downstream modeling impact in this document.*
