# `logging` — Feature Spec

Covers `app/logging.py`, introduced in Phase 8. See [ADR-0025](../adr/0025-structured-logging-correlation-ids.md) for the full decision record.

## Scope

Structured, correlated request logging so an on-call engineer can reconstruct what happened for a single request from logs alone, without reproducing locally. Stdout only — no external log aggregator, no distributed tracing (both explicitly out of scope for this ticket; single-service system today).

## Mechanism

- **Correlation id:** a `contextvars.ContextVar[str | None]` holds the current request's id. `CorrelationIdMiddleware` (Starlette `BaseHTTPMiddleware`) generates a fresh `uuid4().hex` at the start of every HTTP request, sets the contextvar, calls `call_next`, stamps the same id on the `X-Request-ID` response header, and resets the contextvar in a `finally` block. The id is **always server-generated** — an inbound `X-Request-ID`/similar header is never trusted or echoed, since nothing upstream is authenticated to set log-correlation identity for this single-service system.
- **Non-HTTP paths (MCP tools):** `new_correlation_id()` is a context manager that generates and sets a fresh id for the duration of the `with` block (used once per MCP tool invocation in `app/mcp_server.py`), resetting on exit including on exception.
- **Propagation to nested calls:** because the id lives in a contextvar (not a function parameter), any code running within the same async task — service layer, repository layer, exception handlers — picks it up automatically via `_CorrelationIdFilter`, a `logging.Filter` attached to the root handler that stamps `record.correlation_id` from the contextvar (or `"-"` if unset, e.g. at import time) on every `LogRecord` before formatting.
- **Format:** `_JsonFormatter` (a `logging.Formatter` subclass) renders one JSON object per line to stdout: `timestamp`, `level`, `logger`, `message`, `correlation_id`, any caller-supplied `extra=` fields, and `exception` (type + message + formatted traceback) when `record.exc_info` is set.
- **Setup:** `configure_logging(level: str)` is idempotent (clears and re-attaches handlers on the root logger) so it's safe to call from both `app/main.py` (once, at import time) and test setup. Level comes from `LogSettings.log_level` (`app/config.py`, env-overridable, default `INFO`).
- **Logger access:** `get_logger(name: str) -> logging.Logger` is a thin wrapper over `logging.getLogger(name)` — the single choke point call sites use, in case the underlying implementation ever changes.

## Redaction rule (binding on every log call site added under this spec)

Log calls pass **identifiers only** — `agreement_id`, `borrower_id`, `covenant_id`, `status`, exception type/message — via the standard `extra={...}` mechanism. They must never pass a domain object's `model_dump()`, `str(agreement)`, or any field carrying facility terms (`rate_pct`, `margin_pct`, `facility_amount`, installment amounts) or party PII (`legal_name`, `lei`, `jurisdiction`). This is a code-review discipline, not a machine-enforced filter — there is no PII-scrubbing formatter in scope for this ticket.

## Call sites

- `app/logging.py`: `CorrelationIdMiddleware` is also the catch-all for unhandled exceptions — it wraps `call_next()` in a try/except, logs at `ERROR` (correlation id + exception type + `exc_info=True`) and returns a generic `{"detail": "internal server error"}` 500 on failure. This is deliberate, not incidental: Starlette routes a bare-`Exception` handler registered via `app.add_exception_handler(Exception, ...)` to `ServerErrorMiddleware`, which sits *outside* all user middleware and always re-raises after building its response (`# We always continue to raise the exception` in its source) — by the time that handler would run, `CorrelationIdMiddleware`'s `with new_correlation_id():` block has already unwound and reset the contextvar, and the exception has already propagated past the code that would stamp `X-Request-ID` on the response. Catching inside the middleware itself is the only way to keep the correlation id live for both the log line and the response header. `app/main.py` registers no handler for the bare `Exception` type.
- `app/main.py`: `app.add_middleware(CorrelationIdMiddleware)`; `configure_logging()` called at module import. The existing `DomainNotFoundError` (404) and `ValidationError` (422) handlers log at `WARNING` with the identifiers they already have on hand (no new data exposure — these handlers never touch raw domain payloads today). These work correctly without the middleware-catch-all workaround because `add_exception_handler` for a *specific* type is routed to `ExceptionMiddleware`, which sits *inside* user middleware — `call_next()` returns the built response normally, it never raises past `CorrelationIdMiddleware`.
- `app/mcp_server.py`: both tools log invocation start/success at `INFO` and `AgreementNotFoundError`/unexpected exceptions at `WARNING`/`ERROR` respectively, scoped inside `new_correlation_id()`, before re-raising as `ToolError` per the existing error-masking contract (see `docs/specs/mcp_server.md`).

## Testing

`tests/test_logging.py` covers the formatter, filter, and contextvar behavior as pure unit tests, plus `TestClient` + `caplog` integration tests asserting: the `X-Request-ID` response header is present and matches the correlation id on emitted log records; two sequential requests get different ids; a 404/422/500 path logs at the right level with the right identifiers; a redaction regression test asserting a create-agreement request's log output never contains payload values from `rate_pct` or party PII fields. `tests/test_mcp_server.py` gets one additional test asserting a tool invocation's log output is correlated and identifier-only.

## Explicitly out of scope (this ticket)

- Shipping logs to Datadog/ELK/CloudWatch or any external aggregator.
- Distributed tracing / trace-context propagation across services.
- Honoring or trusting an inbound `X-Request-ID`-style header from the caller.
- A third-party structured-logging library (`structlog` etc.) — stdlib `logging` is sufficient at this scope.
- Machine-enforced PII/secret scrubbing of log payloads — the redaction rule above is a discipline for call sites this ticket adds, not a general-purpose filter.
