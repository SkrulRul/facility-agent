from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import NoReturn
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.logging import (
    CorrelationIdMiddleware,
    _correlation_id,  # pyright: ignore[reportPrivateUsage]
    _CorrelationIdFilter,  # pyright: ignore[reportPrivateUsage]
    _JsonFormatter,  # pyright: ignore[reportPrivateUsage]
    new_correlation_id,
)
from app.services.agreement_service import AgreementService
from tests.conftest import build_agreement_payload


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def recorder() -> Iterator[_RecordingHandler]:
    handler = _RecordingHandler()
    handler.addFilter(_CorrelationIdFilter())
    logger = logging.getLogger("tests.logging.recorder")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)


def test_json_formatter_emits_valid_json_with_core_fields(recorder: _RecordingHandler) -> None:
    logging.getLogger("tests.logging.recorder").info("hello world", extra={"agreement_id": "abc"})
    record = recorder.records[0]

    payload = json.loads(_JsonFormatter().format(record))

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "tests.logging.recorder"
    assert payload["agreement_id"] == "abc"
    assert "timestamp" in payload


def test_json_formatter_renders_exception_detail(recorder: _RecordingHandler) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("tests.logging.recorder").exception("failed")
    record = recorder.records[0]

    payload = json.loads(_JsonFormatter().format(record))

    assert payload["exception"]["type"] == "ValueError"
    assert payload["exception"]["message"] == "boom"
    assert "ValueError: boom" in payload["exception"]["traceback"]


def test_json_formatter_defaults_correlation_id_when_unset(recorder: _RecordingHandler) -> None:
    logging.getLogger("tests.logging.recorder").info("no correlation yet")
    record = recorder.records[0]

    payload = json.loads(_JsonFormatter().format(record))

    assert payload["correlation_id"] == "-"


def test_new_correlation_id_binds_and_resets(recorder: _RecordingHandler) -> None:
    assert _correlation_id.get() is None

    with new_correlation_id() as correlation_id:
        assert _correlation_id.get() == correlation_id
        logging.getLogger("tests.logging.recorder").info("inside")

    assert _correlation_id.get() is None
    payload = json.loads(_JsonFormatter().format(recorder.records[0]))
    assert payload["correlation_id"] == correlation_id


def test_new_correlation_id_resets_even_on_exception() -> None:
    with pytest.raises(RuntimeError), new_correlation_id():
        raise RuntimeError("boom")

    assert _correlation_id.get() is None


def test_new_correlation_id_yields_distinct_ids_per_call() -> None:
    with new_correlation_id() as first:
        pass
    with new_correlation_id() as second:
        pass

    assert first != second


def test_middleware_stamps_response_header(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_sequential_requests_get_different_correlation_ids(client: TestClient) -> None:
    first = client.get("/health")
    second = client.get("/health")

    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_not_found_response_is_logged_at_warning_with_correlation_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    unknown_id = uuid4()

    response = client.get(f"/agreements/{unknown_id}")

    assert response.status_code == 404
    request_id = response.headers["X-Request-ID"]
    matching = [
        record
        for record in caplog.records
        if record.name == "app.main" and getattr(record, "correlation_id", None) == request_id
    ]
    assert matching
    assert matching[0].levelname == "WARNING"


def test_create_agreement_logs_never_contain_business_terms(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    response = client.post("/agreements", json=build_agreement_payload())

    assert response.status_code == 201
    formatted = "\n".join(_JsonFormatter().format(record) for record in caplog.records)
    assert "5.25" not in formatted  # rate_pct
    assert "ACT/360" not in formatted  # day_count_convention


def test_unhandled_exception_logs_error_and_returns_generic_500(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.ERROR)

    async def _raise_runtime_error(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError("db is on fire")

    monkeypatch.setattr(AgreementService, "get_agreement", _raise_runtime_error)

    response = client.get(f"/agreements/{uuid4()}")

    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert "db is on fire" not in response.text

    request_id = response.headers["X-Request-ID"]
    matching = [
        record
        for record in caplog.records
        if record.name == "app.logging" and getattr(record, "correlation_id", None) == request_id
    ]
    assert matching
    assert matching[0].levelname == "ERROR"
    assert matching[0].exception_type == "RuntimeError"  # type: ignore[attr-defined]


def test_correlation_id_middleware_is_exported() -> None:
    assert CorrelationIdMiddleware.__name__ == "CorrelationIdMiddleware"
