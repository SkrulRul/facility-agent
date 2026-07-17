from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.extraction_targets.covenant_waiver import CovenantWaiverNotice
from app.extraction_targets.term_sheet import TermSheetExtract
from app.logging import get_logger, new_correlation_id
from app.repositories.in_memory_extraction_job_repository import InMemoryExtractionJobRepository
from app.services.extraction_job import (
    ExtractionJob,
    ExtractionJobNotFoundError,
    ExtractionTargetType,
)
from app.services.extraction_service import (
    ExtractionError,
    ExtractionResponseShapeError,
    ExtractionService,
    ExtractionTransportError,
)

_TARGET_MODELS: dict[ExtractionTargetType, type[BaseModel]] = {
    "term_sheet": TermSheetExtract,
    "covenant_waiver_notice": CovenantWaiverNotice,
}

_FAILURE_MESSAGES: dict[type[Exception], str] = {
    ExtractionError: (
        "We couldn't extract structured data from this document after multiple "
        "attempts. Please review the document text and try again."
    ),
    ExtractionTransportError: (
        "The extraction service was temporarily unavailable. Please try submitting again."
    ),
    ExtractionResponseShapeError: (
        "The extraction service returned an unexpected response. Please try submitting again."
    ),
}
_UNEXPECTED_FAILURE_MESSAGE = "Extraction failed unexpectedly. Please try again or contact support."

logger = get_logger(__name__)


class ExtractionJobService:
    """Orchestrates document extraction as a submit-now / retrieve-later job.

    ExtractionService.extract() (extraction_service.py) takes seconds and
    retries internally, so submit() only creates and stores the job record —
    run() is the actual extraction work, invoked out-of-band as a FastAPI
    BackgroundTask by the router (app/routers/extractions.py) once submit()
    has already returned.
    """

    def __init__(
        self,
        repository: InMemoryExtractionJobRepository,
        extraction_service: ExtractionService,
    ) -> None:
        self._repository = repository
        self._extraction_service = extraction_service

    async def submit(self, target_type: ExtractionTargetType) -> ExtractionJob:
        job = ExtractionJob(
            id=uuid4(),
            target_type=target_type,
            status="pending",
            submitted_at=datetime.now(UTC),
            completed_at=None,
            result=None,
            error_message=None,
        )
        await self._repository.add(job)
        return job

    async def get(self, job_id: UUID) -> ExtractionJob:
        job = await self._repository.get(job_id)
        if job is None:
            raise ExtractionJobNotFoundError(f"Extraction job {job_id} not found")
        return job

    async def run(self, job_id: UUID, document_text: str) -> None:
        """The background task body. Never raises — always leaves the job terminal.

        Runs outside the HTTP request/response cycle, so it binds its own
        correlation id (mirrors app/mcp_server.py's pattern) rather than
        inheriting one — the request that scheduled this has already returned
        its 202 response by the time this executes.
        """
        with new_correlation_id():
            logger.info(
                "Extraction job started",
                extra={"job_id": str(job_id)},
            )
            job = await self.get(job_id)
            target_model = _TARGET_MODELS[job.target_type]
            try:
                extracted = await self._extraction_service.extract(document_text, target_model)
            except (
                ExtractionError,
                ExtractionTransportError,
                ExtractionResponseShapeError,
            ) as exc:
                job.status = "failed"
                job.completed_at = datetime.now(UTC)
                job.error_message = _FAILURE_MESSAGES[type(exc)]
                logger.warning(
                    "Extraction job failed",
                    extra={"job_id": str(job_id), "failure_type": type(exc).__name__},
                )
            except Exception:
                job.status = "failed"
                job.completed_at = datetime.now(UTC)
                job.error_message = _UNEXPECTED_FAILURE_MESSAGE
                logger.error(
                    "Extraction job failed unexpectedly",
                    exc_info=True,
                    extra={"job_id": str(job_id)},
                )
            else:
                job.status = "succeeded"
                job.completed_at = datetime.now(UTC)
                job.result = extracted.model_dump(mode="json")
                logger.info(
                    "Extraction job succeeded",
                    extra={"job_id": str(job_id)},
                )
            await self._repository.update(job)
