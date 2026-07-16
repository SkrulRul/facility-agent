# ADR-0026 — Role-based authentication via static API keys

**Status:** Accepted

## Decision

Every route under `app/routers/agreements.py` requires a valid `X-API-Key` header. `app/auth.py` maps each configured key to exactly one role (`loan_operations_analyst` | `credit_risk_officer`) via `AuthSettings` (`app/config.py`). A missing or unrecognized key raises HTTP 401 (`get_current_identity`). Both roles may call read (`GET`) endpoints; only `loan_operations_analyst` may call write (`POST`) endpoints — `require_role("loan_operations_analyst")` raises HTTP 403 otherwise. `GET /health` is deliberately left unauthenticated (infra liveness probe, no business data).

Keys are provisioned out-of-band as comma-separated environment variables, one list per role — there is no login endpoint, token issuance, or account model.

## Drivers

- The PRD (§2) defines two actors — Loan Operations Analyst (read/write) and Credit Risk Officer (read-only) — but v1 shipped with no enforcement at all, a documented gap that must close before the extraction endpoint (TICKET-10) ships.
- Self-service sign-up, password reset, and account management are explicitly out of scope for this ticket — ruling out any mechanism that implies a user-account store or credential lifecycle.
- Multi-tenant separation and per-resource permissions are also out of scope — only two coarse roles need to be distinguished, not individual identities.
- This is an internal system of record, not a public-facing product; personnel are provisioned by ops, not self-service.

## Alternatives considered

- **JWT (self-issued or third-party IdP).** Rejected — requires a token-issuance path (login endpoint or IdP integration) that nothing in this ticket asks for, plus signing-key management and expiry/refresh handling. Pure overhead for a system with no account model.
- **OAuth2 (Authorization Code / Client Credentials).** Rejected for the same reason, plus it assumes a client registration and consent flow this internal tool has no use for.
- **Session cookies.** Rejected — implies a login form and server-side session store; this is an API consumed by services/analysts, not a browser session in the PRD's scope.
- **HTTP Basic auth.** Considered — functionally similar to API keys (a static credential per identity) but conventionally pairs a username with a low-entropy password; an opaque API key is the more standard shape for a non-interactive API client and avoids inventing a password policy.

## Why chosen

Static API keys are the minimum mechanism that satisfies every acceptance criterion (401 without credentials, role carried by the authenticated identity, 403 on role mismatch) without introducing infrastructure (token issuance, account storage, session state) that no in-scope requirement calls for. It composes with FastAPI's existing `Depends()` graph the same way `app/dependencies.py` already does.

## Consequences

- Key rotation and revocation are manual (edit the env var and redeploy) — acceptable for the current personnel scale; would need revisiting if the roster grows large enough to make blanket rotation costly.
- Role is coarse (two literals) — per-resource permissions (e.g. "Analyst A only sees Analyst A's agreements") remain unimplemented by design, per this ticket's explicit scope boundary.
- `app/mcp_server.py` is untouched: it's a separate stdio transport (no HTTP status codes apply) and today exposes only two read-only tools, so there is no write path to protect. If write tools are ever added there, this ADR's role model should extend to gate them too.
- Keys are secrets: `AuthSettings` fields are `SecretStr`-backed and must never be logged (consistent with `docs/specs/logging.md`'s existing rule against logging raw input).
