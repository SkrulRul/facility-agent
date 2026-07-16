# ADR-0025 — Structured logging with contextvar-based correlation ids

**Status:** Accepted

## Decision

Add request-scoped structured logging using stdlib `logging` only — no new third-party logging dependency. A single JSON `logging.Formatter` writes one log line per record to stdout. A per-request correlation id is generated server-side (`uuid4().hex`) and threaded through nested calls implicitly via a `contextvars.ContextVar`, not by passing it as a function parameter through every layer. See [`docs/specs/logging.md`](../specs/logging.md) for the mechanism and call sites.

## Drivers

- The ticket's acceptance criteria: every request gets a correlation id, that id appears in every log line for that request including nested service calls, logs are structured/machine-parseable, errors carry enough context to diagnose without reproducing, no raw agreement terms or party PII in plaintext.
- The ticket explicitly puts external log shipping (Datadog/ELK/CloudWatch) and distributed tracing out of scope — this is a single-service system today, so a full tracing library (OpenTelemetry) would be solving a problem that doesn't exist yet.
- "Nested service calls" (`app/routers` → `app/services` → `app/repositories`) rules out passing the correlation id as an explicit parameter down every call signature — that would touch every function in three layers for one cross-cutting concern. A contextvar scoped to the current async task solves this without touching business-logic signatures at all.

## Alternatives considered

- **`structlog`.** Gives contextvar-bound structured logging out of the box with less boilerplate. Rejected: it's a new dependency for a capability stdlib `logging` + one `Filter` + one `Formatter` (~80 lines) already covers at this scope. Revisit if log call sites grow enough that stdlib's ergonomics become the bottleneck, or if a second service needs to share the same logging setup.
- **OpenTelemetry (tracing + logs).** Rejected — the ticket explicitly excludes distributed tracing, and OTel's value is multi-service correlation, which doesn't exist here (single-service system, per the ticket's own out-of-scope note).
- **Passing `correlation_id` as an explicit parameter through router → service → repository.** Rejected — cross-cutting concern, would touch every method signature in `AgreementService` and both repository implementations for no reason beyond logging, violating this codebase's layering principle that domain/service signatures reflect business operations, not infrastructure concerns.
- **Trusting/echoing an inbound `X-Request-ID` header from the caller.** Rejected for this ticket's scope — there's no upstream proxy or gateway in this single-service system that's authenticated to set log-correlation identity, so honoring a client-supplied id would let any caller inject arbitrary values into structured logs. Revisit if a reverse proxy or load balancer is introduced that can be trusted to mint or forward this header.

## Consequences

- Zero new runtime dependencies.
- Every log line, from the middleware down through service and repository code, carries the same `correlation_id` for a given request with no code changes needed in `app/services/` or `app/repositories/` — the contextvar crosses layer boundaries for free.
- The correlation id is also returned to the caller via the `X-Request-ID` response header, so an on-call engineer can match a user-reported error back to specific log lines.
- Redaction (no raw agreement terms/PII in logs) is a call-site discipline documented in `docs/specs/logging.md`, not a machine-enforced scrubber — a future ticket could add one if log volume/authorship grows past what code review alone can catch.
- MCP tool invocations (`app/mcp_server.py`) get the same correlation-id treatment via an explicit `new_correlation_id()` context manager, since there's no ASGI request/response cycle to hang middleware off of on that transport.
- `CorrelationIdMiddleware` (not a separate `app.main` handler) owns the catch-all 500 response for unhandled exceptions — discovered during implementation that Starlette dispatches a bare-`Exception` handler to `ServerErrorMiddleware`, which sits outside user middleware and always re-raises after building its response, too late for a correlation-aware middleware downstream to react. See `docs/specs/logging.md` for the mechanics.

## Follow-ups

None required by this ticket. A future ticket introducing a second service or an external log aggregator should revisit the stdlib-only choice and the "no external shipping" scope on their own merits.
