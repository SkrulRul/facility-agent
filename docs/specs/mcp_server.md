# `mcp_server` — Feature Spec

Covers `app/mcp_server.py`, introduced in Phase 5. See [ADR-0018](../adr/0018-mcp-server-fastmcp-stdio.md) for the full decision record and [`.omc/specs/phase-5-mcp-server.md`](../../.omc/specs/phase-5-mcp-server.md) for the phase plan.

## Scope

A standalone MCP server exposing the Facility Agent's query capabilities as MCP tools, so an MCP client (e.g. a Claude Code session) can query facility agreement data directly. Read-only for v1 — no write tools.

## Tools

| Tool | Input | Output | Backing service call |
|---|---|---|---|
| `get_agreement` | `agreement_id: UUID` | `FacilityAgreement` | `AgreementService.get_agreement(agreement_id)` |
| `list_continuing_defaults` | `agreement_id: UUID` | `list[DefaultEvent]` | `AgreementService.list_continuing_defaults(agreement_id)` |

Both tools are thin adapters: no filtering or business logic lives in `app/mcp_server.py` itself. `list_continuing_defaults` is backed by a new `AgreementService` method (not a repository query) — see ADR-0018.

## Transport & library

- **Library:** `fastmcp` (decorator-based tool registration, analogous to FastAPI's route decorators already used in this codebase).
- **Transport:** stdio — the server is launched as a subprocess by an MCP client, not a long-running HTTP service.
- **Entry point:** `uv run python -m app.mcp_server` runs the server via `mcp.run()` under `if __name__ == "__main__":`. This is a second, independent process alongside `uv run fastapi dev` — it is not mounted on the FastAPI app in `app/main.py`.

## DI reuse

`app/mcp_server.py` calls `app.dependencies.get_agreement_service` / `get_agreement_repository` directly (imported by bare name, not qualified — see Testing below), constructing the service fresh on each tool invocation. `get_agreement_repository()` is `@lru_cache`d, so this costs nothing in production — it resolves to the same process-lifetime singleton FastAPI's `Depends()` graph would have used, had this been a FastAPI route.

## Error handling

`mcp = FastMCP("facility-agent", mask_error_details=True)` — any unmodeled exception is masked to a generic message before reaching the client, so a future bug inside a tool body can't leak internals (added after security review; see ADR-0018 Consequences).

`AgreementNotFoundError` is the one expected, deliberate error each tool can raise. It's explicitly caught and re-raised as `fastmcp.exceptions.ToolError(str(exc))` in both tool bodies — `ToolError` is a `FastMCPError` subtype, which bypasses masking, so the caller still gets the useful "Agreement `<id>` not found" message (echoing only their own input, nothing sensitive). This is the MCP equivalent of `app/main.py`'s `DomainNotFoundError` → HTTP 404 mapping — same translation, no HTTP status code involved.

## Testing

`tests/test_mcp_server.py` drives both tools through a real in-process `fastmcp.Client(mcp)` — no subprocess. Repository isolation uses `monkeypatch.setattr("app.mcp_server.get_agreement_repository", lambda: repository)` with a fresh `InMemoryAgreementRepository()` per test, mirroring `tests/conftest.py`'s `app.dependency_overrides` pattern for the HTTP suite (fastmcp has no `Depends`, so `dependency_overrides` cannot reach it — monkeypatch is the equivalent seam).

**Implementation constraint:** `app/mcp_server.py` must `from app.dependencies import get_agreement_repository, get_agreement_service` and call the bare names inside each tool body. A qualified call (`app.dependencies.get_agreement_repository()`) would make the monkeypatch target miss, silently falling through to the real process singleton in tests.

`scripts/smoke_test_mcp_server.py` is a separate, manual smoke test (not part of `uv run poe check`, same pattern as `scripts/smoke_test_extraction.py` — see ADR-0015) that proves the process boundary itself works — tool registration, the success path, and the not-found error path, all over the real wire protocol — closing the coverage gap the in-process test suite structurally can't reach (`tests/test_mcp_server.py` never spawns a subprocess).

Since the production entry point has no write/seed capability by design (see Known Limitation below), the smoke test spawns `scripts/mcp_server_seeded.py` instead of `app/mcp_server.py` directly — a test-only entry point that imports the *same* `mcp` object unmodified, seeds one example agreement (fixed UUID, so no inter-process communication beyond MCP is needed) directly into the repository, then calls `mcp.run()`. This keeps `app/mcp_server.py` itself completely untouched — production usage (a real MCP client launching `uv run python -m app.mcp_server`) still has zero seed/write capability. Run manually:
```bash
uv run python scripts/smoke_test_mcp_server.py
```

## Known limitation

A live stdio subprocess (e.g. one launched by a Claude Code MCP client) gets its own independent, empty `InMemoryAgreementRepository` — separate from any concurrently running `uv run fastapi dev` process's store. There is no write-capable MCP tool, so a live stdio server has no way to be populated with data outside of a test harness that seeds the repository directly. Cross-process data sharing was never a design goal here — the epic's "Out of Scope" section already rules out a real persistence layer for this project — but it means the MCP server is currently useful for demonstrating the protocol and for its own test suite, not for querying data created via the HTTP API in a separate live process.

## Explicitly out of scope (this phase)

- `list_covenants`, `check_covenant_status` (candidates from the original phase-5 spec table, deferred — no service method exists for either today).
- SSE/HTTP transport.
- Raw `mcp` SDK (using `fastmcp` instead).
- Mounting the MCP server on the FastAPI app.
- Any write tool.
