# ADR-0029 — Liveness and readiness health endpoints

**Status:** Accepted

## Decision

Two unauthenticated GET endpoints, both defined in a new
`app/routers/health.py`:

- `GET /health` — liveness. Returns `{"status": "ok"}` unconditionally as
  long as the process is running. This is the same path and response shape
  the pre-existing inline `app/main.py` handler already used; it is moved
  into the new router, not renamed, so the one existing consumer/test needs
  no changes.
- `GET /health/ready` — readiness. Depends on the existing `get_engine()`
  seam (`app/dependencies.py`, ADR-0019/0020). If no `DATABASE_URL` is
  configured (in-memory backend), returns `{"status": "ok"}` unconditionally
  — there is no dependency to be unready for. If an engine is configured, it
  runs a single `SELECT 1` over a pooled connection; a `SQLAlchemyError`
  during that check returns `HTTPException(503)`.

Neither route carries an auth dependency — standard practice for
infrastructure health checks, and explicit in the ticket's acceptance
criteria.

## Drivers

- Ticket acceptance criteria: liveness independent of dependencies,
  readiness that becomes DB-aware once a real database exists, both
  unauthenticated and cheap.
- `get_engine()` (ADR-0019, `DatabaseSettings`) already exposes exactly the
  "is there a configured backend, and can I reach it" seam this needs — no
  new settings or plumbing required.
- The ticket explicitly scopes this to a binary healthy/unhealthy signal per
  endpoint, not a per-dependency dashboard.

## Alternatives considered

- **`/livez` / `/readyz` (or `/health/live` for symmetry with
  `/health/ready`).** Rejected. The existing `/health` path has one real
  consumer (`tests/test_health.py`) and no acceptance criterion demands a
  rename; keeping it in place is a smaller diff for the same behavior.
- **A dedicated health-check service/abstraction (e.g. a
  `HealthCheckService` with a list of pluggable checks).** Rejected —
  YAGNI. There is exactly one dependency to check today (the database), and
  it is already reachable through one existing DI seam. A registry of
  checks is speculative until a second dependency actually exists.
- **Reusing `AgreementRepository` (e.g. `list_all()`) as the readiness
  probe.** Rejected — it would run a real query against the agreements
  table, more expensive and more side-effect-prone than necessary; a bare
  `SELECT 1` on a pooled connection is the standard minimal-cost liveness
  probe for a SQL backend and doesn't touch application tables at all.

## Consequences

- Readiness is a no-op success when no `DATABASE_URL` is set — meaningful
  DB-aware behavior only exists once Phase 6's Postgres backend is
  configured, exactly as the ticket's notes anticipated.
- `GET /health/ready` opens and executes over a real pooled connection on
  every call. This is intentionally cheap (`SELECT 1`, no application
  tables), but it is not free — an orchestrator probing on the order of
  seconds should still keep readiness probes at a reasonable interval, not
  sub-second, to avoid needless connection churn.
- The 503 body carries no per-dependency detail (just `{"detail": "Service
  unavailable"}`), consistent with the ticket's binary-signal scope. A
  future per-dependency dashboard is an explicit non-goal here, not a gap.
