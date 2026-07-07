from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_agreement_repository
from app.main import app
from app.repositories.agreement_repository import InMemoryAgreementRepository


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient backed by a FRESH in-memory repository per test function.

    Overrides the singleton repository provider so tests are isolated from each
    other and from the process-level store.
    """
    repository = InMemoryAgreementRepository()
    app.dependency_overrides[get_agreement_repository] = lambda: repository
    with TestClient(app) as test_client:
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
