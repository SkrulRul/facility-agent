from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import anthropic
import httpx
import pytest

from app.extraction_targets.term_sheet import TermSheetExtract
from app.services.extraction_service import (
    ExtractionError,
    ExtractionResponseShapeError,
    ExtractionTransportError,
)
from tests.extraction.conftest import MalformedShape, RaiseError, make_service

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "term_sheet_excerpt.txt"
DOCUMENT_TEXT = FIXTURE_PATH.read_text()

VALID_PAYLOAD = {
    "borrower_legal_name": "Northwind Manufacturing Group Ltd.",
    "currency": "EUR",
    "facility_amount": "15000000.00",
    "facility_type": "term_loan",
    "maturity_date": "2030-06-30",
    "interest_rate_pct": "6.25",
}

INVALID_PAYLOAD = {**VALID_PAYLOAD, "facility_amount": "0"}


async def test_happy_path_returns_validated_instance() -> None:
    service, fake = make_service(VALID_PAYLOAD)

    result = await service.extract(DOCUMENT_TEXT, TermSheetExtract)

    assert result == TermSheetExtract(
        borrower_legal_name="Northwind Manufacturing Group Ltd.",
        currency="EUR",
        facility_amount=Decimal("15000000.00"),
        facility_type="term_loan",
        maturity_date=date(2030, 6, 30),
        interest_rate_pct=Decimal("6.25"),
    )
    assert len(fake.calls) == 1


async def test_one_retry_recovers_from_validation_error() -> None:
    service, fake = make_service(INVALID_PAYLOAD, VALID_PAYLOAD)

    result = await service.extract(DOCUMENT_TEXT, TermSheetExtract)

    assert result.facility_amount == Decimal("15000000.00")
    assert len(fake.calls) == 2
    correction_turn = fake.calls[1]["messages"][-1]["content"]
    assert "facility_amount must be greater than 0" in correction_turn


async def test_max_attempts_exceeded_raises_extraction_error() -> None:
    service, fake = make_service(INVALID_PAYLOAD, INVALID_PAYLOAD, INVALID_PAYLOAD)

    with pytest.raises(ExtractionError) as exc_info:
        await service.extract(DOCUMENT_TEXT, TermSheetExtract, max_attempts=3)

    assert len(fake.calls) == 3
    assert exc_info.value.__cause__ is not None


async def test_transport_error_is_not_a_validation_retry() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    transport_exc = anthropic.APIConnectionError(message="connection failed", request=request)
    service, fake = make_service(RaiseError(transport_exc))

    with pytest.raises(ExtractionTransportError):
        await service.extract(DOCUMENT_TEXT, TermSheetExtract)

    assert len(fake.calls) == 1


async def test_malformed_response_shape_raises_response_shape_error() -> None:
    service, fake = make_service(MalformedShape("empty"))

    with pytest.raises(ExtractionResponseShapeError):
        await service.extract(DOCUMENT_TEXT, TermSheetExtract)

    assert len(fake.calls) == 1


async def test_non_text_response_block_raises_response_shape_error() -> None:
    service, fake = make_service(MalformedShape("non_text"))

    with pytest.raises(ExtractionResponseShapeError):
        await service.extract(DOCUMENT_TEXT, TermSheetExtract)

    assert len(fake.calls) == 1
