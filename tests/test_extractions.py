from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.dependencies import get_extraction_service
from app.extraction_targets.covenant_waiver import CovenantWaiverNotice
from app.extraction_targets.term_sheet import TermSheetExtract
from app.main import app
from app.services.extraction_service import ExtractionTransportError
from tests.conftest import TEST_RISK_OFFICER_API_KEY


class _SucceedingExtractionService:
    async def extract(
        self, text: str, target_model: type[BaseModel], *, max_attempts: int = 3
    ) -> BaseModel:
        if target_model is TermSheetExtract:
            return TermSheetExtract(
                borrower_legal_name="Acme Corp",
                currency="USD",
                facility_amount=Decimal("1000000.00"),
                facility_type="term_loan",
                maturity_date=date(2030, 1, 1),
                interest_rate_pct=Decimal("5.0"),
            )
        return CovenantWaiverNotice(
            agreement_reference="AGR-001",
            waived_covenant_reference="COV-001",
            waiver_reason="Temporary liquidity shortfall",
            effective_date=date(2026, 1, 1),
        )


class _FailingExtractionService:
    async def extract(
        self, text: str, target_model: type[BaseModel], *, max_attempts: int = 3
    ) -> BaseModel:
        raise ExtractionTransportError("upstream unavailable")


@pytest.fixture
def succeeding_extraction_client(client: TestClient) -> TestClient:
    app.dependency_overrides[get_extraction_service] = lambda: _SucceedingExtractionService()
    return client


@pytest.fixture
def failing_extraction_client(client: TestClient) -> TestClient:
    app.dependency_overrides[get_extraction_service] = lambda: _FailingExtractionService()
    return client


def test_submit_extraction_returns_202_pending(succeeding_extraction_client: TestClient) -> None:
    response = succeeding_extraction_client.post(
        "/extractions",
        json={"target_type": "term_sheet", "document_text": "some term sheet text"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["target_type"] == "term_sheet"
    assert body["result"] is None
    assert body["error_message"] is None


def test_submit_and_poll_term_sheet_succeeds_with_result(
    succeeding_extraction_client: TestClient,
) -> None:
    submit_response = succeeding_extraction_client.post(
        "/extractions",
        json={"target_type": "term_sheet", "document_text": "some term sheet text"},
    )
    job_id = submit_response.json()["id"]

    poll_response = succeeding_extraction_client.get(f"/extractions/{job_id}")

    assert poll_response.status_code == 200
    body = poll_response.json()
    assert body["status"] == "succeeded"
    assert body["result"]["borrower_legal_name"] == "Acme Corp"
    assert body["error_message"] is None


def test_submit_and_poll_covenant_waiver_notice_succeeds(
    succeeding_extraction_client: TestClient,
) -> None:
    submit_response = succeeding_extraction_client.post(
        "/extractions",
        json={"target_type": "covenant_waiver_notice", "document_text": "some waiver letter"},
    )
    job_id = submit_response.json()["id"]

    poll_response = succeeding_extraction_client.get(f"/extractions/{job_id}")

    assert poll_response.status_code == 200
    body = poll_response.json()
    assert body["status"] == "succeeded"
    assert body["result"]["waived_covenant_reference"] == "COV-001"


def test_extraction_failure_gives_clear_message_not_stack_trace(
    failing_extraction_client: TestClient,
) -> None:
    submit_response = failing_extraction_client.post(
        "/extractions",
        json={"target_type": "term_sheet", "document_text": "some term sheet text"},
    )
    job_id = submit_response.json()["id"]

    poll_response = failing_extraction_client.get(f"/extractions/{job_id}")

    assert poll_response.status_code == 200
    body = poll_response.json()
    assert body["status"] == "failed"
    assert body["result"] is None
    assert body["error_message"] == (
        "The extraction service was temporarily unavailable. Please try submitting again."
    )
    assert "Traceback" not in body["error_message"]
    assert "ExtractionTransportError" not in body["error_message"]


def test_get_unknown_job_returns_404(client: TestClient) -> None:
    response = client.get(f"/extractions/{uuid4()}")

    assert response.status_code == 404


def test_submit_invalid_target_type_returns_422(client: TestClient) -> None:
    response = client.post(
        "/extractions",
        json={"target_type": "invoice", "document_text": "some text"},
    )

    assert response.status_code == 422


def test_submit_empty_document_text_returns_422(client: TestClient) -> None:
    response = client.post(
        "/extractions",
        json={"target_type": "term_sheet", "document_text": ""},
    )

    assert response.status_code == 422


def test_credit_risk_officer_cannot_submit_extraction(client: TestClient) -> None:
    response = client.post(
        "/extractions",
        json={"target_type": "term_sheet", "document_text": "some text"},
        headers={"X-API-Key": TEST_RISK_OFFICER_API_KEY},
    )

    assert response.status_code == 403


def test_credit_risk_officer_cannot_get_extraction(
    succeeding_extraction_client: TestClient,
) -> None:
    submit_response = succeeding_extraction_client.post(
        "/extractions",
        json={"target_type": "term_sheet", "document_text": "some text"},
    )
    job_id = submit_response.json()["id"]

    response = succeeding_extraction_client.get(
        f"/extractions/{job_id}",
        headers={"X-API-Key": TEST_RISK_OFFICER_API_KEY},
    )

    assert response.status_code == 403


def test_missing_api_key_returns_401(client: TestClient) -> None:
    response = TestClient(app).post(
        "/extractions",
        json={"target_type": "term_sheet", "document_text": "some text"},
    )

    assert response.status_code == 401
