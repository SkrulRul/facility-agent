# CLAUDE.md
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                  # install all dependency groups (dev + test)
uv run fastapi dev       # start dev server with auto-reload (http://127.0.0.1:8000)
uv run poe test          # run all tests
uv run poe lint          # ruff check
uv run poe format        # ruff format
uv run poe typecheck     # mypy + pyright (both must pass)
uv run poe check         # lint + typecheck + test (full CI gate)
```

Run a single test file or test by name:
```bash
uv run pytest tests/test_health.py
uv run pytest -k "test_health_returns_ok"
```

## Architecture

Entry point: `app/main.py` exports the `app` FastAPI instance. FastAPI's auto-discovery (`fastapi dev`) finds it there.

Tests use `fastapi.testclient.TestClient` (backed by `httpx2`) — no running server needed.

Type checking is **strict** via both mypy and pyright. All production code in `app/` must be fully annotated; `tests/` relaxes `disallow_untyped_defs`.

Active ruff rule sets: `FAST, ANN, E, F, I, UP, B, SIM` — annotations required on all public functions (`ANN`).

---

## Domain Layer — Conventions and Restrictions

### Module structure

All domain models live in `app/domain.py` (single file, dependency-ordered top-to-bottom).

**Why single file:** The domain uses discriminated union members (`InterestTerms`, `RepaymentSchedule`, `Covenant`) that reference each other and the aggregate root. A single file eliminates circular-import risk entirely and makes dependency ordering trivial. Pydantic v2 forward references resolve via `from __future__ import annotations` at the top.

**When to split:** If the domain grows beyond ~15 types, split into `app/domain/` package with careful import ordering in `__init__.py`. Document the split decision as an ADR.

### Layering

```
app/domain.py       ← domain models (Pydantic BaseModel, pure Python)
app/services/       ← service layer (Phase 2+): orchestrates domain, owns transitions
app/repositories/   ← repository layer (Phase 2+): in-memory stores, later persistence
app/routers/        ← FastAPI routes (Phase 2+): HTTP interface, calls services
```

Dependencies flow **inward only**: routers → services → domain. Domain models have no imports from services, repositories, or routers.

### Per-layer restrictions

**Domain layer (`app/domain.py`):**
- Claude must not add service logic (loading, saving, orchestrating transitions) to domain models.
- No `float` anywhere. All monetary amounts, rates, margins, thresholds use `Decimal`. A `float` annotation is a type-checking defect.
- Derived state (e.g. `status`, `is_continuing`, `is_in_covenant_breach`) stays as `@computed_field` — never stored as a plain field that could become inconsistent.
- Business-rule violations raise `ValueError` inside `@model_validator` — Pydantic wraps these into `ValidationError`, FastAPI returns HTTP 422.
- No database imports, no HTTP client imports, no external I/O.

**Service layer (Phase 2+):**
- Owns forward-only state transitions (`draft → active → terminated`). Domain models provide `activate()` / `terminate()` as transition helpers; the service enforces preconditions before calling them.
- No direct Pydantic `model_validate` calls on raw dicts from HTTP — that belongs in the router layer.

**Repository layer (Phase 2+):**
- In-memory storage only for this project (explicitly out of scope: SQLAlchemy, database, persistence). See PRD §7.
- Repositories return domain model instances, not dicts or ORM objects.

### Error type policy

| Source | Mechanism | HTTP response |
|---|---|---|
| Shape / type error (wrong field type, missing required field, bad enum value) | Pydantic `ValidationError` | 422 Unprocessable Entity |
| Business-rule violation (`@model_validator` raises `ValueError`) | Pydantic `ValidationError` | 422 Unprocessable Entity |
| Not found | Service raises (Phase 2) | 404 Not Found |
| Conflict / forbidden transition | Service raises (Phase 2) | 409 Conflict |

Note: PRD §5 distinguishes shape errors (400) from business-rule errors (422). The current policy maps both to 422 via Pydantic's default FastAPI integration. This will be refined in the API phase.

### Naming conventions

- Models: `PascalCase` (`FacilityAgreement`, `DefaultEvent`)
- Fields: `snake_case` (`facility_amount`, `borrower_id`)
- Discriminator field: always named `type` with a `Literal` value (`type: Literal["fixed"]`)
- Type aliases: `PascalCase` (`AgreementStatus`, `Currency`, `InterestTerms`)
- Private attrs: single leading underscore (`_base_status`)
- Transition methods: imperative verb (`activate()`, `terminate()`)
- Validators: leading underscore + descriptive name (`_validate_agreement`)

### Pydantic v2 patterns used in this project

- `ConfigDict(frozen=True, strict=True)` — value objects (cannot be mutated after construction, no type coercion)
- `ConfigDict(strict=True)` — aggregate root (`FacilityAgreement`, mutable via transition methods)
- `ConfigDict(strict=True, validate_assignment=True)` — `DefaultEvent` (mutable; model_validator re-runs on field assignment)
- `@computed_field @property` — derived fields serialized in model output (decorator order: `@computed_field` first, then `@property`)
- `Annotated[A | B, Field(discriminator="type")]` — discriminated union pattern
- `PrivateAttr` — internal state not exposed in serialization (`_base_status`)

---

## Architecture Decision Records

### ADR-002 — `is_continuing` uses Option A

**Decision:** `DefaultEvent.is_continuing` = `not (remediation_status == "remedied" or waiver_status == "waived")`. Either remedy OR waiver clears the default.

**Drivers:** PRD-recommended; simpler than Option B (AND logic); dominant LMA market drafting convention.

**Alternatives:** Option B — both remedy AND waiver required to clear. Rejected: stricter than market convention, no second consumer today.

**Consequences:** A waiver alone (without formal remediation) clears `is_continuing`. Appropriate for LMA market drafting; document if requirements differ.

---

### ADR-003 — `FacilityAgreement.status` uses `_base_status` + `@computed_field` overlay (Option A)

**Decision:** `_base_status: PrivateAttr` stores `Literal["draft","active","terminated"]`. `status` computed field overlays `"defaulted"` (any continuing default event) and `"matured"` (`maturity_date < date.today()`). Defaulted takes priority over matured.

**Drivers:** Mixed lifecycle: `draft → active → terminated` are manual transitions; `defaulted` and `matured` are derived from events and dates. Can't model all five states as purely computed without injection.

**Alternatives:** Option C — module-level `compute_agreement_status()` function (present in codebase as a contrast pattern; `status` delegates to it).

**Consequences:** `status` cannot be set to `"defaulted"` or `"matured"` from outside the model. `_base_status` accepts only `draft/active/terminated`. `matured` uses `date.today()` — Phase 2 tests freeze time with `freezegun`.

---

### ADR-004 — `CovenantTestResult` referenced on `FacilityAgreement`, not embedded in `Covenant`

**Decision:** `FacilityAgreement.covenant_test_results: list[CovenantTestResult]`, each with `covenant_id: UUID`. Compliance derived via `is_in_covenant_breach` computed field.

**Drivers:** PRD field naming (`covenant_id`) implies separate storage. Cleaner for future normalization. `Covenant` has no stored pass/fail state (PRD §3.5).

**Alternatives:** Embed test results in `Covenant`. Rejected: couples the value object to mutable test history; harder to normalize.

**Consequences:** `is_in_covenant_breach` iterates `covenant_test_results` keyed by `covenant_id`, returning the latest result per covenant. Same-date ties: strictly-later semantics (`test_date >` previous), so a same-date pass does not clear a same-date fail (to be reviewed when result recording is implemented in Phase 2).

---

### ADR-005 — No pytest in Phase 1

**Decision:** Phase 1 exit gate is `uv run poe typecheck` (mypy strict + pyright strict) and `uv run poe lint` only. No pytest.

**Drivers:** Tests are the Phase 2 learning focus. Phase 1 focuses on Pydantic v2 model patterns.

**Alternatives:** Add validator tests in Phase 1. Rejected: scope boundary deliberate. Note: the type checker verifies structural correctness only — behavioral correctness of `@model_validator` runtime logic is the Phase 2 pytest scope.

**Consequences:** ~10 runtime validators are structurally sound but behaviorally unverified until Phase 2.

---

### ADR-006 — CLAUDE.md v1: comprehensive layering doc

**Decision:** CLAUDE.md includes full domain/service/repository boundary intent, per-layer Claude restrictions, naming conventions, and error type policy.

**Drivers:** Phase 1 training objective: Claude drafts layering constraints that will govern all subsequent phases.

**Consequences:** This section grows as each phase is implemented. Service-layer and repository-layer restrictions are intentionally forward-looking stubs; fill in during Phase 2 implementation.

---

### ADR-007 — Single `app/domain.py` (no package split)

**Decision:** All domain models in one file, dependency-ordered top-to-bottom.

**Drivers:** 9 model types, one developer, no existing circular-import pressure. Forward refs resolved by `from __future__ import annotations`.

**Alternatives:** `app/domain/` package with one file per entity/group. Rejected: real circular-import risk between union members and aggregate root; premature for current scope.

**Consequences:** File is ~290 lines. Revisit if domain exceeds ~15 types or multiple developers contend on the file.

---

### ADR-008 — Business-rule validation in Pydantic models → HTTP 422

**Decision:** All field and cross-field business-rule checks live in `@model_validator` or `@field_validator` in the domain layer. Violations raise `ValueError`; Pydantic wraps to `ValidationError`; FastAPI returns HTTP 422.

**Drivers:** Keeps validation co-located with the model it protects. Consistent with PRD §5 "shape/type errors are 422."

**Alternatives:** Service-layer validation returning HTTP 400. Deferred: the 400 vs 422 split for intentional business rejections vs malformed input will be refined in the API phase.

**Consequences:** Current policy: all domain violations are 422. The PRD §5 distinction (shape error = 400, business rule = 422) is a follow-up for the API phase.

---

### ADR-009 — `DefaultEvent` is mutable (`validate_assignment=True`)

**Decision:** `DefaultEvent.model_config = ConfigDict(strict=True, validate_assignment=True)`. NOT frozen. `remediation_status` and `waiver_status` are updated in-place. `is_continuing` recomputes on access.

**Drivers:** A default event's remediation and waiver status change after the event is recorded. Frozen would prevent this.

**Alternatives:** Immutable event log with new entries for each status change. Rejected: over-engineered for Phase 1 scope; no second consumer.

**Consequences:** Forward-only transition enforcement (e.g., `outstanding → remedied` only) is a service-layer concern (Phase 2). The domain model allows direct field assignment — the service layer guards the sequence. Pydantic's `@field_validator` with `validate_assignment=True` does not receive the previous value, so direction enforcement cannot be expressed as a domain validator; the service layer checks `if event.remediation_status == "remedied": raise` before any write. If stronger domain-level guarding is needed, the pattern from `FacilityAgreement` (`PrivateAttr` + named transition methods) can be applied to `DefaultEvent` in Phase 2.

---

### ADR-010 — Audit timestamps in model layer

**Decision:** `FacilityAgreement.created_at: datetime` and `DefaultEvent.recorded_at: datetime` required at construction time. PRD §6 audit trail requirement.

**Drivers:** PRD §6 requires an audit trail for all domain events.

**Alternatives:** Add timestamps in the service layer. Rejected: moves a model-level invariant out of the model.

**Consequences:** Both fields are required (no default). Caller supplies the timestamp. Phase 2 tests may use `datetime.now(UTC)` or a fixed datetime for reproducibility.

---

### ADR-011 — `matured` status uses `date.today()`

**Decision:** `compute_agreement_status()` compares `agreement.maturity_date <= date.today()`. Not injected.

**Drivers:** Simplicity. `date.today()` is a side effect, not a dependency we need to swap for this project.

**Alternatives:** Inject a clock. Rejected: YAGNI; one consumer.

**Consequences:** Phase 2 tests that exercise `matured` status must freeze time using `freezegun` (`@freeze_time("2030-01-01")`). Document in test file when first used.

---

### ADR-012 — `Literal` enums for all bounded domain strings

**Decision:** Every string field with a finite set of valid values uses `Literal[...]` instead of `str`. Applied to: `day_count_convention` (both interest terms), `reference_rate`, `reset_frequency`, `financial_metric`, `FinancialCovenant.operator`, `FinancialCovenant.frequency`, `NonFinancialCovenant.category`, `DefaultEvent.event_type`, `FacilityAgreement.facility_type`.

**Drivers:** Consistency with how `Currency`, `AgreementStatus`, `Party.role`, and all discriminator `type` fields are already typed. Under `strict=True`, a `str` field accepts any string — `FloatingInterestTerms(reference_rate="banana")` would pass all static and runtime checks. `Literal` gives invalid-value rejection at the shape-validation level (HTTP 422) with zero additional code.

**Alternatives:** `str` + `@field_validator` — runtime-only, loses static exhaustiveness, duplicates the constraint. `Enum` class — more verbose, no added value for pure-string labels with one consumer. Both rejected: YAGNI.

**Consequences:** Adding a new valid value (new reference rate, new event type) is a one-line Literal change. `FinancialCovenant.operator` is stored as informational metadata — no auto-evaluation of threshold conditions occurs in v1 (test results are manually recorded by analysts per §3.6); the field is available for UI display and future auto-evaluation.
