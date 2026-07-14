from __future__ import annotations

from datetime import date

import pytest

from app.extraction_targets.covenant_waiver import CovenantWaiverNotice
from app.services.extraction_service import ExtractionError
from tests.extraction.conftest import make_service

VALID_PAYLOAD = {
    "agreement_reference": "FA-2024-0091",
    "waived_covenant_reference": "COV-LEV-01",
    "waiver_reason": "One-off restructuring charge unrelated to trading performance",
    "effective_date": "2026-10-20",
}

INVALID_PAYLOAD = {
    "agreement_reference": "FA-2024-0091",
    "waived_covenant_reference": "COV-LEV-01",
    "effective_date": "2026-10-20",
}  # missing required waiver_reason


async def test_happy_path_returns_validated_instance() -> None:
    service, fake = make_service(VALID_PAYLOAD)

    result = await service.extract("waiver letter text", CovenantWaiverNotice)

    assert result == CovenantWaiverNotice(
        agreement_reference="FA-2024-0091",
        waived_covenant_reference="COV-LEV-01",
        waiver_reason="One-off restructuring charge unrelated to trading performance",
        effective_date=date(2026, 10, 20),
    )
    assert len(fake.calls) == 1


async def test_one_retry_recovers_from_validation_error() -> None:
    service, fake = make_service(INVALID_PAYLOAD, VALID_PAYLOAD)

    result = await service.extract("waiver letter text", CovenantWaiverNotice)

    assert result.waiver_reason == "One-off restructuring charge unrelated to trading performance"
    assert len(fake.calls) == 2
    correction_turn = fake.calls[1]["messages"][-1]["content"]
    assert "waiver_reason" in correction_turn


async def test_max_attempts_exceeded_raises_extraction_error() -> None:
    service, fake = make_service(INVALID_PAYLOAD, INVALID_PAYLOAD, INVALID_PAYLOAD)

    with pytest.raises(ExtractionError):
        await service.extract("waiver letter text", CovenantWaiverNotice, max_attempts=3)

    assert len(fake.calls) == 3
