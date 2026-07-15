# ADR-0019 — Database backend selection: `DATABASE_URL` presence

**Status:** Accepted

## Decision

`app/dependencies.py`'s `get_agreement_repository()` selects the backend purely by whether `DatabaseSettings().database_url` is set: unset → `InMemoryAgreementRepository()`, set → `PostgresAgreementRepository`. Routers and services never branch on backend — they depend only on the `AgreementRepository` Protocol.

## Drivers

- Tests, local development, and CI must keep running against in-memory with zero new external dependency — a single, absent setting already guarantees this with no further config.
- Only two backends exist; the URL's mere presence already fully encodes which one is wanted.

## Alternatives considered

- **Explicit `REPOSITORY_BACKEND: Literal["memory", "postgres"]` setting.** Rejected — adds a second setting that must agree with `DATABASE_URL` (e.g. `backend="postgres"` with no URL, or vice versa), for a boolean the URL's presence already encodes. No second backend selection axis exists to justify the extra surface.

## Why chosen

Matches this project's YAGNI posture: the simplest mechanism that satisfies "config, not code" (per the Phase 6 acceptance criteria) with the fewest new settings.

## Consequences

- A malformed-but-present `DATABASE_URL` fails loudly: `DatabaseSettings.database_url` is typed `PostgresDsn | None`, so a bad connection string raises a Pydantic validation error at settings construction, not a confusing downstream `asyncpg` error on first query.
- **MCP/HTTP cross-process data sharing becomes real.** `app/mcp_server.py`'s tools resolve `get_agreement_repository()`/`get_agreement_service()` through the same DI providers as the HTTP API (`docs/specs/mcp_server.md`). Once `DATABASE_URL` is set, both processes resolve to `PostgresAgreementRepository` instances hitting the same live database — an MCP client can now read live data created via the HTTP API in a separate process. Before this ADR, `docs/specs/mcp_server.md`'s "Known limitation" section stated this couldn't happen, because no persistence layer existed; that premise is now false whenever `DATABASE_URL` is set. See `docs/specs/mcp_server.md`'s updated Known Limitation section and ADR-0018's Follow-ups.
- `get_agreement_repository()` remains a synchronous `@lru_cache` provider — it only constructs objects (`create_async_engine()` doesn't open a connection), so no I/O happens at DI-resolution time regardless of backend.
