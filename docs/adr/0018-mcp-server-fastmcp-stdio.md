# ADR-0018 — MCP server: fastmcp, stdio, 2-tool scope, standalone entry point

**Status:** Accepted

## Decision

`app/mcp_server.py` uses `fastmcp.FastMCP` over stdio transport, exposing exactly two tools — `get_agreement(agreement_id: UUID) -> FacilityAgreement` and `list_continuing_defaults(agreement_id: UUID) -> list[DefaultEvent]` — wired directly to `app/dependencies.py`'s existing `get_agreement_repository()`/`get_agreement_service()` providers. It is a standalone entry point (`uv run python -m app.mcp_server`), not mounted on the FastAPI app in `app/main.py`.

## Drivers

- Phase 5's stated learning objective is understanding the MCP *provider* side; stdio is the simplest transport that maps directly to a local Claude Code MCP client config, with no new HTTP surface to stand up.
- `fastmcp`'s decorator-based tool registration (`@mcp.tool`) is structurally analogous to FastAPI's own route decorators, already used throughout this codebase — minimizing new concepts over the raw `mcp` SDK's manual JSON-RPC wiring.
- Two tools keeps the exercise scoped and fully testable in one sitting, matching this project's phase-by-phase structure.

## Alternatives considered

- **SSE/HTTP transport.** Rejected: doesn't map to a local Claude Code MCP client config as directly as stdio; adds an HTTP lifecycle question (port, startup) with no corresponding requirement this phase.
- **Raw `mcp` SDK.** Rejected: more "from scratch," but the extra JSON-RPC boilerplate has no second consumer to justify it; `fastmcp`'s API is the lower-friction, already-familiar shape.
- **Mount on `app/main.py`'s FastAPI app.** Rejected: stdio is a different process-lifecycle model than an ASGI HTTP app; conflating them would make `app/main.py` responsible for two servers reachable two different ways, with no forcing requirement from the epic or CLAUDE.md.
- **All 4 candidate tools from the original phase-5 spec table.** Rejected for v1: the spec table was explicitly marked "candidates — to be confirmed during discovery." `list_covenants`/`check_covenant_status` would need new, untested service methods this phase doesn't budget for — deferred, not designed away.

## Why chosen

This combination satisfies the phase's explicit acceptance criteria (≥2 tools, server starts and registers correctly, ≥2 tools tested end-to-end from a client) with the least new surface area, and leaves `app/main.py`'s HTTP-only responsibility untouched — avoiding an unanswered layering question (how would an MCP mount interact with the `DomainNotFoundError` → HTTP 404 exception handler registered there?).

## Consequences

- New runtime dependency: `fastmcp`.
- New top-level `app/` segment (`mcp_server`) requires its own `docs/specs/mcp_server.md` before Hook 2 permits edits — not grandfathered, per `docs/specs/pre-phase-4-baseline.md`'s own text.
- `AgreementService` gains one new method, `list_continuing_defaults` — the only other production-code change this phase. Placed on the service (not inlined in `app/mcp_server.py`) because CLAUDE.md states "`AgreementService` owns all filtering and pagination ... the repository has no query surface for this" — that rule's intent extends to single-item filtering, not just repository-wide queries, and adding a 2-line method to an already-existing class trips none of the project's YAGNI triggers (no new type, file, or registry).
- `get_agreement` and `list_continuing_defaults` return raw domain models (`FacilityAgreement`, `list[DefaultEvent]`) rather than the router layer's `*Response` DTOs — an intentional divergence from the router convention (`DefaultEventResponse` already exists and already carries `is_continuing: bool`, so the DTO option was available at zero cost but not taken). Chosen for adapter simplicity: MCP tool consumers are agents, not browser clients, and the domain models already serialize cleanly via their computed fields.
- No FastAPI route added; the MCP server is a second, independent entry point run via `uv run python -m app.mcp_server`, alongside `uv run fastapi dev`.
- `mask_error_details=True` on the `FastMCP` constructor, added after security review: any unmodeled exception is masked to a generic message rather than echoing `str(exc)` to the client, closing an information-exposure gap the HTTP API doesn't have (FastAPI/Starlette's default 500 handler is already opaque). The one expected error, `AgreementNotFoundError`, is explicitly caught in each tool and re-raised as `fastmcp.exceptions.ToolError(str(exc))` — a `FastMCPError` subtype that bypasses masking — so the useful not-found message still reaches the client. This is the MCP equivalent of `app/main.py`'s `DomainNotFoundError` → 404 mapping, done per-tool rather than via a single exception handler (fastmcp has no app-wide exception-handler registration analogous to FastAPI's).
- A live stdio subprocess has its own independent, empty in-memory store, separate from any concurrently running `fastapi dev` process — see the "Known limitation" section of `docs/specs/mcp_server.md`.
- Not covered: `list_covenants`, `check_covenant_status` — deferred, no consumer today.

## Follow-ups

- If a future phase needs `list_covenants`/`check_covenant_status` as MCP tools, add them as new `@mcp.tool` functions in the same file (no reason to split files at 4 tools) plus corresponding service methods, with a `docs/specs/mcp_server.md` update if scope grows meaningfully.
- If remote/SSE transport is ever needed, `fastmcp` supports it via `mcp.run(transport=...)` without a rewrite — revisit only if a concrete consumer appears.
