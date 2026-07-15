from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.dependencies import get_agreement_repository
from app.domain import (
    BulletRepaymentSchedule,
    CovenantTestResult,
    FacilityAgreement,
    FixedInterestTerms,
)
from app.main import app
from app.repositories.in_memory_agreement_repository import InMemoryAgreementRepository
from tests.conftest import build_agreement_payload, financial_covenant


def build_agreement(**overrides: object) -> FacilityAgreement:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "agreement_date": date(2025, 1, 1),
        "effective_date": date(2025, 1, 15),
        "maturity_date": date(2030, 1, 15),
        "currency": "USD",
        "facility_amount": Decimal("1000000.00"),
        "facility_type": "term_loan",
        "borrower_id": uuid4(),
        "lender_ids": [uuid4()],
        "facility_agent_id": None,
        "interest_terms": FixedInterestTerms(
            type="fixed", rate_pct=Decimal("5.25"), day_count_convention="ACT/360"
        ),
        "repayment_schedule": BulletRepaymentSchedule(type="bullet"),
        "covenants": [],
        "default_events": [],
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return FacilityAgreement(**defaults)  # type: ignore[arg-type]


class SpyAgreementRepository:
    """Wraps a real InMemoryAgreementRepository; records update() calls.

    Used to prove the service layer actually calls repository.update() as
    its durable-write path (ADR-0021) — independent of InMemoryAgreementRepository's
    own reference-mutation semantics, which would otherwise mask a future
    regression where that call is silently dropped from the service layer
    (the exact failure mode ADR-0013 named).
    """

    def __init__(self, inner: InMemoryAgreementRepository) -> None:
        self._inner = inner
        self.update_calls: list[FacilityAgreement] = []

    async def add(self, agreement: FacilityAgreement) -> None:
        await self._inner.add(agreement)

    async def get(self, agreement_id: UUID) -> FacilityAgreement | None:
        return await self._inner.get(agreement_id)

    async def list_all(self) -> list[FacilityAgreement]:
        return await self._inner.list_all()

    async def update(self, agreement: FacilityAgreement) -> None:
        self.update_calls.append(agreement)
        await self._inner.update(agreement)


async def test_in_memory_repository_add_and_get_round_trip() -> None:
    repository = InMemoryAgreementRepository()
    agreement = build_agreement()

    await repository.add(agreement)
    fetched = await repository.get(agreement.id)

    assert fetched is not None
    assert fetched.id == agreement.id
    assert fetched.facility_amount == agreement.facility_amount


async def test_in_memory_repository_get_returns_none_for_unknown_id() -> None:
    repository = InMemoryAgreementRepository()

    assert await repository.get(uuid4()) is None


async def test_in_memory_repository_list_all_returns_every_added_agreement() -> None:
    repository = InMemoryAgreementRepository()
    first = build_agreement()
    second = build_agreement()

    await repository.add(first)
    await repository.add(second)

    all_agreements = await repository.list_all()
    assert {agreement.id for agreement in all_agreements} == {first.id, second.id}


async def test_in_memory_repository_update_replaces_stored_agreement() -> None:
    repository = InMemoryAgreementRepository()
    agreement = build_agreement()
    await repository.add(agreement)

    agreement.covenant_test_results.append(
        CovenantTestResult(
            id=uuid4(),
            covenant_id=uuid4(),
            test_date=date(2026, 1, 1),
            result="pass",
            tested_by="analyst",
        )
    )
    await repository.update(agreement)

    fetched = await repository.get(agreement.id)
    assert fetched is not None
    assert len(fetched.covenant_test_results) == 1


def test_record_covenant_test_result_calls_repository_update(client: TestClient) -> None:
    inner = InMemoryAgreementRepository()
    spy = SpyAgreementRepository(inner)
    app.dependency_overrides[get_agreement_repository] = lambda: spy

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
    assert len(spy.update_calls) == 1
    updated_agreement = spy.update_calls[-1]
    assert len(updated_agreement.covenant_test_results) == 1
    assert str(updated_agreement.covenant_test_results[0].covenant_id) == covenant_id


def test_record_default_event_calls_repository_update(client: TestClient) -> None:
    inner = InMemoryAgreementRepository()
    spy = SpyAgreementRepository(inner)
    app.dependency_overrides[get_agreement_repository] = lambda: spy

    payload = build_agreement_payload()
    created = client.post("/agreements", json=payload)
    assert created.status_code == 201
    agreement_id = created.json()["id"]

    response = client.post(
        f"/agreements/{agreement_id}/default-events",
        json={
            "event_type": "payment_default",
            "occurred_date": "2026-01-01",
            "remediation_status": "outstanding",
            "waiver_status": "none",
        },
    )

    assert response.status_code == 201, response.text
    assert len(spy.update_calls) == 1
    updated_agreement = spy.update_calls[-1]
    assert len(updated_agreement.default_events) == 1
    assert updated_agreement.default_events[0].event_type == "payment_default"
