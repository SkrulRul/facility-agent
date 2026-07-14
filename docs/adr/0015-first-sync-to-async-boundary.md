# ADR-0015 — First sync-to-async boundary: ExtractionService

**Status:** Accepted

## Decision

`ExtractionService` (`app/services/extraction_service.py`) is `async` — the sole async surface in `app/`. It calls the Anthropic API via structured outputs (`messages.create(output_config=...)`).

## Drivers

- The Anthropic API call is real network I/O, unlike Phase 2's in-memory dict repository (ADR-0014).
- The Anthropic SDK's async client (`AsyncAnthropic`) is the idiomatic path for awaited I/O.
- Keeping the retry-with-correction loop non-blocking avoids holding a thread for the duration of multiple sequential API round-trips.

## Alternatives considered

- **Make the whole stack async.** Rejected — no I/O justifies it elsewhere in `app/`; would contradict ADR-0014 for zero benefit.
- **Keep sync, offload the SDK call to a thread.** Rejected — fights the SDK's async-native design and adds a thread-pool hop for no gain.

## Why chosen

Narrowest possible async footprint at the one genuine I/O boundary. This narrows ADR-0014's scope rather than overturning it: ADR-0014 already anticipated "an LLM API call in Phase 3" as a case that should be evaluated for async on its own merits.

## Contingent, not permanent

The "async is contained to `ExtractionService` and does not propagate" property holds **only because no endpoint calls `extract()` today**. `await` is legal solely inside an `async def`, so the moment any future FastAPI route calls `await extraction_service.extract(...)` — directly or transitively — that route handler **must** itself become `async def`; there is no sync bridge that keeps the boundary contained. This is a forward-looking caveat, not a new decision: the containment is conditional on the current no-caller state, and this is the exact trigger that ends it.

## Consequences

- First `async` in `app/`; adds `pytest-asyncio` (`asyncio_mode=auto`).
- Tests inject a contract-enforcing fake client (`tests/extraction/conftest.py`) so no test path touches a live API key.
- Three distinct failure exceptions surface: `ExtractionError` (validation exhaustion), `ExtractionTransportError` (SDK transport exhaustion), and `ExtractionResponseShapeError` (malformed response content despite a successful call) — kept separate so a future endpoint's exception handler can map each to a different HTTP status (e.g. 422 / 503 / 502).

## Follow-ups

- If a future extraction endpoint appears: (a) the route handler goes `async def` per the caveat above, and (b) it is the trigger to consider a string-keyed dispatch registry as a thin wrapper over `extract()` (deferred per the RALPLAN-DR consensus, not invalidated).
