from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain import AgreementStatus, CovenantTestResult, DefaultEvent, FacilityAgreement
from app.repositories.agreement_repository import AgreementRepository
from app.routers.schemas import (
    CovenantTestResultRequest,
    CreateAgreementRequest,
    DefaultEventRequest,
)


class DomainNotFoundError(Exception):
    """Base for domain lookups that fail — mapped to HTTP 404 in main.py."""


class AgreementNotFoundError(DomainNotFoundError):
    pass


class CovenantNotFoundError(DomainNotFoundError):
    pass


class AgreementService:
    """Orchestrates the agreement aggregate.

    Synchronous by design (see ADR-0014): no endpoint in Phase 2 touches real
    I/O — the repository is an in-memory dict — so ``async def`` would be a
    fake justification.
    """

    def __init__(self, repository: AgreementRepository) -> None:
        self._repository = repository

    def create_agreement(self, dto: CreateAgreementRequest) -> FacilityAgreement:
        agreement = FacilityAgreement(
            id=uuid4(),
            created_at=datetime.now(UTC),
            **dto.model_dump(),
        )
        self._repository.add(agreement)
        return agreement

    def get_agreement(self, agreement_id: UUID) -> FacilityAgreement:
        agreement = self._repository.get(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError(f"Agreement {agreement_id} not found")
        return agreement

    def list_agreements(
        self,
        status: AgreementStatus | None = None,
        borrower_id: UUID | None = None,
        in_covenant_breach: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FacilityAgreement]:
        agreements = self._repository.list_all()
        if status is not None:
            agreements = [item for item in agreements if item.status == status]
        if borrower_id is not None:
            agreements = [item for item in agreements if item.borrower_id == borrower_id]
        if in_covenant_breach is not None:
            agreements = [
                item for item in agreements if item.is_in_covenant_breach == in_covenant_breach
            ]
        return agreements[offset : offset + limit]

    def record_covenant_test_result(
        self,
        agreement_id: UUID,
        covenant_id: UUID,
        dto: CovenantTestResultRequest,
    ) -> CovenantTestResult:
        agreement = self.get_agreement(agreement_id)
        if not any(covenant.id == covenant_id for covenant in agreement.covenants):
            raise CovenantNotFoundError(
                f"Covenant {covenant_id} not found on agreement {agreement_id}"
            )
        result = CovenantTestResult(
            id=uuid4(),
            covenant_id=covenant_id,
            test_date=dto.test_date,
            result=dto.result,
            tested_by=dto.tested_by,
        )
        agreement.covenant_test_results.append(result)
        return result

    def record_default_event(
        self,
        agreement_id: UUID,
        dto: DefaultEventRequest,
    ) -> DefaultEvent:
        agreement = self.get_agreement(agreement_id)
        event = DefaultEvent(
            id=uuid4(),
            event_type=dto.event_type,
            occurred_date=dto.occurred_date,
            recorded_at=datetime.now(UTC),
            related_covenant_id=dto.related_covenant_id,
            related_external_reference=dto.related_external_reference,
            remediation_status=dto.remediation_status,
            waiver_status=dto.waiver_status,
        )
        agreement.default_events.append(event)
        return event
