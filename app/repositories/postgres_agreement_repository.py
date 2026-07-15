from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.domain import FacilityAgreement
from app.repositories.orm_models import (
    OrmCovenantTestResult,
    OrmDefaultEvent,
    OrmFacilityAgreement,
)


def _select_with_children() -> Select[tuple[OrmFacilityAgreement]]:
    return select(OrmFacilityAgreement).options(
        selectinload(OrmFacilityAgreement.covenant_test_results),
        selectinload(OrmFacilityAgreement.default_events),
    )


def _scalar_fields(agreement: FacilityAgreement) -> dict[str, object]:
    """Shared by ``_to_row`` (constructor kwargs) and ``update`` (attribute
    assignment) — the two places every persisted scalar column is named.
    """
    return {
        "agreement_date": agreement.agreement_date,
        "effective_date": agreement.effective_date,
        "maturity_date": agreement.maturity_date,
        "currency": agreement.currency,
        "facility_amount": agreement.facility_amount,
        "facility_type": agreement.facility_type,
        "borrower_id": agreement.borrower_id,
        "lender_ids": agreement.lender_ids,
        "facility_agent_id": agreement.facility_agent_id,
        "interest_terms": agreement.interest_terms.model_dump(mode="json"),
        "repayment_schedule": agreement.repayment_schedule.model_dump(mode="json"),
        "covenants": [covenant.model_dump(mode="json") for covenant in agreement.covenants],
        "created_at": agreement.created_at,
        "base_status": agreement.get_base_status(),
    }


def _covenant_test_result_rows(agreement: FacilityAgreement) -> list[OrmCovenantTestResult]:
    return [
        OrmCovenantTestResult(
            id=item.id,
            covenant_id=item.covenant_id,
            test_date=item.test_date,
            result=item.result,
            tested_by=item.tested_by,
        )
        for item in agreement.covenant_test_results
    ]


def _default_event_rows(agreement: FacilityAgreement) -> list[OrmDefaultEvent]:
    return [
        OrmDefaultEvent(
            id=item.id,
            event_type=item.event_type,
            occurred_date=item.occurred_date,
            recorded_at=item.recorded_at,
            related_covenant_id=item.related_covenant_id,
            related_external_reference=item.related_external_reference,
            remediation_status=item.remediation_status,
            waiver_status=item.waiver_status,
        )
        for item in agreement.default_events
    ]


def _to_domain(row: OrmFacilityAgreement) -> FacilityAgreement:
    """Reconstruct the domain aggregate from an ORM row.

    strict=False is required: interest_terms/repayment_schedule/covenants are
    JSONB, so their nested Decimal/UUID/date fields round-trip as JSON
    primitives (e.g. plain strings), which FacilityAgreement's class-level
    ConfigDict(strict=True) would otherwise reject. See ADR-0021.
    """
    data: dict[str, object] = {
        "id": row.id,
        "agreement_date": row.agreement_date,
        "effective_date": row.effective_date,
        "maturity_date": row.maturity_date,
        "currency": row.currency,
        "facility_amount": row.facility_amount,
        "facility_type": row.facility_type,
        "borrower_id": row.borrower_id,
        "lender_ids": row.lender_ids,
        "facility_agent_id": row.facility_agent_id,
        "interest_terms": row.interest_terms,
        "repayment_schedule": row.repayment_schedule,
        "covenants": row.covenants,
        "covenant_test_results": [
            {
                "id": item.id,
                "covenant_id": item.covenant_id,
                "test_date": item.test_date,
                "result": item.result,
                "tested_by": item.tested_by,
            }
            for item in row.covenant_test_results
        ],
        "default_events": [
            {
                "id": item.id,
                "event_type": item.event_type,
                "occurred_date": item.occurred_date,
                "recorded_at": item.recorded_at,
                "related_covenant_id": item.related_covenant_id,
                "related_external_reference": item.related_external_reference,
                "remediation_status": item.remediation_status,
                "waiver_status": item.waiver_status,
            }
            for item in row.default_events
        ],
        "created_at": row.created_at,
    }
    agreement = FacilityAgreement.model_validate(data, strict=False)
    # _base_status is a PrivateAttr, excluded from model_validate — restore it
    # via the domain's own transition methods rather than a persistence-shaped
    # constructor path (keeps app/domain.py free of persistence concerns).
    if row.base_status == "active":
        agreement.activate()
    elif row.base_status == "terminated":
        agreement.terminate()
    return agreement


def _to_row(agreement: FacilityAgreement) -> OrmFacilityAgreement:
    return OrmFacilityAgreement(
        id=agreement.id,
        covenant_test_results=_covenant_test_result_rows(agreement),
        default_events=_default_event_rows(agreement),
        **_scalar_fields(agreement),
    )


class PostgresAgreementRepository:
    """Postgres-backed implementation of ``AgreementRepository`` (ADR-0019/0021)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, agreement: FacilityAgreement) -> None:
        async with self._session_factory() as session, session.begin():
            session.add(_to_row(agreement))

    async def get(self, agreement_id: UUID) -> FacilityAgreement | None:
        stmt = _select_with_children().where(OrmFacilityAgreement.id == agreement_id)
        async with self._session_factory() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list_all(self) -> list[FacilityAgreement]:
        async with self._session_factory() as session:
            rows = (await session.execute(_select_with_children())).scalars().all()
        return [_to_domain(row) for row in rows]

    async def update(self, agreement: FacilityAgreement) -> None:
        """Full-aggregate write: replaces the parent row and delete-then-
        reinserts child rows in a single transaction (ADR-0021) — the
        replacement for ADR-0013's mutation-by-reference contract.

        Reassigning the relationship collections triggers the ORM's
        cascade="all, delete-orphan" to delete the stale child rows and
        insert the new ones as part of the same flush, so the delete+insert
        is atomic with the parent-row update by construction (session.begin()
        wraps the whole method in one transaction).
        """
        stmt = _select_with_children().where(OrmFacilityAgreement.id == agreement.id)
        async with self._session_factory() as session, session.begin():
            row = (await session.execute(stmt)).scalar_one()
            for field, value in _scalar_fields(agreement).items():
                setattr(row, field, value)
            row.covenant_test_results = _covenant_test_result_rows(agreement)
            row.default_events = _default_event_rows(agreement)
