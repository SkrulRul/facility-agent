# `health` — Feature Spec

Covers `app/routers/health.py`, introduced in Phase 11. See
[ADR-0029](../adr/0029-liveness-readiness-health-endpoints.md) for the full
decision record.

## Scope

Two unauthenticated, no-side-effect GET endpoints for operators (a
container orchestrator, a load balancer) to distinguish "is the process
alive" from "can this instance serve traffic right now":

- `GET /health` — liveness. Always `{"status": "ok"}`, 200, regardless of
  any downstream dependency.
- `GET /health/ready` — readiness. `{"status": "ok"}`, 200, when the
  service can serve traffic; `{"detail": "Service unavailable"}`, 503,
  otherwise.

Not covered: per-dependency health detail, alerting/paging integration —
both explicitly out of scope per the originating ticket.

## Mechanism

Readiness reuses the existing `get_engine()` DI seam
(`app/dependencies.py`, ADR-0019/0020):

- No `DATABASE_URL` configured (in-memory repository backend) → always
  ready. There is no database dependency to be unready for.
- `DATABASE_URL` configured → opens a pooled connection and runs a bare
  `SELECT 1`. A `SQLAlchemyError` during that check reports 503. No
  application tables are queried.

## Testing

`tests/test_health.py` covers all three states without a real Postgres
instance (ADR-0024 keeps Postgres out of CI): no DB configured, DB
reachable, and DB unreachable — the latter two via minimal fake
`AsyncEngine`/`AsyncConnection` doubles substituted through
`app.dependency_overrides[get_engine]`.
