# ADR-0016 — Project-scoped Claude Code hooks: quality tripwire + per-feature spec gate

**Status:** Accepted

## Decision

Adopt two project-scoped Claude Code hooks wired via `.claude/settings.json` (never `~/.claude/settings.json`):

1. **`PostToolUse` quality tripwire** (`.claude/hooks/quality_gate.sh`): on `Write|Edit` to `app/**`, runs the full `uv run poe check`. On failure, emits `{"decision":"block","reason":<output>}`, halting Claude's continuation until the failure is fixed. Carves out `**/__init__.py` and `app/extraction_targets/**` (the latter so the extraction-target-designer Skill's multi-file generation flow isn't interrupted mid-run).
2. **`PreToolUse` per-feature spec gate** (`.claude/hooks/require_spec.sh`): on `Write|Edit` to `app/**`, derives a *feature segment* from the path — the first path component under `app/` for subdirectory files (e.g. `app/services/extraction_service.py` → `services`), or the filename stem for top-level `app/` files (e.g. `app/domain.py` → `domain`). Denies the edit via `hookSpecificOutput.permissionDecision: "deny"` unless `docs/specs/<segment>.md` exists, or the segment is listed in the grandfather file `docs/specs/pre-phase-4-baseline.md` (which covers all Phase 1–3 legacy segments). `**/__init__.py` is exempt before segment derivation.

`docs/specs/` is a new committed directory, sibling to `docs/adr/` and `docs/PRD.md`. It is unrelated to `.omc/specs/`, which holds this project's epic/phase planning docs and is untouched by either hook.

## Drivers

- **Truthful enforcement semantics.** A hook must only claim to do what its event can actually do. `PostToolUse` fires after the write lands — it cannot prevent or undo it, only block Claude's next turn. It is named a *tripwire*, not a *gate*, throughout the docs and code to avoid overselling it.
- **Per-feature spec discipline over per-file precision.** The spec-before-code gate binds at the feature-subtree level, not the individual file, matching how specs are actually authored on this project (one spec per phase/feature, not per module).
- **Zero regression, zero disruption.** `uv run poe check` must stay green after wiring; normal development (including TDD red-phase test authoring) must remain workable; the Phase-3 extraction-target-designer Skill must still be able to write `app/extraction_targets/<slug>.py` + its test without interruption.

## Alternatives considered

- **Typecheck-only tripwire (skip lint/tests).** Rejected — the full `poe check` runs in ~3.6s, fast enough to run on every gated write; no need to trade completeness for speed.
- **Trip the quality tripwire on `tests/**` too.** Rejected — would block a deliberately-failing (red) TDD test on every intermediate save, fighting the standard test-first workflow. The tripwire scoped to `app/**` still catches test-visible regressions, because it always runs the *entire* suite regardless of which file triggered it.
- **Per-file `path → spec` manifest (or spec-frontmatter naming each covered file).** Rejected — a registry with a single consumer; premature abstraction per this project's KISS/YAGNI conventions, and finer-grained than the intended per-feature discipline.
- **Whole-word basename grep across `.omc/specs/**` (an earlier draft of this design).** Superseded — wrong granularity (per-file, not per-feature), wrong directory (`.omc/specs/` holds planning docs, not committed feature specs), and a basename mention anywhere in any planning doc would unlock that file forever, both over- and under-inclusive in practice.
- **Hardcoded `app/extraction_targets/**` bypass in the spec gate.** Rejected — `extraction_targets` is a first-class baseline-covered segment, so the bypass would be redundant for spec coverage. (The *quality tripwire* keeps its own `extraction_targets` carve-out, for the unrelated runtime reason of not interrupting the Skill mid-generation.)
- **`PreToolUse` for the quality check.** Invalid — the code to check does not exist on disk until the write completes; a pre-write hook cannot run `poe check` against content that isn't there yet.
- **Global `~/.claude/settings.json`.** Rejected — project-scoped is safer and keeps the hooks reviewable/versioned alongside the code they gate.

## Why chosen

Each hook enforces exactly what it can truthfully enforce at its event, with minimal moving parts: one settings file, two ~15-line scripts, one enumerated baseline markdown file, no registry. Feature-segment membership is a deterministic naming convention (shell parameter expansion, not a stored mapping) plus a single fixed-string, whole-line grep (`grep -Fxq -- "- $segment"`) against a fenced, machine-checked token list — kept physically separate from that same file's human-readable ADR-cross-reference prose, so the match can never collide with descriptive text. Legacy Phase 1–3 code is grandfathered by one file instead of requiring eight new specs up front.

## Consequences

- Every non-carved-out `app/` write pays the full `poe check` (~3.6s) — accepted; the tripwire cannot roll back a bad write, only block Claude's continuation.
- The spec gate is coarse at the feature level: once a segment is covered, every file in that subtree is editable, even ones the covering spec doesn't discuss. Accepted as training-grade.
- The naming convention is coarse enough that a hypothetical future top-level `app/services.py` and the existing `app/services/` directory would collapse to the same `services` token — accepted as coarse-but-not-a-security-gap.
- `docs/specs/` now exists and must be maintained going forward: any new top-level `app/` file or new subdirectory introduced after Phase 4 requires its own `docs/specs/<segment>.md` before the spec gate allows edits to it. The baseline grandfather file covers Phases 1–3 only and is not extended retroactively.
- `app/extraction_targets/**` is spec-covered via the baseline segment for the spec gate, but still carved out of the quality tripwire for the separate runtime reason.
- `**/__init__.py` is never gated by either hook.

## Follow-ups

- Author real per-segment `docs/specs/<segment>.md` files as features evolve, gradually retiring reliance on the baseline grandfather file.
- Tighten to per-file binding only if a second genuine consumer of finer-grained spec coverage appears (currently none).
- Revisit the ~3.6s per-write tripwire cost if the suite grows slow enough to make rapid multi-save editing sessions noisy.
