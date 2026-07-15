from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastmcp import Client
from fastmcp.client.transports import FastMCPTransport
from fastmcp.exceptions import ToolError

from app.domain import BulletRepaymentSchedule, DefaultEvent, FacilityAgreement, FixedInterestTerms
from app.mcp_server import mcp
from app.repositories.agreement_repository import InMemoryAgreementRepository


@pytest.fixture
def mcp_repository(monkeypatch: pytest.MonkeyPatch) -> InMemoryAgreementRepository:
    """A fresh in-memory repository per test, patched into app.mcp_server.

    Mirrors tests/conftest.py's app.dependency_overrides pattern: fastmcp has
    no Depends() graph for dependency_overrides to reach, so monkeypatching
    the bare name mcp_server.py imports is the equivalent isolation seam.
    """
    repository = InMemoryAgreementRepository()
    monkeypatch.setattr("app.mcp_server.get_agreement_repository", lambda: repository)
    return repository


@pytest.fixture
def mcp_client() -> Client[FastMCPTransport]:
    return Client(mcp)


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


def build_default_event(**overrides: object) -> DefaultEvent:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "event_type": "payment_default",
        "occurred_date": date(2026, 1, 1),
        "recorded_at": datetime.now(UTC),
        "remediation_status": "outstanding",
        "waiver_status": "none",
    }
    defaults.update(overrides)
    return DefaultEvent(**defaults)  # type: ignore[arg-type]


async def test_lists_both_registered_tools(mcp_client: Client[FastMCPTransport]) -> None:
    async with mcp_client:
        tools = await mcp_client.list_tools()
    assert {tool.name for tool in tools} == {"get_agreement", "list_continuing_defaults"}


async def test_get_agreement_returns_seeded_agreement(
    mcp_repository: InMemoryAgreementRepository, mcp_client: Client[FastMCPTransport]
) -> None:
    agreement = build_agreement()
    mcp_repository.add(agreement)

    async with mcp_client:
        result = await mcp_client.call_tool("get_agreement", {"agreement_id": str(agreement.id)})

    content = result.structured_content
    assert content is not None
    assert UUID(content["id"]) == agreement.id
    assert UUID(content["borrower_id"]) == agreement.borrower_id
    assert Decimal(content["facility_amount"]) == agreement.facility_amount


async def test_get_agreement_raises_for_unknown_id(
    mcp_repository: InMemoryAgreementRepository, mcp_client: Client[FastMCPTransport]
) -> None:
    unknown_id = uuid4()
    async with mcp_client:
        with pytest.raises(ToolError, match=f"Agreement {unknown_id} not found"):
            await mcp_client.call_tool("get_agreement", {"agreement_id": str(unknown_id)})


async def test_get_agreement_raises_for_malformed_uuid(
    mcp_repository: InMemoryAgreementRepository, mcp_client: Client[FastMCPTransport]
) -> None:
    async with mcp_client:
        with pytest.raises(ToolError):
            await mcp_client.call_tool("get_agreement", {"agreement_id": "not-a-uuid"})


async def test_list_continuing_defaults_filters_out_remedied_and_waived(
    mcp_repository: InMemoryAgreementRepository, mcp_client: Client[FastMCPTransport]
) -> None:
    continuing = build_default_event()
    remedied = build_default_event(remediation_status="remedied")
    waived = build_default_event(waiver_status="waived")
    agreement = build_agreement(default_events=[continuing, remedied, waived])
    mcp_repository.add(agreement)

    async with mcp_client:
        result = await mcp_client.call_tool(
            "list_continuing_defaults", {"agreement_id": str(agreement.id)}
        )

    content = result.structured_content
    assert content is not None
    returned_ids = {UUID(event["id"]) for event in content["result"]}
    assert returned_ids == {continuing.id}


async def test_list_continuing_defaults_raises_for_unknown_id(
    mcp_repository: InMemoryAgreementRepository, mcp_client: Client[FastMCPTransport]
) -> None:
    unknown_id = uuid4()
    async with mcp_client:
        with pytest.raises(ToolError, match=f"Agreement {unknown_id} not found"):
            await mcp_client.call_tool(
                "list_continuing_defaults", {"agreement_id": str(unknown_id)}
            )


async def test_list_continuing_defaults_returns_empty_list_when_none_continuing(
    mcp_repository: InMemoryAgreementRepository, mcp_client: Client[FastMCPTransport]
) -> None:
    remedied = build_default_event(remediation_status="remedied")
    agreement = build_agreement(default_events=[remedied])
    mcp_repository.add(agreement)

    async with mcp_client:
        result = await mcp_client.call_tool(
            "list_continuing_defaults", {"agreement_id": str(agreement.id)}
        )

    content = result.structured_content
    assert content is not None
    assert content["result"] == []


async def test_list_continuing_defaults_returns_empty_list_when_no_default_events_at_all(
    mcp_repository: InMemoryAgreementRepository, mcp_client: Client[FastMCPTransport]
) -> None:
    agreement = build_agreement(default_events=[])
    mcp_repository.add(agreement)

    async with mcp_client:
        result = await mcp_client.call_tool(
            "list_continuing_defaults", {"agreement_id": str(agreement.id)}
        )

    content = result.structured_content
    assert content is not None
    assert content["result"] == []
