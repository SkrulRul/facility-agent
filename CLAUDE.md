# CLAUDE.md
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Related documents:**
- [`docs/PRD.md`](docs/PRD.md) — functional specification (domain entities, API behavior, non-functional requirements)
- [`docs/adr/`](docs/adr/) — Architecture Decision Records (one file per decision, numbered `NNNN-slug.md`)

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

**When to split:** If the domain grows beyond ~15 types, split into `app/domain/` package with careful import ordering in `__init__.py`. Document the split decision as a new file in `docs/adr/`.

### Layering

```
app/domain.py       ← domain models (Pydantic BaseModel, pure Python)
app/services/       ← service layer (Phase 2+): orchestrates domain, owns transitions
app/repositories/   ← repository layer (Phase 2+): in-memory stores, later persistence
app/routers/        ← FastAPI routes (Phase 2+): HTTP interface, calls services
```

Dependencies flow **inward only**: routers → services → domain. Domain models have no imports from services, repositories, or routers.

`app/config.py` (Phase 3+) holds runtime settings (`pydantic-settings`), not domain state. `app/extraction_targets/` (Phase 3+) holds Pydantic models produced by the LLM extraction pipeline/Skill — these are extraction outputs, not the domain aggregate, so they live outside `app/domain.py`.

### Per-layer restrictions

**Domain layer (`app/domain.py`):**
- Claude must not add service logic (loading, saving, orchestrating transitions) to domain models.
- No `float` anywhere. All monetary amounts, rates, margins, thresholds use `Decimal`. A `float` annotation is a type-checking defect.
- Derived state (e.g. `status`, `is_continuing`, `is_in_covenant_breach`) stays as `@computed_field` — never stored as a plain field that could become inconsistent.
- Business-rule violations raise `ValueError` inside `@model_validator` — Pydantic wraps these into `ValidationError`, FastAPI returns HTTP 422.
- No database imports, no HTTP client imports, no external I/O.

**Service layer:**
- Owns forward-only state transitions (`draft → active → terminated`). Domain models provide `activate()` / `terminate()` as transition helpers; the service enforces preconditions before calling them.
- No direct Pydantic `model_validate` calls on raw dicts from HTTP — that belongs in the router layer.
- `AgreementService` owns all filtering and pagination (`status`, `borrower_id`, `in_covenant_breach`, `limit`/`offset`) — the repository has no query surface for this.
- Raises `AgreementNotFoundError` / `CovenantNotFoundError` (subclassing `DomainNotFoundError`) for missing entities; a FastAPI exception handler in `app/main.py` maps `DomainNotFoundError` to HTTP 404.

**Repository layer:**
- In-memory storage only for this project (explicitly out of scope: SQLAlchemy, database, persistence). See [`docs/PRD.md` §7](docs/PRD.md#7-explicitly-out-of-scope-for-v1).
- `AgreementRepository` is a `Protocol` (structural typing) with exactly three methods: `add`, `get`, `list_all`. No `update`/`save` — see [ADR-0013](docs/adr/0013-in-memory-repository-mutation-by-reference.md).
- Repositories return domain model instances, not dicts or ORM objects.
- DI wiring lives in `app/dependencies.py`: routes depend on `Depends(get_agreement_service)` (or similar), backed by a singleton repository instance — never instantiated directly in a route handler.

### Error type policy

| Source | Mechanism | HTTP response |
|---|---|---|
| Shape / type error (wrong field type, missing required field, bad enum value) | Pydantic `ValidationError` | 422 Unprocessable Entity |
| Business-rule violation (`@model_validator` raises `ValueError`) | Pydantic `ValidationError` | 422 Unprocessable Entity |
| Not found | Service raises (Phase 2) | 404 Not Found |
| Conflict / forbidden transition | Service raises (Phase 2) | 409 Conflict |

Note: [`docs/PRD.md` §5](docs/PRD.md#5-api-behavior-requestresponse-error-handling) distinguishes shape errors (400) from business-rule errors (422). The current policy maps both to 422 via Pydantic's default FastAPI integration — see [ADR-0008](docs/adr/0008-business-rule-validation-to-422.md).

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

Full ADRs live under [`docs/adr/`](docs/adr/), one file per decision (`NNNN-slug.md`). This table is an index only — read the linked file for Decision/Drivers/Alternatives/Consequences.

| ID | Title | Phase |
|---|---|---|
| [0001](docs/adr/0001-invoices-out-of-scope.md) | Invoices out of scope for v1 | — |
| [0002](docs/adr/0002-is-continuing-option-a.md) | `is_continuing` uses Option A | 1 |
| [0003](docs/adr/0003-facility-agreement-status-computed-overlay.md) | `FacilityAgreement.status` → `_base_status` + `@computed_field` overlay | 1 |
| [0004](docs/adr/0004-covenant-test-result-referenced-not-embedded.md) | `CovenantTestResult` referenced on `FacilityAgreement`, not embedded | 1 |
| [0005](docs/adr/0005-no-pytest-in-phase-1.md) | No pytest in Phase 1 | 1 |
| [0006](docs/adr/0006-claude-md-comprehensive-layering-doc.md) | CLAUDE.md v1: comprehensive layering doc | 1 |
| [0007](docs/adr/0007-single-domain-module-no-package-split.md) | Single `app/domain.py` (no package split) | 1 |
| [0008](docs/adr/0008-business-rule-validation-to-422.md) | Business-rule validation in Pydantic models → HTTP 422 | 1 |
| [0009](docs/adr/0009-default-event-mutable.md) | `DefaultEvent` is mutable (`validate_assignment=True`) | 1 |
| [0010](docs/adr/0010-audit-timestamps-in-model-layer.md) | Audit timestamps in model layer | 1 |
| [0011](docs/adr/0011-matured-status-uses-date-today.md) | `matured` status uses `date.today()` | 1 |
| [0012](docs/adr/0012-literal-enums-for-bounded-domain-strings.md) | `Literal` enums for all bounded domain strings | 1 |
| [0013](docs/adr/0013-in-memory-repository-mutation-by-reference.md) | In-memory repository persists by mutation-by-reference (no `update`/`save`) | 2 |
| [0014](docs/adr/0014-sync-by-default-no-real-io.md) | Sync by default: no real I/O in Phase 2 | 2 |
| [0015](docs/adr/0015-first-sync-to-async-boundary.md) | First sync-to-async boundary: `ExtractionService` (narrows ADR-0014) | 3 |
| [0016](docs/adr/0016-project-scoped-hooks-quality-gate.md) | Project-scoped Claude Code hooks: quality tripwire + per-feature spec gate | 4 |

New ADRs: add a `docs/adr/NNNN-slug.md` file with the next sequential number (check the existing folder before assigning — do not reuse or skip numbers), then add a row here.

---

## Claude Code Hooks

Two project-scoped hooks are wired via [`.claude/settings.json`](.claude/settings.json) and enforced on every `Write`/`Edit` — see [ADR-0016](docs/adr/0016-project-scoped-hooks-quality-gate.md) for the full rationale and alternatives considered.

### Hook 1 — quality tripwire (`.claude/hooks/quality_gate.sh`)

**Fires:** `PostToolUse`, on `Write`/`Edit` to `app/**` (excluding `**/__init__.py` and `app/extraction_targets/**`, the latter carved out so it doesn't interrupt the extraction-target-designer Skill mid-generation).

**Checks:** runs the full `uv run poe check` (ruff + mypy + pyright + pytest). On failure, emits `{"decision":"block","reason":<check output>}`.

**Important caveat — this is a tripwire, not a gate.** `PostToolUse` fires *after* the write has already landed on disk; it cannot prevent or undo the write. A failure blocks Claude from continuing to its next turn until the reported failure is fixed — it does not roll back the edit.

**When blocked:** read the reported lint/type/test failure and fix it in the same file before continuing; there is nothing to "unblock" other than making `uv run poe check` pass again.

### Hook 2 — per-feature spec gate (`.claude/hooks/require_spec.sh`)

**Fires:** `PreToolUse`, on `Write`/`Edit` to `app/**` (excluding `**/__init__.py`, checked before segment derivation). Does not gate `tests/`, `docs/`, or `scripts/`.

**Checks:** derives a *feature segment* from the target path — the first path component under `app/` for subdirectory files (e.g. `app/services/extraction_service.py` → `services`), or the filename stem for top-level `app/` files (e.g. `app/domain.py` → `domain`). The edit is allowed only if `docs/specs/<segment>.md` exists, or the segment is listed in the grandfather file [`docs/specs/pre-phase-4-baseline.md`](docs/specs/pre-phase-4-baseline.md) (which covers all Phase 1–3 legacy segments: `domain`, `main`, `config`, `dependencies`, `repositories`, `routers`, `services`, `extraction_targets`). Otherwise it denies via `hookSpecificOutput.permissionDecision: "deny"` with an actionable message.

**`docs/specs/` vs `.omc/specs/`:** these are two separate, unrelated directories. `docs/specs/` is the committed, per-feature spec directory this hook reads (new in Phase 4). `.omc/specs/` holds this project's epic/phase planning docs (deep-interviews, phase reports) and is never read by either hook.

**Going forward (Phase 5+):** any new top-level `app/` file or new subdirectory introduced after Phase 4 needs its own `docs/specs/<segment>.md` before this hook allows edits to it — the baseline grandfather file covers Phases 1–3 only and is not extended retroactively.

**When blocked:** create `docs/specs/<segment>.md` describing the feature you're about to touch, then retry the edit.
