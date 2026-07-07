from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.conftest import build_agreement_payload, financial_covenant


def test_record_covenant_test_result_returns_201_with_shape(client: TestClient) -> None:
    covenant_id = str(uuid4())
    payload = build_agreement_payload(covenants=[financial_covenant(covenant_id)])
    created = client.post("/agreements", json=payload)
    assert created.status_code == 201
    agreement_id = created.json()["id"]

    response = client.post(
        f"/agreements/{agreement_id}/covenants/{covenant_id}/test-results",
        json={"test_date": "2026-03-31", "result": "pass", "tested_by": "analyst"},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert body["id"]
    assert body["covenant_id"] == covenant_id
    assert body["result"] == "pass"
    assert body["tested_by"] == "analyst"


def test_record_covenant_test_result_unknown_agreement_returns_404(client: TestClient) -> None:
    response = client.post(
        f"/agreements/{uuid4()}/covenants/{uuid4()}/test-results",
        json={"test_date": "2026-03-31", "result": "pass", "tested_by": "analyst"},
    )
    assert response.status_code == 404
    assert "detail" in response.json()


def test_record_covenant_test_result_unknown_covenant_returns_404(client: TestClient) -> None:
    payload = build_agreement_payload(covenants=[financial_covenant()])
    created = client.post("/agreements", json=payload)
    agreement_id = created.json()["id"]

    response = client.post(
        f"/agreements/{agreement_id}/covenants/{uuid4()}/test-results",
        json={"test_date": "2026-03-31", "result": "pass", "tested_by": "analyst"},
    )
    assert response.status_code == 404
    assert "detail" in response.json()
