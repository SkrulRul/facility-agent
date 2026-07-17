from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_identity, require_role
from app.dependencies import get_agreement_service
from app.domain import AgreementStatus, FacilityAgreement
from app.routers.schemas import (
    AgreementResponse,
    CovenantTestResultRequest,
    CovenantTestResultResponse,
    CreateAgreementRequest,
    DefaultEventRequest,
    DefaultEventResponse,
    PaginatedResponse,
)
from app.services.agreement_service import AgreementService

router = APIRouter(
    prefix="/agreements",
    tags=["agreements"],
    dependencies=[Depends(get_current_identity)],
)

ServiceDep = Annotated[AgreementService, Depends(get_agreement_service)]
RequireWriter = Depends(require_role("loan_operations_analyst"))


def _to_response(agreement: FacilityAgreement) -> AgreementResponse:
    return AgreementResponse.model_validate(agreement, from_attributes=True)


@router.post("", status_code=201, dependencies=[RequireWriter])
async def create_agreement(dto: CreateAgreementRequest, service: ServiceDep) -> AgreementResponse:
    agreement = await service.create_agreement(dto)
    return _to_response(agreement)


@router.get("")
async def list_agreements(
    service: ServiceDep,
    status: AgreementStatus | None = None,
    borrower_id: UUID | None = None,
    in_covenant_breach: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[AgreementResponse]:
    agreements = await service.list_agreements(
        status=status,
        borrower_id=borrower_id,
        in_covenant_breach=in_covenant_breach,
        limit=limit,
        offset=offset,
    )
    items = [_to_response(agreement) for agreement in agreements]
    return PaginatedResponse(items=items, count=len(items), limit=limit, offset=offset)


@router.get("/{agreement_id}")
async def get_agreement(agreement_id: UUID, service: ServiceDep) -> AgreementResponse:
    agreement = await service.get_agreement(agreement_id)
    return _to_response(agreement)


@router.post(
    "/{agreement_id}/covenants/{covenant_id}/test-results",
    status_code=201,
    dependencies=[RequireWriter],
)
async def record_covenant_test_result(
    agreement_id: UUID,
    covenant_id: UUID,
    dto: CovenantTestResultRequest,
    service: ServiceDep,
) -> CovenantTestResultResponse:
    result = await service.record_covenant_test_result(agreement_id, covenant_id, dto)
    return CovenantTestResultResponse.model_validate(result, from_attributes=True)


@router.post("/{agreement_id}/default-events", status_code=201, dependencies=[RequireWriter])
async def record_default_event(
    agreement_id: UUID,
    dto: DefaultEventRequest,
    service: ServiceDep,
) -> DefaultEventResponse:
    event = await service.record_default_event(agreement_id, dto)
    return DefaultEventResponse.model_validate(event, from_attributes=True)
