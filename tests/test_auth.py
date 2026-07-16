from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import TEST_RISK_OFFICER_API_KEY


def _risk_officer_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_RISK_OFFICER_API_KEY}


def test_missing_api_key_returns_401(client: TestClient) -> None:
    response = TestClient(app).get("/agreements")
    assert response.status_code == 401


def test_unknown_api_key_returns_401(client: TestClient) -> None:
    response = TestClient(app).get("/agreements", headers={"X-API-Key": "not-a-real-key"})
    assert response.status_code == 401


def test_credit_risk_officer_can_list_agreements(client: TestClient) -> None:
    response = client.get("/agreements", headers=_risk_officer_headers())
    assert response.status_code == 200


def test_credit_risk_officer_can_get_agreement(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    created = client.post("/agreements", json=agreement_payload)
    assert created.status_code == 201

    response = client.get(
        f"/agreements/{created.json()['id']}", headers=_risk_officer_headers()
    )
    assert response.status_code == 200


def test_credit_risk_officer_cannot_create_agreement(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    response = client.post(
        "/agreements", json=agreement_payload, headers=_risk_officer_headers()
    )
    assert response.status_code == 403


def test_credit_risk_officer_cannot_record_covenant_test_result(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    created = client.post("/agreements", json=agreement_payload)
    agreement_id = created.json()["id"]
    covenant_id = created.json()["covenants"][0]["id"]

    response = client.post(
        f"/agreements/{agreement_id}/covenants/{covenant_id}/test-results",
        json={"test_date": "2026-03-31", "result": "fail", "tested_by": "analyst"},
        headers=_risk_officer_headers(),
    )
    assert response.status_code == 403


def test_credit_risk_officer_cannot_record_default_event(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    created = client.post("/agreements", json=agreement_payload)
    agreement_id = created.json()["id"]

    response = client.post(
        f"/agreements/{agreement_id}/default-events",
        json={"event_type": "payment_default", "occurred_date": "2026-06-01"},
        headers=_risk_officer_headers(),
    )
    assert response.status_code == 403


def test_loan_operations_analyst_can_create_and_read(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    created = client.post("/agreements", json=agreement_payload)
    assert created.status_code == 201

    response = client.get(f"/agreements/{created.json()['id']}")
    assert response.status_code == 200
