# ADR-0020 — Async boundary extension: repository through service, routers, and MCP tools

**Status:** Accepted

## Decision

Async propagates fully from `PostgresAgreementRepository` through `AgreementService`, all 5 FastAPI route handlers (`app/routers/agreements.py`), and both MCP tool functions (`app/mcp_server.py`). The `AgreementRepository` Protocol's four methods (`add`, `get`, `list_all`, `update`) are all `async def`; `InMemoryAgreementRepository` implements them as trivial async wrappers around its dict operations (no real `await` inside) so one Protocol serves both backends uniformly.

## Drivers

- SQLAlchemy's async engine (chosen for the Postgres repository) forces the boundary to start at the repository — there is no sync SQLAlchemy async session.
- ADR-0015's precedent: no sync bridge keeps a genuine I/O boundary contained. `ExtractionService`'s "async is contained" property held only because no caller awaited it; the moment a caller does, the boundary propagates. `AgreementService`'s methods are called from route handlers by construction, so the same propagation is immediate and total here, not conditional.
- Narrows ADR-0014, which explicitly anticipated this: "if a later phase introduces real I/O ... that new code path should be evaluated for async on its own merits — this ADR does not preclude async elsewhere."

## Alternatives considered

- **Sync facade bridging to the async repository via `asyncio.run()` per call.** Rejected — event-loop-inside-event-loop hazard under FastAPI's own async runtime; the same rejection logic ADR-0015 already applied when considering (and rejecting) a thread-offloaded sync wrapper for `ExtractionService`. Also reintroduces exactly the "fake sync wrapper over real I/O" pattern ADR-0014/0015 argued against.
- **Synchronous SQLAlchemy engine (`psycopg`, not `asyncpg`) with FastAPI's threadpool offload for sync handlers** — the mechanism ADR-0014 relied on for the in-memory repository. A real alternative, not a strawman: `docs/PRD.md` §6 states no performance requirement exists, so this would have delivered equivalent behavior with zero `async def` propagation and zero `MissingGreenlet` risk. Rejected during Phase 6 discovery specifically to keep one Protocol, one code path, and one persistence strategy going forward, matching this project's "match established precedent" principle (ADR-0015's real-I/O-goes-async pattern) rather than introducing a second, sync-only persistence style alongside it.

## Why chosen

The atomic, full propagation keeps a single `AgreementRepository` Protocol implementation shape for both backends — no sync/async split between them — and follows the one precedent this codebase has already set for a genuine I/O boundary (ADR-0015).

## Consequences

- **The conversion had to land as one coherent commit, not staged.** `async`/`await` is contagious at the type level under strict mypy/pyright — a partial conversion is a type-check failure, not a soft warning. This project's own tooling makes a staged, multi-commit conversion actively unworkable, not merely inadvisable: `.claude/hooks/quality_gate.sh` runs the full `uv run poe check` after every `Write`/`Edit` to `app/**`, and the `enforce_check.sh` Stop-hook backstop (ADR-0017) blocks ending a session turn on a red `app/` state. An intermediate "Protocol is async but the service isn't" state would leave `app/` red and get blocked.
- `app/mcp_server.py`'s two `@mcp.tool` functions become `async def` — `fastmcp` supports async tools natively, so this is mechanical, but it is a real, necessary consequence: a sync tool calling a now-async service method would silently return an unawaited coroutine rather than a result.
- `PostgresAgreementRepository.get()`/`list_all()` use explicit `selectinload()` for the `covenant_test_results`/`default_events` relationships — SQLAlchemy's async ORM raises `MissingGreenlet` at runtime (with no static type-check signal) if a lazy-loaded relationship is touched outside an awaited context.
- `app/main.py` gains a `lifespan` handler (previously had none) that disposes the async engine on shutdown when `DatabaseSettings().database_url` is set — closes an engine-lifecycle gap that would otherwise leave the connection pool undisposed for the process lifetime.
- `list_all()`'s full-table-scan-and-hydrate cost is real once backed by Postgres (a genuine network round-trip + full relationship hydration per call, vs. an in-process dict scan) — accepted, not addressed, because `AgreementService` owns all filtering per CLAUDE.md (the repository has no query-pushdown surface), so no index or filter-pushdown would remove this cost regardless; no stated performance requirement exists to justify optimizing it speculatively.

## Follow-ups

- If a genuine concurrency/performance requirement appears, revisit whether `AgreementService`'s filtering should move query-level (would require reopening CLAUDE.md's "repository has no query surface" rule, not just this ADR).
