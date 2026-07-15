"""Manual smoke test against a REAL Postgres database.

Not part of `uv run poe check` — automated CI coverage against a real
Postgres instance is explicitly out of scope for Phase 6 (see
.omc/specs/phase-6-persistence.md). This is the only artifact that proves
`AgreementRepository.update()` is genuinely durable-write-necessary end to
end (ADR-0021): the in-memory backend's reference-mutation semantics make
that property untestable there by construction.

Mirrors scripts/smoke_test_mcp_server.py's style/purpose for the MCP layer.

Requires DATABASE_URL to point at a real, reachable Postgres instance. Run
manually (as a module, like scripts/mcp_server_seeded.py — a plain
`python scripts/smoke_test_persistence.py` invocation fails to resolve the
`app` package, a pre-existing sys.path quirk shared with
scripts/smoke_test_extraction.py):
    DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname \\
        uv run python -m scripts.smoke_test_persistence

This script runs `alembic upgrade head` for you (never automatically —
only here, in this script's own explicit main()), then exercises all 5
agreement endpoints end-to-end through the real FastAPI app, wired to the
real PostgresAgreementRepository via DATABASE_URL. Each HTTP call opens a
fresh database session (see PostgresAgreementRepository), so every GET after
a write already proves durability across sessions — no separate process
needed to prove the point.
"""

from __future__ import annotations

import subprocess
import sys
from decimal import Decimal

from fastapi.testclient import TestClient

from app.config import DatabaseSettings
from app.main import app


def _run_migrations() -> None:
    print("Running `alembic upgrade head`...")
    result = subprocess.run(  # noqa: S603
        ["uv", "run", "alembic", "upgrade", "head"],  # noqa: S607
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("alembic upgrade head failed — see output above")
    print("Migrations applied.\n")


def main() -> None:
    if DatabaseSettings().database_url is None:
        print(
            "DATABASE_URL is not set. This script requires a real, reachable "
            "Postgres instance:\n"
            "    DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname "
            "uv run python -m scripts.smoke_test_persistence",
            file=sys.stderr,
        )
        raise SystemExit(1)

    _run_migrations()

    with TestClient(app) as client:
        agreement_payload = {
            "agreement_date": "2025-01-01",
            "effective_date": "2025-01-15",
            "maturity_date": "2030-01-15",
            "currency": "USD",
            "facility_amount": "1000000.00",
            "facility_type": "term_loan",
            "borrower_id": "00000000-0000-0000-0000-000000000001",
            "lender_ids": ["00000000-0000-0000-0000-000000000002"],
            "facility_agent_id": None,
            "interest_terms": {
                "type": "fixed",
                "rate_pct": "5.25",
                "day_count_convention": "ACT/360",
            },
            "repayment_schedule": {"type": "bullet"},
            "covenants": [
                {
                    "type": "financial",
                    "id": "00000000-0000-0000-0000-000000000003",
                    "description": "Leverage ratio must stay at or below 3.5x",
                    "financial_metric": "leverage_ratio",
                    "operator": "<=",
                    "threshold": "3.5",
                    "frequency": "quarterly",
                }
            ],
        }

        created = client.post("/agreements", json=agreement_payload)
        if created.status_code != 201:
            raise AssertionError(f"create failed: {created.status_code} {created.text}")
        agreement_id = created.json()["id"]
        print(f"create -> 201, agreement_id={agreement_id}")

        fetched = client.get(f"/agreements/{agreement_id}")
        if fetched.status_code != 200:
            raise AssertionError(f"get failed: {fetched.status_code} {fetched.text}")
        if Decimal(fetched.json()["facility_amount"]) != Decimal("1000000.00"):
            raise AssertionError(f"unexpected facility_amount: {fetched.json()}")
        print("get -> 200, facility_amount round-tripped correctly")

        listed = client.get("/agreements", params={"borrower_id": agreement_payload["borrower_id"]})
        if listed.status_code != 200 or agreement_id not in {
            item["id"] for item in listed.json()["items"]
        }:
            raise AssertionError(f"list failed to include created agreement: {listed.text}")
        print("list -> 200, created agreement present")

        covenant_id = agreement_payload["covenants"][0]["id"]
        test_result = client.post(
            f"/agreements/{agreement_id}/covenants/{covenant_id}/test-results",
            json={"test_date": "2026-03-31", "result": "pass", "tested_by": "smoke-test"},
        )
        if test_result.status_code != 201:
            raise AssertionError(f"record covenant test result failed: {test_result.text}")
        print("record covenant test result -> 201")

        default_event = client.post(
            f"/agreements/{agreement_id}/default-events",
            json={
                "event_type": "payment_default",
                "occurred_date": "2026-01-01",
                "remediation_status": "outstanding",
                "waiver_status": "none",
            },
        )
        if default_event.status_code != 201:
            raise AssertionError(f"record default event failed: {default_event.text}")
        print("record default event -> 201")

        # Fresh GET, opening a brand new DB session — proves update() durably
        # persisted both writes, not just that an in-process object reference
        # happened to still hold them.
        refetched = client.get(f"/agreements/{agreement_id}")
        body = refetched.json()
        if len(body["covenant_test_results"]) != 1:
            raise AssertionError(
                f"covenant test result did not durably persist: {body['covenant_test_results']}"
            )
        if len(body["default_events"]) != 1:
            raise AssertionError(f"default event did not durably persist: {body['default_events']}")
        print(
            "re-fetch (fresh session) -> covenant_test_results and default_events "
            "both durably persisted"
        )

    print(
        "\nOK — real Postgres round-trip verified: create, get, list, "
        "record covenant test result, record default event, and a fresh-session "
        "re-fetch all behaved correctly against a real database."
    )


if __name__ == "__main__":
    main()
