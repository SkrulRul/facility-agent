# ADR-0028 — Per-identity fixed-window rate limiting on `POST /extractions`

**Status:** Accepted

## Decision

`POST /extractions` (`app/routers/extractions.py`) is capped at 20 requests
per authenticated identity per 60-minute fixed window
(`RateLimitSettings`, `app/config.py` — both values are env-overridable). A
client that exceeds the cap receives `HTTPException(429, ...)` with a
`Retry-After` header (integer seconds until the window resets) and a
human-readable `detail` message. Enforcement is an in-memory, per-process
fixed-window counter (`InMemoryRateLimiter`, `app/rate_limit.py`), keyed by
a new `Identity.key_fingerprint` field (`app/auth.py`) — a truncated SHA-256
hex digest of the raw `X-API-Key` value, never the raw key itself. No other
route is rate limited by this ticket.

## Drivers

- TICKET-11's acceptance criteria: a cap per authenticated identity per time
  window (exact numbers left to engineering), a standard 429 with retry
  guidance, and enforcement per identity — explicitly **not** a single
  global ceiling shared by all users.
- `ExtractionService.extract()` (ADR-0015, ADR-0027) is the only endpoint in
  this codebase that spends real, metered third-party API budget per call —
  every other route is free to call repeatedly.
- The ticket is explicit that this only makes sense once `POST /extractions`
  exists (ADR-0027, this project's TICKET-10) and once "per identity" means
  something (ADR-0026, TICKET-09's role-based API-key auth).

## Alternatives considered

- **Bucket by `Identity.role` instead of by API key.** Rejected. Every
  extraction call requires the `loan_operations_analyst` role
  (`require_role("loan_operations_analyst")`, `app/routers/extractions.py`),
  and `AuthSettings.loan_operations_analyst_api_keys` is a
  comma-separated list — multiple analysts, each with their own key, can
  share that role. Bucketing by role alone would give every analyst one
  shared budget, which is precisely the "single global ceiling shared by
  all users" the acceptance criteria rule out. Bucketing by the resolved
  key (via a fingerprint, not the raw secret) is the only granularity that
  actually distinguishes "one misbehaving integration" from the rest.
- **`slowapi` (or another Starlette rate-limiting library backed by the
  `limits` package).** Rejected for the same reason ADR-0027 rejected a
  real task queue for extraction jobs: no existing infrastructure
  requirement forces it, it pulls in a new runtime dependency and its own
  Redis-backable configuration surface, and a single flat per-identity
  fixed-window counter is a few dozen lines — well within this project's
  "smallest change that satisfies the requirement" posture (KISS/YAGNI).
- **Sliding-window log (store every request timestamp per identity).** More
  accurate at the window boundary than a fixed window, but requires
  per-identity timestamp lists pruned on every check, and the retry-after
  calculation (time until the oldest timestamp ages out) is more involved
  than a fixed window's `window_seconds - elapsed`. A flat 20/hour cap on a
  low-volume internal tool (PRD §6) doesn't need that precision; fixed
  window's boundary burst (up to 2x the nominal rate right at a window
  edge) is an accepted, documented trade for the simpler implementation.
- **Redis-backed counter.** Rejected — no existing cache/broker
  infrastructure in this project (same absence ADR-0027 already leaned on),
  and the current deployment is single-process (`docker-entrypoint.sh`, no
  `--workers`), so an in-process dict has no cross-process visibility gap
  under that shape.
- **A `Protocol` for the limiter, matching `AgreementRepository`'s shape.**
  Rejected for now — only one implementation exists (in-memory); this
  project's own bar for introducing an interface is two concrete consumers
  today, not "the existing pattern used one." `InMemoryRateLimiter` is a
  plain concrete class, same posture ADR-0027 took for the job repository.

## Why chosen

An in-memory, per-key, fixed-window counter is the smallest mechanism that
satisfies every acceptance criterion — real per-identity isolation, a
standard 429 with retry guidance, no global ceiling — without adding a new
runtime dependency or infrastructure this single-process, low-volume
project doesn't otherwise need.

## Consequences

- **Limits do not survive a process restart, and are not shared across
  multiple worker processes.** Same accepted limitation as ADR-0027's job
  store, for the same reason (single-process deployment today). If
  multi-worker/multi-replica deployment is ever introduced, both this
  limiter and the job store need an external, shared backend at the same
  time — revisit together.
- **Fixed-window boundary bursts.** A client can send up to
  `2 * extraction_rate_limit_max_requests` requests within a short span
  straddling a window boundary (e.g. 20 just before the window resets, 20
  more just after). Accepted for a flat, low-volume internal cap; revisit
  with a sliding window if this is ever a real problem in practice.
- **`Identity.key_fingerprint` is a one-way SHA-256 digest of the raw API
  key, truncated for log-friendliness.** It is safe to log (unlike the raw
  key, which `docs/specs/auth.md` already forbids logging) and is stable
  for the lifetime of a given provisioned key, which is all a rate-limit
  bucket key needs to be.
- **The 20/60min defaults are engineering's proposal, not a confirmed
  Product number.** Both are plain env-overridable settings
  (`RateLimitSettings`), so tuning them is a config change, not a code
  change — Product confirmation is an explicit follow-up, not a blocker for
  this ticket per its own acceptance criteria wording.

## Follow-ups

- Get the 20-requests/60-minute default confirmed (or replaced) by Product.
- If multi-worker/multi-replica deployment becomes a real requirement,
  revisit this ADR and ADR-0027 together — both need an external, shared
  backend at that point.
