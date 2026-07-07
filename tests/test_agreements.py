from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from freezegun import freeze_time

from tests.conftest import (
    amortizing_repayment,
    build_agreement_payload,
    financial_covenant,
    floating_interest_terms,
)


def _create(client: TestClient, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/agreements", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_create_agreement_returns_201_with_sane_shape(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    body = _create(client, agreement_payload)
    assert body["id"]
    assert body["currency"] == "USD"
    assert body["facility_amount"] == "1000000.00"
    assert body["status"] == "draft"
    assert body["is_in_covenant_breach"] is False
    assert body["interest_terms"]["type"] == "fixed"
    assert len(body["covenants"]) == 2
    assert body["default_events"] == []
    assert body["covenant_test_results"] == []


def test_create_agreement_floating_and_amortizing(client: TestClient) -> None:
    payload = build_agreement_payload(
        interest_terms=floating_interest_terms(),
        repayment_schedule=amortizing_repayment(),
    )
    body = _create(client, payload)
    assert body["interest_terms"]["type"] == "floating"
    assert body["interest_terms"]["reference_rate"] == "SOFR"
    assert body["repayment_schedule"]["type"] == "amortizing"
    assert len(body["repayment_schedule"]["installments"]) == 2


def test_create_agreement_business_rule_violation_is_422(client: TestClient) -> None:
    # borrower_id also appears in lender_ids -> domain @model_validator raises -> 422.
    shared = str(uuid4())
    payload = build_agreement_payload(borrower_id=shared, lender_ids=[shared])
    response = client.post("/agreements", json=payload)
    assert response.status_code == 422


def test_get_agreement_by_id_returns_200(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    created = _create(client, agreement_payload)
    response = client.get(f"/agreements/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_agreement_unknown_id_returns_404(client: TestClient) -> None:
    response = client.get(f"/agreements/{uuid4()}")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_list_pagination_limit_and_offset(client: TestClient) -> None:
    for _ in range(3):
        _create(client, build_agreement_payload())

    first_page = client.get("/agreements", params={"limit": 2, "offset": 0})
    assert first_page.status_code == 200
    body = first_page.json()
    assert body["count"] == 2
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2

    second_page = client.get("/agreements", params={"limit": 2, "offset": 2})
    assert second_page.json()["count"] == 1


def test_list_filtered_by_status_draft(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    _create(client, agreement_payload)
    # Freshly created agreements are "draft": maturity_date is in the future and
    # there are no continuing default events. "active"/"terminated" base status
    # is unreachable via the Phase 2 endpoints (no activate endpoint in scope).
    response = client.get("/agreements", params={"status": "draft"})
    assert response.status_code == 200
    assert response.json()["count"] == 1

    empty = client.get("/agreements", params={"status": "terminated"})
    assert empty.json()["count"] == 0


def test_list_filtered_by_borrower_id(client: TestClient) -> None:
    target_borrower = str(uuid4())
    _create(client, build_agreement_payload(borrower_id=target_borrower))
    _create(client, build_agreement_payload())  # different random borrower

    response = client.get("/agreements", params={"borrower_id": target_borrower})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["borrower_id"] == target_borrower


def test_list_filtered_by_in_covenant_breach(client: TestClient) -> None:
    covenant_id = str(uuid4())
    payload = build_agreement_payload(covenants=[financial_covenant(covenant_id)])
    created = _create(client, payload)
    agreement_id = created["id"]

    fail_result = client.post(
        f"/agreements/{agreement_id}/covenants/{covenant_id}/test-results",
        json={"test_date": "2026-03-31", "result": "fail", "tested_by": "analyst"},
    )
    assert fail_result.status_code == 201

    breaching = client.get("/agreements", params={"in_covenant_breach": "true"})
    assert breaching.status_code == 200
    breaching_body = breaching.json()
    assert breaching_body["count"] == 1
    assert breaching_body["items"][0]["id"] == agreement_id
    assert breaching_body["items"][0]["is_in_covenant_breach"] is True

    non_breaching = client.get("/agreements", params={"in_covenant_breach": "false"})
    assert non_breaching.json()["count"] == 0


def test_list_pagination_rejects_out_of_bounds_params(client: TestClient) -> None:
    # Negative offset/limit or an oversized limit used to silently return the wrong
    # slice window (e.g. offset=-1 -> agreements[-1:...]) instead of erroring.
    assert client.get("/agreements", params={"limit": -1}).status_code == 422
    assert client.get("/agreements", params={"offset": -1}).status_code == 422
    assert client.get("/agreements", params={"limit": 0}).status_code == 422
    assert client.get("/agreements", params={"limit": 201}).status_code == 422


def test_list_status_matured_with_frozen_time(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    created = _create(client, agreement_payload)  # maturity_date 2030-01-15
    with freeze_time("2031-06-01"):
        response = client.get(f"/agreements/{created['id']}")
        assert response.status_code == 200
        assert response.json()["status"] == "matured"

        filtered = client.get("/agreements", params={"status": "matured"})
        assert filtered.json()["count"] == 1
