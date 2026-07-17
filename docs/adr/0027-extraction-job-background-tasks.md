# ADR-0027 — Extraction jobs: FastAPI `BackgroundTasks` + in-memory job store

**Status:** Accepted

## Decision

`ExtractionService.extract()` (`app/services/extraction_service.py`, built in an earlier phase, unreachable by any endpoint until this ticket) gets its first real caller via two new endpoints on `app/routers/extractions.py`:

- `POST /extractions` — validates `target_type` (`"term_sheet"` | `"covenant_waiver_notice"`, the only two extraction targets that exist) and `document_text`, creates an `ExtractionJob` (`app/services/extraction_job.py`) in `"pending"` status, schedules the actual extraction via `BackgroundTasks.add_task(...)`, and returns `202 Accepted` immediately with the job.
- `GET /extractions/{job_id}` — returns the job's current state (`pending` / `succeeded` / `failed`, plus `result` or `error_message`).

The job store (`InMemoryExtractionJobRepository`, `app/repositories/in_memory_extraction_job_repository.py`) is an in-process dict, mirroring `InMemoryAgreementRepository`'s shape. No new runtime dependency (no Celery, no Redis, no external queue).

## Drivers

- The ticket's acceptance criteria explicitly require submit-now/retrieve-later (mechanism left as an engineering decision) because `extract()` takes seconds and retries internally — a synchronous `POST` would hold the connection open for that whole duration.
- `docs/PRD.md` §6 states no performance requirement exists ("low-volume portfolio project"); §5 predates this ticket and says "no async workflows... in v1" — this ADR is the explicit, documented supersession of that line for this one endpoint, not an oversight.
- The project's current packaging (`docker-entrypoint.sh` runs plain `uv run fastapi run app/main.py`, no `--workers`) is single-process — `BackgroundTasks` executing in the same process as the request that scheduled them, backed by an in-process dict, has no cross-process visibility gap under that deployment shape.

## Alternatives considered

- **A real task queue (Celery/arq + Redis).** Rejected — no existing message-broker infrastructure in this project, and PRD §6's "no performance requirement" gives no forcing justification for the added operational surface (a broker to run, a worker process to deploy, retry/dead-letter semantics to configure) for two low-volume endpoints.
- **Client-side polling against a synchronous, blocking `POST` with a long client-side timeout.** Rejected — doesn't satisfy the acceptance criterion that the analyst isn't forced to hold a connection open; also fragile against `ExtractionService`'s internal retries pushing latency past typical HTTP client/proxy timeouts.
- **Webhook/callback delivery instead of polling.** Not chosen for v1 — polling is the simpler of the two mechanisms the ticket explicitly allowed ("polling, callback, or otherwise"), and there's no caller-supplied callback URL concept anywhere else in this API. Revisit if a concrete caller needs push delivery.
- **A `Protocol` for the job repository, matching `AgreementRepository`'s shape.** Rejected for now — only one implementation exists (in-memory); this project's own bar for introducing an interface is two concrete consumers today, not "the existing pattern used it." `InMemoryExtractionJobRepository` is a plain concrete class. Revisit (extract a `Protocol`) if a durable/Postgres-backed job store ever becomes a real second consumer.

## Why chosen

`BackgroundTasks` + an in-memory store is the smallest change that satisfies every acceptance criterion, adds zero new runtime dependencies, and matches the project's existing "low-volume, single-process" posture rather than introducing infrastructure with no current requirement driving it.

## Consequences

- **Jobs do not survive a process restart, and are not visible across multiple worker processes.** A job created by one worker is invisible to a `GET` handled by a different worker. This is an accepted, documented limitation for v1, not a silent gap — it holds only because the current deployment (`docker-entrypoint.sh`) runs a single process with no `--workers` flag. If a future ticket introduces multi-worker or multi-replica deployment, this ADR's premise breaks and the job store needs an external, shared backend (e.g. Postgres-backed, mirroring `AgreementRepository`'s `DATABASE_URL`-gated backend selection from ADR-0019) — at that point, extract the `Protocol` deferred above.
- **Correlation ids are per-job, not inherited from the submitting request.** `BackgroundTasks` scheduled via `add_task()` execute after `BaseHTTPMiddleware.dispatch()` has already returned (confirmed against `docs/specs/logging.md`'s own explanation of why `CorrelationIdMiddleware` catches exceptions internally, for the same underlying reason) — by the time the background task runs, the submitting request's correlation-id contextvar has already been reset. `ExtractionJobService.run()` therefore binds its own correlation id via `new_correlation_id()`, the same pattern `app/mcp_server.py` already uses for its non-HTTP-request-scoped tool invocations. The `job_id` (present in every log line across both the submission and the background execution) is the actual correlating key across this async boundary, not the HTTP correlation id.
- **Failure messages are deliberately generic, not exception-specific internals.** `ExtractionJobService.run()` maps `ExtractionError` / `ExtractionTransportError` / `ExtractionResponseShapeError` to three distinct, actionable messages, and any other unmodeled exception to one generic message — logged with `exc_info=True` server-side, never echoed to the client. This is the same posture `app/mcp_server.py` takes with `mask_error_details=True` (ADR-0018), applied by hand here since there's no FastMCP-style app-wide masking switch for a plain FastAPI route.
- **`ExtractionJobNotFoundError` does not subclass `AgreementService`'s `DomainNotFoundError`.** `app/services/agreement_service.py` (which defines `DomainNotFoundError`) imports `app.routers.schemas` for its request DTOs; `app.routers.schemas` now imports extraction DTOs' shared types from `app/services/extraction_job.py`. Subclassing `DomainNotFoundError` there would close a circular import. Instead, `app/main.py` registers `_domain_not_found_handler` for both exception types independently — same 404 behavior, no shared base class required.
- **Extraction jobs are not part of the audited `FacilityAgreement` aggregate.** They carry no `borrower_id`/agreement linkage and are not written through `AgreementRepository` — a deliberate scope boundary matching the ticket's silence on linking an extraction's result back to a specific agreement (out of scope: "editing/correcting extracted data before it's saved" implies no save-to-agreement path exists yet at all).

## Follow-ups

- If a future ticket needs the extracted result to seed or update a `FacilityAgreement` (the natural next step after this one), that's new scope requiring its own spec — this ticket explicitly stops at "retrieve the validated, structured result."
- If multi-worker/multi-replica deployment becomes a real requirement, revisit the in-memory job store per the Consequences section above.
