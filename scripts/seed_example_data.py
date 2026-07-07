"""Populate a running facility-agent instance with example data via its HTTP API.

Usage:
    uv run fastapi dev                      # in one terminal
    uv run python scripts/seed_example_data.py [--base-url http://127.0.0.1:8000]

Talks to the API only (POST /agreements, .../test-results, .../default-events) — no
direct app/repository imports, since the whole point is exercising the same endpoints
a real client would use, against whatever process is listening on --base-url.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Any
from uuid import uuid4

import httpx


def fixed_interest_terms() -> dict[str, Any]:
    return {"type": "fixed", "rate_pct": "5.25", "day_count_convention": "ACT/360"}


def floating_interest_terms() -> dict[str, Any]:
    return {
        "type": "floating",
        "reference_rate": "SOFR",
        "margin_pct": "1.50",
        "reset_frequency": "quarterly",
        "day_count_convention": "ACT/360",
    }


def bullet_repayment() -> dict[str, Any]:
    return {"type": "bullet"}


def amortizing_repayment(total: str, first: str, second: str) -> dict[str, Any]:
    return {
        "type": "amortizing",
        "installments": [
            {"due_date": "2027-06-15", "principal_amount": first},
            {"due_date": "2028-06-15", "principal_amount": second},
        ],
    }


def financial_covenant(covenant_id: str) -> dict[str, Any]:
    return {
        "type": "financial",
        "id": covenant_id,
        "description": "Leverage ratio must stay at or below 3.5x",
        "financial_metric": "leverage_ratio",
        "operator": "<=",
        "threshold": "3.5",
        "frequency": "quarterly",
    }


def non_financial_covenant() -> dict[str, Any]:
    return {
        "type": "non_financial",
        "id": str(uuid4()),
        "category": "reporting",
        "description": "Quarterly management accounts within 45 days",
    }


def post(client: httpx.Client, path: str, json: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=json)
    if response.is_error:
        print(f"FAILED POST {path}: {response.status_code} {response.text}", file=sys.stderr)
        response.raise_for_status()
    body: dict[str, Any] = response.json()
    return body


def seed(client: httpx.Client) -> None:
    # 1. Simple bilateral term loan, fixed rate, bullet repayment — stays "draft".
    healthy_covenant_id = str(uuid4())
    healthy = post(
        client,
        "/agreements",
        {
            "agreement_date": "2025-01-01",
            "effective_date": "2025-01-15",
            "maturity_date": "2030-01-15",
            "currency": "USD",
            "facility_amount": "1000000.00",
            "facility_type": "term_loan",
            "borrower_id": str(uuid4()),
            "lender_ids": [str(uuid4())],
            "interest_terms": fixed_interest_terms(),
            "repayment_schedule": bullet_repayment(),
            "covenants": [financial_covenant(healthy_covenant_id), non_financial_covenant()],
        },
    )
    print(f"Created agreement (healthy, draft): {healthy['id']}")

    post(
        client,
        f"/agreements/{healthy['id']}/covenants/{healthy_covenant_id}/test-results",
        {"test_date": str(date.today()), "result": "pass", "tested_by": "seed-script"},
    )
    print("  Recorded a passing covenant test result")

    # 2. Syndicated revolving credit, floating rate, amortizing schedule, in breach.
    breaching_covenant_id = str(uuid4())
    breaching = post(
        client,
        "/agreements",
        {
            "agreement_date": "2024-06-01",
            "effective_date": "2024-06-15",
            "maturity_date": "2029-06-15",
            "currency": "EUR",
            "facility_amount": "5000000.00",
            "facility_type": "revolving_credit",
            "borrower_id": str(uuid4()),
            "lender_ids": [str(uuid4()), str(uuid4())],
            "facility_agent_id": str(uuid4()),
            "interest_terms": floating_interest_terms(),
            "repayment_schedule": amortizing_repayment("5000000.00", "2000000.00", "3000000.00"),
            "covenants": [financial_covenant(breaching_covenant_id)],
        },
    )
    print(f"Created agreement (syndicated, in covenant breach): {breaching['id']}")

    post(
        client,
        f"/agreements/{breaching['id']}/covenants/{breaching_covenant_id}/test-results",
        {"test_date": str(date.today()), "result": "fail", "tested_by": "seed-script"},
    )
    print("  Recorded a failing covenant test result (in_covenant_breach=true)")

    # 3. Term loan with an outstanding payment default -> status becomes "defaulted".
    defaulted = post(
        client,
        "/agreements",
        {
            "agreement_date": "2023-03-01",
            "effective_date": "2023-03-15",
            "maturity_date": "2028-03-15",
            "currency": "GBP",
            "facility_amount": "2500000.00",
            "facility_type": "term_loan",
            "borrower_id": str(uuid4()),
            "lender_ids": [str(uuid4())],
            "interest_terms": fixed_interest_terms(),
            "repayment_schedule": bullet_repayment(),
            "covenants": [non_financial_covenant()],
        },
    )
    print(f"Created agreement (defaulted): {defaulted['id']}")

    post(
        client,
        f"/agreements/{defaulted['id']}/default-events",
        {"event_type": "payment_default", "occurred_date": str(date.today())},
    )
    print("  Recorded a continuing default event (status=defaulted)")

    # 4. Agreement already past maturity_date -> status becomes "matured".
    matured = post(
        client,
        "/agreements",
        {
            "agreement_date": "2015-01-01",
            "effective_date": "2015-01-15",
            "maturity_date": "2020-01-15",
            "currency": "USD",
            "facility_amount": "750000.00",
            "facility_type": "term_loan",
            "borrower_id": str(uuid4()),
            "lender_ids": [str(uuid4())],
            "interest_terms": fixed_interest_terms(),
            "repayment_schedule": bullet_repayment(),
        },
    )
    print(f"Created agreement (matured): {matured['id']}")

    print("\nDone. Fetch the list to see all four:")
    print(f"  curl {client.base_url}/agreements")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError as exc:
            print(
                f"Could not reach {args.base_url}/health — is the server running "
                f"(`uv run fastapi dev`)? ({exc})",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc

        seed(client)


if __name__ == "__main__":
    main()
