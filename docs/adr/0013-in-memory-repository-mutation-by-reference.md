# ADR-0013 — In-memory repository persists by mutation-by-reference (no `update`/`save`)

**Status:** Accepted

## Decision

`AgreementRepository` exposes only `add`, `get`, and `list_all` — no `update` or `save` method. `FacilityAgreement` is frozen at the top level (`ConfigDict(frozen=True)`, `app/domain.py`), but its list fields (`covenant_test_results`, `default_events`) are ordinary mutable Python lists. The in-memory repository stores object references, not copies, so appending to a list on an agreement fetched via `repository.get(id)` **is** the persistence write — no explicit save call is needed or exists.

## Drivers

- YAGNI — no second repository implementation exists today to justify an `update` method whose only job would be a no-op passthrough.

## Alternatives Considered

- An explicit no-op `save(agreement)` method to preserve the repository seam for future real persistence. Considered seriously (the spec anticipates Phase 5 wrapping this service layer) but rejected for now per the project's stated rule requiring two concrete consumers before adding speculative methods.

## Consequences

- This is an implicit contract, not enforced by the Protocol's type signature.
- If Phase 5+ (or any future phase) introduces a real store (e.g. a database-backed repository) that returns copies instead of references, every `record_*` write in the service layer will silently stop persisting with no test failure signal, because the current pytest suite tests behavior through the same in-memory repository instance.
- FastAPI runs sync handlers in a threadpool, so concurrent appends to the shared singleton's mutable lists are not atomic-safe — accepted because [`docs/PRD.md` §6](../PRD.md#6-non-functional-behavior) explicitly states there is no performance requirement for this project; revisit if concurrent write load is ever a real scenario.
