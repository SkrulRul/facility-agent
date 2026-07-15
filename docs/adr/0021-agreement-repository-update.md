# ADR-0021 — `AgreementRepository.update()`: the ADR-0013 replacement

**Status:** Accepted (supersedes ADR-0013's mutation-by-reference contract)

## Decision

`AgreementRepository` gains a fourth method, `async def update(self, agreement: FacilityAgreement) -> None`, alongside `add`/`get`/`list_all`. `AgreementService.record_covenant_test_result` and `record_default_event` each call `await self._repository.update(agreement)` immediately after mutating the agreement's list fields — this is the explicit, durable-write path that replaces ADR-0013's "the fetched object's reference identity is the persistence write" contract.

`InMemoryAgreementRepository.update()` re-stores the agreement in its dict (`self._store[agreement.id] = agreement`) — not treated as a no-op, so its behavior is uniform and testable alongside the Postgres implementation.

`PostgresAgreementRepository.update()` performs a full-aggregate write: the parent row's scalar/JSONB columns are replaced, and the `covenant_test_results`/`default_events` child-row collections are reassigned (triggering the ORM's `cascade="all, delete-orphan"` to delete stale rows and insert new ones). This entire operation runs inside a single `async with session.begin():` transaction — the parent-row write and the child-row delete/reinsert are atomic with each other; a mid-write failure (e.g. a constraint violation on reinsert) rolls back cleanly rather than orphaning or losing child rows. This is distinct from — and addresses a correctness gap on top of — the concurrency story below, which concerns races *between* two writers, not the atomicity of one writer's own multi-statement write.

## Drivers

- ADR-0013 itself named the exact failure mode this ADR closes, verbatim: "If [a future phase] introduces a real store ... that returns copies instead of references, every `record_*` write in the service layer will silently stop persisting with no test failure signal." `PostgresAgreementRepository.get()` returns a freshly-deserialized object on every call — the reference-identity trick ADR-0013 relied on no longer holds once a second, real backend exists.
- Two concrete consumers now exist for an `update` method (in-memory and Postgres), closing the YAGNI objection ADR-0013 raised against adding one speculatively.

## Alternatives considered

- **Narrow, per-mutation methods** (e.g. `add_covenant_test_result()`, `add_default_event()`) mapping directly to a single child-table `INSERT`, avoiding a full-aggregate read-modify-write. Rejected — more Protocol surface for equivalent effect, and contradicts this project's aggregate-root pattern, where `FacilityAgreement` (not its individual child collections) is the sole unit of consistency the service layer reasons about.
- **Full-aggregate `update()` with optimistic locking** (a version column, checked and incremented on write, raising a conflict error on a stale read). Rejected for this phase — no stated concurrency requirement exists in `docs/PRD.md`; revisit if one appears (see Consequences below).

## Why chosen

Full-aggregate `update()` with no locking is the smallest change that gives the service layer an explicit, testable durable-write call, matches the existing aggregate-root shape of `record_covenant_test_result`/`record_default_event` (fetch the whole agreement, mutate it, persist it), and keeps parity with `InMemoryAgreementRepository`'s existing (already accepted, already documented) non-atomic-write posture from ADR-0013.

## Consequences

- **Concurrent writes are last-write-wins — a deliberate, documented limitation, not an implicit assumption.** Two concurrent requests recording different changes to the same agreement can race: the second `update()` call persists a snapshot read before the first call's write landed, silently dropping the first change. Accepted because `docs/PRD.md` §6 states no concurrency requirement exists (the same rationale ADR-0013 used to accept non-atomic in-memory list appends); revisit if concurrent write load ever becomes a real scenario.
- **In-memory-backend testing cannot prove `update()` is *necessary* by construction.** `InMemoryAgreementRepository.get()` still returns a live object reference, so the service layer's existing in-place list mutation (`agreement.covenant_test_results.append(...)`) is already visible to a subsequent `get()` *before* `update()` is ever called. A future refactor that accidentally deletes the `await self._repository.update(agreement)` call would still pass every in-memory-backed test — this is precisely the failure mode this ADR exists to prevent, and the in-memory backend cannot detect its absence by itself. Two mitigations: (1) `tests/test_agreement_repository.py` includes a `SpyAgreementRepository`-based regression test asserting the service layer's `update()` *call* happens (independent of whether the underlying store's reference semantics would mask a missing call) — verified during implementation by temporarily reverting the `update()` call sites and confirming the test goes red; (2) `scripts/smoke_test_persistence.py` against real Postgres is the only artifact that exercises genuine durable-write behavior end to end (a fresh session's `get()` after a write, proving the data isn't merely an in-process object-reference artifact).
- **`covenant_test_results.covenant_id` has no DB-level foreign key.** Covenants live in the parent `agreements` row's `covenants` JSONB column (ADR-0019/Phase 6 discovery decision), not their own table — so a covenant's `id` is not a real FK target. This is a pre-existing gap, not introduced by this ADR: `covenant_id` was already validated only in the service layer (`AgreementService.record_covenant_test_result`), never DB-enforced, since no database existed before this phase. Documented here as an accepted limitation rather than left implicit.
- **`strict=False` reconstruction is verified, not a residual risk.** `PostgresAgreementRepository`'s domain reconstruction (`FacilityAgreement.model_validate(data, strict=False)`, then `.activate()`/`.terminate()` to restore the `_base_status` `PrivateAttr`) was independently verified during implementation: a round-trip of a `FacilityAgreement` (including nested `FixedInterestTerms`, itself `ConfigDict(frozen=True, strict=True)`) through `model_dump(mode="json")` → `model_validate(strict=False)` correctly coerces JSON-primitive values (e.g. `str` → `Decimal`, `str` → `UUID`) even three levels deep through a `Field(discriminator="type")` union. `frozen=True` does not interfere with validation-time coercion — it only blocks post-construction attribute assignment on declared fields, and `PrivateAttr` mutation via `.activate()`/`.terminate()` is unaffected (this pattern already existed in the codebase before this phase).

## Follow-ups

- If a genuine concurrent-write requirement ever appears, add optimistic locking (a version column on `agreements`, checked and incremented by `update()`, raising a conflict error on mismatch) as a narrow follow-up to this ADR rather than a redesign.
