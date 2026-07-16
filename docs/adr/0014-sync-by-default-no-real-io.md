# ADR-0014 — Sync by default: no real I/O in Phase 2

**Status:** Superseded by [ADR-0020](0020-async-boundary-extension.md) (Phase 6) — async fully propagated through `app/` in Phase 6 (repository, service, routers, MCP tools all `async def`), so no sync code path remains anywhere in `app/`. This differs from [ADR-0015](0015-first-sync-to-async-boundary.md), which only narrowed this ADR's scope (one additional async surface, `ExtractionService`) without overturning it — ADR-0020 is what fully supersedes it.

## Decision

Every Phase 2 repository, service, and router function is synchronous (`def`, not `async def`). Async is not used anywhere in Phase 2.

## Drivers

- The Phase 2 spec requires that async only be used where justified by real I/O, with sync as the default.
- The in-memory repository is a plain Python dict — there is no database driver, network call, or file I/O anywhere in the request path. Making handlers `async def` over an in-memory dict would be a fake justification with zero benefit.

## Consequences

- FastAPI runs synchronous route handlers in a thread pool automatically, so this has no correctness impact; [`docs/PRD.md` §6](../PRD.md#6-non-functional-behavior) explicitly states there is no performance requirement for this project, which licenses this choice.
- If a later phase introduces real I/O (e.g. an LLM API call in Phase 3, or a real database in a future persistence phase), that new code path should be evaluated for async on its own merits — this ADR does not preclude async elsewhere, it only documents why Phase 2 specifically has none.
