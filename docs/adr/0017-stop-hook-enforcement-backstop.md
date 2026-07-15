# ADR-0017 — Stop-hook enforcement backstop for the quality tripwire

**Status:** Accepted

## Decision

Add a `Stop` hook (`.claude/hooks/enforce_check.sh`) that turns Hook 1 (the `PostToolUse` quality tripwire, ADR-0016) from an advisory signal into a genuinely enforced gate. `quality_gate.sh` now additionally persists its result to `.claude/hooks/.runtime/last_check.json` (`{status, reason, session_id}`) every time it runs `poe check`. `enforce_check.sh` reads that file at `Stop` time: if `status: "fail"` **and** the recorded `session_id` matches the current session, it emits `{"decision":"block","reason":...}`, which the Claude Code harness enforces by refusing to let the turn end. Any other case (pass, no state file, or a `session_id` mismatch) allows the stop. This narrows ADR-0016 rather than replacing it — the `PostToolUse` detection mechanism, its `app/**` scoping, and its carve-outs are unchanged.

## Drivers

- **The Phase 4 spec's own stated goal** — "make it impossible to write broken code without immediate feedback" — is not actually met by `PostToolUse` alone. Its `decision:"block"` is injected as tool-result-like feedback *within Claude's own turn*; nothing in the harness compels the agent to act on it. `Stop`'s `decision:"block"` is different in kind: the harness refuses to let the turn end at all, regardless of what Claude currently intends to do.
- **Reuse, not duplication, of the detection logic.** `quality_gate.sh` already runs the full check precisely when it needs to (scoped to `app/**`, carved out where appropriate) and produces a clean failure reason. Re-running `poe check` a second time at `Stop` (which has no matcher and can't cheaply tell whether `app/` was touched this turn) would double the cost and duplicate the ANSI-stripping/JSON-building logic for no benefit.
- **No false blocking of unrelated future sessions.** A hook mechanism this strict (refuses to let a turn end) must fail open on stale or ambiguous state, or it becomes a bigger problem than the one it solves.

## Alternatives considered

- **Have `Stop` re-run `uv run poe check` itself, independent of `quality_gate.sh`.** Rejected — duplicates the check/ANSI-strip/JSON-build logic across two scripts, and pays the full ~3.6s cost at the end of *every* turn regardless of whether `app/` was even touched (Stop has no matcher and no cheap way to know).
- **State file with no `session_id` tagging.** Rejected — a session interrupted or killed mid-failure (before its own `Stop` event could resolve the failure) would leave a `status:"fail"` marker on disk indefinitely, wrongly blocking a completely unrelated future session before it had touched `app/` at all. Tagging with `session_id` (available on both `PostToolUse` and `Stop` stdin per the Claude Code hook contract) closes this cleanly and cheaply — confirmed empirically this session: a `Stop` invocation with a mismatched `session_id` correctly allows the stop even while a real `fail` marker is present.
- **Do nothing; document the PostToolUse-vs-Stop enforcement gap as an accepted limitation.** Considered and rejected once the hybrid design was proposed — the hybrid gets the enforcement guarantee without giving up `PostToolUse`'s precise, cheap, file-path-scoped detection, so there was no real reason to accept the weaker guarantee.
- **Replace `PostToolUse` entirely with a `Stop`-only design.** Rejected (see the earlier PostToolUse-vs-Stop discussion) — `Stop` has no matcher, so it can't scope to `app/**` or carve out `__init__.py`/`extraction_targets/**` without parsing the transcript; keeping `PostToolUse` for detection preserves that precision.

## Why chosen

The hybrid keeps each hook doing what it's structurally good at: `PostToolUse` for fast, precisely-scoped detection immediately after the causing edit; `Stop` for the one thing only it can do — refuse to let Claude walk away from a known-broken `app/` state. The state file is the minimal glue between them, and the `session_id` tag is the minimal fix for the one real failure mode (cross-session staleness) that glue introduces.

## Consequences

- A new ephemeral, gitignored file (`.claude/hooks/.runtime/last_check.json`) exists at runtime — not committed, not part of the repo's tracked state.
- If a session is interrupted while `status:"fail"` is recorded, the marker persists on disk but is inert for any *other* session (session_id mismatch) and is only ever re-honored if that exact session resumes and hits another `Stop` event — an accepted, narrow edge case.
- `Stop` fires on every turn end, but the check itself is now free at `Stop` time (`test -f` + a small `jq` read) — it doesn't re-run `poe check`, so the enforcement backstop adds negligible cost.
- Claude can no longer silently end a turn with known-broken `app/` code in the same session that broke it — verified empirically (see `.omc/specs/phase-4-hooks.md` evidence).

## Follow-ups

- If a future need arises to enforce across `SubagentStop` too (a subagent finishing mid-task with broken code), the same state-file + session-tagging pattern would extend directly — not built now, no concrete consumer yet (YAGNI).
- Revisit the interrupted-session inert-marker edge case only if it proves to actually confuse a real workflow; not fixed further now since normal operation makes it self-resolving within the originating session.
