# ADR-0024 — CI scope: lint + typecheck + in-memory test suite only

**Status:** Accepted

## Decision

GitHub Actions runs `uv run poe check` (ruff lint, mypy, pyright, pytest) on every push and pull request to `main`. There is no Postgres service in CI, and `scripts/smoke_test_*.py` are never invoked automatically — both remain manual, by design.

## Drivers

- This matches the codebase's existing, deliberate "manual smoke test" pattern for every other genuine real-I/O boundary: `scripts/smoke_test_extraction.py` (live Anthropic API, ADR-0015), `scripts/smoke_test_mcp_server.py` (MCP subprocess), and `scripts/smoke_test_persistence.py` (live Postgres, ADR-0021) are all excluded from the automated pytest suite for the same reason — they require live external services CI shouldn't be provisioning credentials/infrastructure for on every push.
- `tests/test_postgres_agreement_repository.py` (confirmed by reading it) only unit-tests the private `_to_domain`/`_scalar_fields` helper functions against plain, unflushed `OrmFacilityAgreement` objects — it never opens a real database connection. The entire pytest suite already passes with zero live `DATABASE_URL`, so a CI Postgres service would add infrastructure for no test that needs it.

## Alternatives considered

- **Add a Postgres service container to CI, run the full suite against it.** Rejected — explicitly out of this ticket's scope. Would also require secrets/schema-migration bootstrapping (running `alembic upgrade head` against the service container before tests) that this ticket isn't chartered to build, for a test file that doesn't currently need it.
- **Run `scripts/smoke_test_persistence.py` in CI against a service container.** Rejected for the same reason, and because it would be the first automated test in this repo to depend on live external state — a real scope expansion, not a packaging/verification change.

## Consequences

- CI stays fast and secret-free — no `DATABASE_URL`, no Postgres service, no external API keys.
- The Postgres-backed path (real migrations, real query behavior) is verified only by the existing manual smoke scripts and by the Docker verification step in ADR-0023 — an accepted, documented gap, not an oversight.
- If a future ticket adds genuine Postgres-dependent test coverage (not just unit tests against ORM objects), CI scope should be revisited then, on its own merits.

## Follow-ups

None required by this ticket.
