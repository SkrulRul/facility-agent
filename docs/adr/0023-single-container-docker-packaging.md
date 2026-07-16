# ADR-0023 — Single-container Docker packaging, external Postgres

**Status:** Accepted

## Decision

One API-only `Dockerfile` builds and runs the API. It does not bundle or orchestrate a database — `DATABASE_URL` is supplied externally at `docker run` time, pointing at a Postgres instance the caller already provisioned. No `docker-compose.yml` exists in this repo.

The image's entrypoint (`docker-entrypoint.sh`) conditionally runs `uv run alembic upgrade head` before starting the server, but only when `DATABASE_URL` is set — an unset `DATABASE_URL` means the in-memory backend (ADR-0019), which has no schema to migrate.

## Drivers

- `DATABASE_URL`-presence backend selection (ADR-0019) already treats Postgres as externally supplied to the process — a bundled compose Postgres would just be a second, redundant way to provide the same thing a reviewer's own instance already provides.
- A reviewer following "clone, `docker build`, `docker run`" expects the container to be immediately usable against whatever Postgres they point it at — an image that starts but 500s on the first DB-backed request because migrations never ran would fail that expectation silently.

## Alternatives considered

- **`docker-compose.yml` bundling Postgres.** Rejected — explicitly out of scope for this ticket. Compose lifecycle/volume management (data persistence across restarts, network wiring, healthchecks) is real scope this project doesn't need to own; the project already assumes "bring your own Postgres" per ADR-0019, and a reviewer evaluating this repo is expected to have their own database available.
- **No migration step in the image; document `alembic upgrade head` as a manual pre-run step instead.** Rejected — a reviewer running `docker run -e DATABASE_URL=...` following the README's documented one-command flow would hit an unexplained 500 on first request. An automatic, `DATABASE_URL`-gated entrypoint migration is the only version of "one command" that's actually true.

## Consequences

- The image is slightly more complex than a bare `CMD` (one entrypoint script), but is genuinely runnable against a fresh external Postgres — the entire point of this acceptance criterion.
- No connection pooling/lifecycle concerns beyond what `app/main.py`'s existing `lifespan` handler already manages (ADR-0020) — the container doesn't add a second database-management layer.
- If a future ticket needs a fully self-contained local dev environment (bundled Postgres, seed data, hot reload), that's a new decision requiring its own ADR — not a reversal of this one.

## Follow-ups

None required by this ticket.
