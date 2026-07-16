# `auth` — Feature Spec

Covers `app/auth.py`, introduced in Phase 9. See [ADR-0026](../adr/0026-role-based-api-key-authentication.md) for the full decision record.

## Scope

Role-based access control for the HTTP API. Replaces the "no authentication/authorization" gap the PRD (§2, §7) explicitly documented as acceptable for v1 but not beyond. Two roles, matching the PRD's actors:

- `loan_operations_analyst` — read and write.
- `credit_risk_officer` — read only.

## Mechanism

A single `X-API-Key` request header. `AuthSettings` (`app/config.py`) holds two comma-separated key lists, one per role. `_load_role_keys()` (`app/auth.py`, `@lru_cache`) parses both into a single `dict[str, Role]` at first use — mirrors `app/dependencies.py`'s `get_engine()` caching pattern.

## Dependencies

| Name | Behavior |
|---|---|
| `get_current_identity` | FastAPI dependency. Reads `X-API-Key` (via `APIKeyHeader(auto_error=False)` so FastAPI never raises its own default-403-on-missing behavior). Missing header or a key not present in `_load_role_keys()` → `HTTPException(401, "Not authenticated")`. Otherwise returns an `Identity(role=...)`. |
| `require_role(*allowed_roles)` | Dependency factory. Depends on `get_current_identity`; if the resolved role isn't in `allowed_roles` → `HTTPException(403, "Forbidden")`; otherwise returns the `Identity` unchanged. |

## Wiring

`app/routers/agreements.py`'s `APIRouter` carries `dependencies=[Depends(get_current_identity)]` at construction — every route gets 401 enforcement with no per-route boilerplate. The three write handlers (`create_agreement`, `record_covenant_test_result`, `record_default_event`) additionally declare a `Depends(require_role("loan_operations_analyst"))` parameter for 403 enforcement. Read handlers (`list_agreements`, `get_agreement`) take no further dependency — any authenticated identity may call them.

`GET /health` (`app/main.py`) is deliberately **not** gated — it's an infra liveness probe with no business data, and gating it would break unauthenticated load-balancer/container health checks for no security benefit.

## Testing

`tests/conftest.py`'s `client` fixture monkeypatches `app.auth._load_role_keys` to a fixed test mapping and sets a default `X-API-Key` header (the test analyst key) on the `TestClient` instance — every pre-existing test authenticates as the Loan Operations Analyst by default, since that role's access matches the full endpoint scope those tests already exercised pre-Phase-9. `tests/test_auth.py` covers the role-specific and credential-failure paths explicitly: missing key, unknown key, Credit Risk Officer on read vs. write, Loan Operations Analyst on both.

## Out of scope (this ticket)

- Self-service sign-up, password reset, account management.
- Multi-tenant/organization separation.
- Per-resource permissions (e.g. an analyst restricted to their own agreements) — role-level access only.
- `app/mcp_server.py` — separate stdio transport, no HTTP status codes apply, and it exposes only read-only tools today (nothing to gate). See ADR-0026's Consequences for the revisit condition.
