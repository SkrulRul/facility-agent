from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_agreement_repository
from app.main import app
from app.repositories.in_memory_agreement_repository import InMemoryAgreementRepository

TEST_ANALYST_API_KEY = "test-analyst-key"
TEST_RISK_OFFICER_API_KEY = "test-risk-officer-key"

_TEST_ROLE_KEYS = {
    TEST_ANALYST_API_KEY: "loan_operations_analyst",
    TEST_RISK_OFFICER_API_KEY: "credit_risk_officer",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A TestClient backed by a FRESH in-memory repository per test function.

    Overrides the singleton repository provider so tests are isolated from each
    other and from the process-level store. Also monkeypatches app.main's
    bare-name get_engine (called directly by the lifespan handler, outside
    FastAPI's Depends() graph, so app.dependency_overrides can't reach it —
    same seam as app/mcp_server.py's bare-name pattern, see
    docs/specs/mcp_server.md) so tests never depend on an ambient DATABASE_URL
    that no test here actually intends to exercise.

    Defaults to authenticating as the Loan Operations Analyst (full read+write
    access, matching this fixture's pre-Phase-9 scope) via a default X-API-Key
    header, so the ~40 existing call sites across the test suite need no
    changes — see docs/specs/auth.md. Tests targeting role-specific behavior
    (tests/test_auth.py) override the header per-request instead.
    """
    repository = InMemoryAgreementRepository()
    app.dependency_overrides[get_agreement_repository] = lambda: repository
    monkeypatch.setattr("app.main.get_engine", lambda: None)
    monkeypatch.setattr("app.auth._load_role_keys", lambda: _TEST_ROLE_KEYS)
    with TestClient(app, headers={"X-API-Key": TEST_ANALYST_API_KEY}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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


def amortizing_repayment() -> dict[str, Any]:
    """Installments sum to 1_000_000 (the default facility_amount)."""
    return {
        "type": "amortizing",
        "installments": [
            {"due_date": "2026-01-15", "principal_amount": "400000.00"},
            {"due_date": "2027-01-15", "principal_amount": "600000.00"},
        ],
    }


def financial_covenant(covenant_id: str | None = None) -> dict[str, Any]:
    return {
        "type": "financial",
        "id": covenant_id or str(uuid4()),
        "description": "Leverage ratio must stay at or below 3.5x",
        "financial_metric": "leverage_ratio",
        "operator": "<=",
        "threshold": "3.5",
        "frequency": "quarterly",
    }


def non_financial_covenant(covenant_id: str | None = None) -> dict[str, Any]:
    return {
        "type": "non_financial",
        "id": covenant_id or str(uuid4()),
        "category": "reporting",
        "description": "Quarterly management accounts within 45 days",
    }


def build_agreement_payload(**overrides: object) -> dict[str, Any]:
    """A valid create-agreement JSON payload; override any field via kwargs."""
    payload: dict[str, Any] = {
        "agreement_date": "2025-01-01",
        "effective_date": "2025-01-15",
        "maturity_date": "2030-01-15",
        "currency": "USD",
        "facility_amount": "1000000.00",
        "facility_type": "term_loan",
        "borrower_id": str(uuid4()),
        "lender_ids": [str(uuid4())],
        "facility_agent_id": None,
        "interest_terms": fixed_interest_terms(),
        "repayment_schedule": bullet_repayment(),
        "covenants": [financial_covenant(), non_financial_covenant()],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def agreement_payload() -> dict[str, Any]:
    return build_agreement_payload()
