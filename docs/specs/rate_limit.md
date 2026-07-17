# `rate_limit` — Feature Spec

Covers `app/rate_limit.py`, introduced in Phase 10 (TICKET-11). See
[ADR-0028](../adr/0028-per-identity-fixed-window-rate-limiting.md) for the
full decision record.

## Scope

Caps the number of `POST /extractions` calls a single authenticated identity
may make in a rolling configuration window, so that no one client (or bug,
or retry loop) can cause unbounded spend against the metered third-party LLM
API `ExtractionService` calls (ADR-0027). No other endpoint is rate limited
by this ticket — `GET /extractions/{job_id}` and every route under
`app/routers/agreements.py` are unaffected.

## Mechanism

An in-memory, per-process fixed-window request counter
(`InMemoryRateLimiter`), keyed by `Identity.key_fingerprint`
(`app/auth.py`) rather than by role — see ADR-0028 for why role-level
bucketing would violate the "not a single global ceiling shared by all
users" requirement. No new runtime dependency (no Redis, no `slowapi`) —
mirrors ADR-0027's posture for the extraction job store: smallest change
that satisfies the requirement, matching this project's single-process
deployment shape (`docker-entrypoint.sh` runs `uv run fastapi run
app/main.py`, no `--workers`).

`RateLimitSettings` (`app/config.py`) holds the two tunables:

| Field | Default | Meaning |
|---|---|---|
| `extraction_rate_limit_max_requests` | `20` | Max `POST /extractions` calls per identity per window |
| `extraction_rate_limit_window_seconds` | `3600` | Window length, in seconds |

These are proposed engineering defaults per the ticket's "exact numbers to
be proposed by engineering" note — tunable via environment variables
without a code change; Product confirmation of the final numbers is a
follow-up, not a blocker for this ticket.

## Dependencies

| Name | Behavior |
|---|---|
| `get_rate_limiter` | `@lru_cache` factory. Builds one process-lifetime `InMemoryRateLimiter` from `RateLimitSettings()` — mirrors `app/auth.py`'s `_load_role_keys()` caching pattern. Overridable per-test via `app.dependency_overrides` (like `app/dependencies.py`'s `get_agreement_repository`). |
| `enforce_extraction_rate_limit` | FastAPI dependency. Depends on `get_current_identity` (reused via FastAPI's per-request dependency cache — no extra auth cost) and `get_rate_limiter`. Calls `InMemoryRateLimiter.check(identity.key_fingerprint)`; if it returns a retry-after duration, raises `HTTPException(429, ...)` with a `Retry-After` header (integer seconds) and a human-readable `detail` message. Otherwise returns `None` and the request proceeds. |

## Wiring

`app/routers/extractions.py`'s `POST ""` handler carries
`dependencies=[Depends(enforce_extraction_rate_limit)]` at the route level
(not on the `APIRouter(...)` itself, which would also gate `GET
/extractions/{job_id}` — out of scope for this ticket).

## Testing

`tests/conftest.py`'s `client` fixture overrides `get_rate_limiter` with a
fresh, generously-sized `InMemoryRateLimiter` per test function, so the
`@lru_cache`'d process-lifetime limiter never leaks request counts across
tests (mirrors the existing `get_agreement_repository` override).
`tests/test_rate_limit.py` covers the limiter unit behavior (allow up to
max, block after, window reset), the HTTP 429 + `Retry-After` path via a
small `get_rate_limiter` override, per-identity isolation (two distinct
analyst API keys have independent windows), and that `GET
/extractions/{job_id}` is never rate limited.

## Out of scope (this ticket)

- Per-customer/tier-configurable limits — a single flat limit for all
  authenticated users.
- Rate limiting any endpoint other than `POST /extractions`.
- Cross-process/cross-replica limit enforcement — same accepted limitation
  as ADR-0027's job store; revisit together if multi-worker deployment is
  ever introduced.
- Final numeric threshold confirmation with Product — the defaults above
  are engineering's proposal, tunable via env var.
