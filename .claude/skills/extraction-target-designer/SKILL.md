---
name: extraction-target-designer
description: Given an example unstructured document, design a Pydantic extraction target model + pytest test file for the Phase 3 LLM extraction pipeline
triggers:
  - design extraction target
  - new extraction target
argument-hint: "<path to example document, or pasted document text>"
---

<Purpose>
Given one example of an unstructured document (a term sheet excerpt, a covenant waiver letter, an amendment notice, etc.), design a new Pydantic model that represents its structured content and a pytest test file that proves `ExtractionService.extract()` can extract it — without editing any existing shared file. This is a Claude-native reasoning task: you (Claude Code) design the model and test yourself. No Python code calls an LLM to generate the model.
</Purpose>

<Use_When>
- A new unstructured document type needs to become an extraction target
- User says "design extraction target" or provides an example document and asks for a new Pydantic model + test
</Use_When>

<Restrictions>
- No API call, no meta-generation Python code. The model design is your own reasoning against the example document, not an LLM call made in application code.
- Write to `app/extraction_targets/<slug>.py` and `tests/extraction/test_<slug>_extraction.py` only. Never edit `app/extraction_targets/__init__.py` (it stays empty — no re-export barrel) or any other existing file. A target "registers" itself simply by existing as a module the caller can import and pass to `extract(text, YourModel)`.
- Follow `CLAUDE.md` domain-layer conventions: `Decimal` for money, `Literal` for bounded strings, `ConfigDict(frozen=True, strict=True)`, snake_case fields, PascalCase model name, `date`/`UUID` for their respective concepts. No `float` anywhere.
- **Every `@model_validator` `ValueError` message must name the offending field in its text** (e.g. `"facility_amount must be greater than 0"`, not `"must be greater than 0"`). Model-level validators produce `loc: []` in `ValidationError.errors()` — the correction turn injects `msg` but has no field path to fall back on, so the field name in the message text is the only positional signal the LLM gets during a correction retry.
</Restrictions>

<Steps>
1. **Read the example document.** Identify the concrete fields it contains — the ones you could actually populate from the text, not a speculative superset.
2. **Design the Pydantic model** in `app/extraction_targets/<slug>.py` (slug = a short snake_case name for the document type, e.g. `amendment_notice`):
   - `ConfigDict(frozen=True, strict=True)`
   - Money → `Decimal`. Bounded/enum-like strings → `Literal`. Dates → `date`. References/IDs that are free text (not a real `UUID` in the document) → `str`.
   - If the document implies a business rule beyond shape (e.g. "amount must be positive", "effective date must be after some reference date"), add a `@model_validator(mode="after")` that raises `ValueError` with the offending field named in the message text.
3. **Write the test file** `tests/extraction/test_<slug>_extraction.py`, following the pattern in `tests/extraction/test_term_sheet_extraction.py` / `test_covenant_waiver_extraction.py`:
   - Import `make_service` from `tests.extraction.conftest`.
   - Author a `VALID_PAYLOAD` and an `INVALID_PAYLOAD` as JSON-native dicts (string dates, string/number amounts — never pre-converted `Decimal`/`date` objects), since the pipeline validates via `model_validate_json`.
   - Three cases minimum: happy path (`make_service(VALID_PAYLOAD)`, assert result, assert 1 call), one-retry recovery (`make_service(INVALID_PAYLOAD, VALID_PAYLOAD)`, assert result, assert 2 calls, assert the correction turn's `msg` text appears), max-attempts exceeded (`make_service(INVALID_PAYLOAD, INVALID_PAYLOAD, INVALID_PAYLOAD)`, assert `ExtractionError` raised, assert 3 calls).
4. **Add a fixture** — if the caller supplied an example document as free text rather than a file path, save it to `tests/fixtures/<slug>.txt`.
5. **Run `uv run poe check`** and iterate until it's green. Fix type errors, lint issues, and failing assertions before considering the target done.
</Steps>

<Output_Format>
Report the two (or three, with fixture) files created, and confirm `uv run poe check` is green.
</Output_Format>
