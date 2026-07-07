from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient


def test_record_default_event_returns_201(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    created = client.post("/agreements", json=agreement_payload)
    agreement_id = created.json()["id"]

    response = client.post(
        f"/agreements/{agreement_id}/default-events",
        json={"event_type": "payment_default", "occurred_date": "2026-06-01"},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert body["id"]
    assert body["event_type"] == "payment_default"
    assert body["is_continuing"] is True


def test_continuing_default_event_drives_defaulted_status(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    created = client.post("/agreements", json=agreement_payload)
    agreement_id = created.json()["id"]

    event = client.post(
        f"/agreements/{agreement_id}/default-events",
        json={"event_type": "payment_default", "occurred_date": "2026-06-01"},
    )
    assert event.status_code == 201

    fetched = client.get(f"/agreements/{agreement_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "defaulted"


def test_record_default_event_unknown_agreement_returns_404(client: TestClient) -> None:
    response = client.post(
        f"/agreements/{uuid4()}/default-events",
        json={"event_type": "payment_default", "occurred_date": "2026-06-01"},
    )
    assert response.status_code == 404
    assert "detail" in response.json()


def test_covenant_breach_default_event_without_related_covenant_id_is_422(
    client: TestClient, agreement_payload: dict[str, Any]
) -> None:
    # DefaultEvent._validate_covenant_breach (app/domain.py) raises ValueError when
    # event_type == "covenant_breach" and related_covenant_id is None. This exercises
    # the same _validation_error_handler wiring in app/main.py as the create-agreement
    # 422 test, but through the default-events sub-resource endpoint.
    created = client.post("/agreements", json=agreement_payload)
    agreement_id = created.json()["id"]

    response = client.post(
        f"/agreements/{agreement_id}/default-events",
        json={"event_type": "covenant_breach", "occurred_date": "2026-06-01"},
    )
    assert response.status_code == 422
