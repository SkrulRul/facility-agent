# Pre-Phase-4 Baseline — Grandfathered Feature Segments

Covers all app/ code predating the Phase-4 spec-before-code gate (Phases 1-3).
Each segment below is grandfathered: editing its code is allowed without a
per-segment docs/specs/<segment>.md, because the referenced ADRs/phase specs
already document it. NEW segments introduced in Phase 5+ are NOT covered here
and must get their own docs/specs/<segment>.md.

## Covered segments (machine-checked)

<!-- Hook 2 (require_spec.sh) matches ONLY this fenced list, whole-line, fixed-string:
     grep -Fxq -- "- <segment>". One token per line, exact form "- <token>".
     Do NOT add prose, trailing text, or table rows inside this fence. -->

```
- domain
- main
- config
- dependencies
- repositories
- routers
- services
- extraction_targets
```

## Documentation (human-readable — NOT machine-checked)

| Segment | Documented by |
|---------|---------------|
| domain | Domain models (`app/domain.py`). ADR-0002 (`is_continuing` Option A), ADR-0003 (`status` computed overlay), ADR-0004 (`CovenantTestResult` referenced), ADR-0007 (single-module structure), ADR-0009 (`DefaultEvent` mutable), ADR-0010 (audit timestamps), ADR-0011 (`matured` uses `date.today()`), ADR-0012 (Literal enums). See `.omc/specs/phase-1-domain-modeling.md`. |
| main | App entrypoint and exception-handler wiring (`app/main.py`). `DomainNotFoundError` -> HTTP 404 mapping. ADR-0008 (business-rule validation -> 422). See `.omc/specs/phase-2-di-async-pytest.md`. |
| config | Runtime settings via `pydantic-settings` (`app/config.py`), introduced for the LLM extraction pipeline. See `.omc/specs/phase-3-llm-extraction.md`, ADR-0015. |
| dependencies | FastAPI DI wiring, repository singleton (`app/dependencies.py`). ADR-0013 (in-memory repository, mutation-by-reference, no update/save). See `.omc/specs/phase-2-di-async-pytest.md`. |
| repositories | In-memory `AgreementRepository` Protocol and implementation (`app/repositories/`). ADR-0013. See `.omc/specs/phase-2-di-async-pytest.md`. |
| routers | HTTP interface, FastAPI routes and response schemas (`app/routers/`). ADR-0008 (422 mapping). See `.omc/specs/phase-2-di-async-pytest.md`. |
| services | Service layer: `AgreementService` (forward-only transitions, filtering/pagination) and `ExtractionService` (async LLM extraction pipeline) (`app/services/`). ADR-0014 (sync-by-default), ADR-0015 (first sync-to-async boundary). See `.omc/specs/phase-2-di-async-pytest.md`, `.omc/specs/phase-3-llm-extraction.md`. |
| extraction_targets | Pydantic extraction-target models produced by the extraction-target-designer Skill (`app/extraction_targets/`). ADR-0015. See `.omc/specs/phase-3-llm-extraction.md`, `.omc/specs/deep-interview-phase3-llm-extraction.md`. |

Note the prose table above intentionally contains words like `handler` and
`interface` that are NOT segment tokens — these prove the value of matching
only the fenced list: `grep -Fxq -- "- handler"` against this file must FAIL
even though "handler" appears in the table above.

Convention coarseness (accepted, not blocking): a hypothetical future
top-level `app/services.py` and the existing `app/services/` directory would
both derive the same `services` token — coarse-but-not-a-security-gap for a
training MVP.

Phase-5+ new segments are NOT covered by this file and must get their own
`docs/specs/<segment>.md` before Hook 2 (`require_spec.sh`) allows edits to
them. This baseline is not extended retroactively.
