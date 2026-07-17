from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends

from app.auth import require_role
from app.dependencies import get_extraction_job_service
from app.rate_limit import enforce_extraction_rate_limit
from app.routers.schemas import ExtractionJobResponse, SubmitExtractionRequest
from app.services.extraction_job import ExtractionJob
from app.services.extraction_job_service import ExtractionJobService

router = APIRouter(
    prefix="/extractions",
    tags=["extractions"],
    dependencies=[Depends(require_role("loan_operations_analyst"))],
)

ServiceDep = Annotated[ExtractionJobService, Depends(get_extraction_job_service)]


def _to_response(job: ExtractionJob) -> ExtractionJobResponse:
    return ExtractionJobResponse.model_validate(job, from_attributes=True)


@router.post("", status_code=202, dependencies=[Depends(enforce_extraction_rate_limit)])
async def submit_extraction(
    dto: SubmitExtractionRequest,
    background_tasks: BackgroundTasks,
    service: ServiceDep,
) -> ExtractionJobResponse:
    job = await service.submit(dto.target_type)
    background_tasks.add_task(service.run, job.id, dto.document_text)
    return _to_response(job)


@router.get("/{job_id}")
async def get_extraction(job_id: UUID, service: ServiceDep) -> ExtractionJobResponse:
    job = await service.get(job_id)
    return _to_response(job)
