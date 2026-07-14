from __future__ import annotations

from app.config import ExtractionSettings
from app.services.extraction_service import ExtractionService, build_extraction_service


def test_build_extraction_service_wires_settings_into_client() -> None:
    settings = ExtractionSettings(extraction_model="test-model", transport_max_retries=5)

    service = build_extraction_service(settings)

    assert isinstance(service, ExtractionService)
    assert service._settings is settings  # pyright: ignore[reportPrivateUsage]
    client = service._client  # pyright: ignore[reportPrivateUsage]
    assert client.max_retries == 5  # type: ignore[attr-defined]
