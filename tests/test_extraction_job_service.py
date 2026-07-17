from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from app.repositories.in_memory_extraction_job_repository import (
    InMemoryExtractionJobRepository,
)
from app.services.extraction_job import ExtractionJobNotFoundError
from app.services.extraction_job_service import ExtractionJobService
from tests.extraction.conftest import MalformedShape, RaiseError, make_service

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "term_sheet_excerpt.txt"
DOCUMENT_TEXT = FIXTURE_PATH.read_text()

VALID_PAYLOAD = {
    "borrower_legal_name": "Northwind Manufacturing Group Ltd.",
    "currency": "EUR",
    "facility_amount": "15000000.00",
    "facility_type": "term_loan",
    "maturity_date": "2030-06-30",
    "interest_rate_pct": "6.25",
}


class _RaisingExtractionService:
    """A minimal fake whose extract() always raises an unmodeled exception."""

    async def extract(
        self, text: str, target_model: type[BaseModel], *, max_attempts: int = 3
    ) -> BaseModel:
        raise ValueError("boom")


class _NeverCalledExtractionService:
    async def extract(
        self, text: str, target_model: type[BaseModel], *, max_attempts: int = 3
    ) -> BaseModel:
        raise AssertionError("submit() must not invoke extraction")


async def test_submit_returns_pending_job_without_calling_extraction_service() -> None:
    service = ExtractionJobService(
        InMemoryExtractionJobRepository(),
        _NeverCalledExtractionService(),  # type: ignore[arg-type]
    )

    job = await service.submit("term_sheet")

    assert job.status == "pending"
    assert job.result is None
    assert job.error_message is None
    assert job.completed_at is None


async def test_get_unknown_job_raises_not_found() -> None:
    service = ExtractionJobService(
        InMemoryExtractionJobRepository(),
        _RaisingExtractionService(),  # type: ignore[arg-type]
    )

    with pytest.raises(ExtractionJobNotFoundError):
        await service.get(uuid4())


async def test_run_success_stores_result_and_succeeded_status() -> None:
    extraction_service, _fake = make_service(VALID_PAYLOAD)
    repository = InMemoryExtractionJobRepository()
    service = ExtractionJobService(repository, extraction_service)
    job = await service.submit("term_sheet")

    await service.run(job.id, DOCUMENT_TEXT)

    updated = await service.get(job.id)
    assert updated.status == "succeeded"
    assert updated.completed_at is not None
    assert updated.result is not None
    assert updated.result["borrower_legal_name"] == "Northwind Manufacturing Group Ltd."
    assert updated.error_message is None


async def test_run_validation_failure_after_retries_is_clear_and_actionable() -> None:
    invalid = {**VALID_PAYLOAD, "facility_amount": "0"}
    extraction_service, _fake = make_service(invalid, invalid, invalid)
    repository = InMemoryExtractionJobRepository()
    service = ExtractionJobService(repository, extraction_service)
    job = await service.submit("term_sheet")

    await service.run(job.id, DOCUMENT_TEXT)

    updated = await service.get(job.id)
    assert updated.status == "failed"
    assert updated.result is None
    assert updated.error_message
    assert "Traceback" not in updated.error_message
    assert "ValidationError" not in updated.error_message


async def test_run_transport_failure_is_clear_and_actionable() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    transport_exc = anthropic.APIConnectionError(message="connection failed", request=request)
    extraction_service, _fake = make_service(RaiseError(transport_exc))
    repository = InMemoryExtractionJobRepository()
    service = ExtractionJobService(repository, extraction_service)
    job = await service.submit("term_sheet")

    await service.run(job.id, DOCUMENT_TEXT)

    updated = await service.get(job.id)
    assert updated.status == "failed"
    assert "temporarily unavailable" in updated.error_message  # type: ignore[operator]


async def test_run_response_shape_failure_is_clear_and_actionable() -> None:
    extraction_service, _fake = make_service(MalformedShape("empty"))
    repository = InMemoryExtractionJobRepository()
    service = ExtractionJobService(repository, extraction_service)
    job = await service.submit("term_sheet")

    await service.run(job.id, DOCUMENT_TEXT)

    updated = await service.get(job.id)
    assert updated.status == "failed"
    assert "unexpected response" in updated.error_message  # type: ignore[operator]


async def test_run_unexpected_exception_never_leaks_raw_details() -> None:
    repository = InMemoryExtractionJobRepository()
    service = ExtractionJobService(
        repository,
        _RaisingExtractionService(),  # type: ignore[arg-type]
    )
    job = await service.submit("term_sheet")

    await service.run(job.id, DOCUMENT_TEXT)

    updated = await service.get(job.id)
    assert updated.status == "failed"
    assert updated.error_message == (
        "Extraction failed unexpectedly. Please try again or contact support."
    )
