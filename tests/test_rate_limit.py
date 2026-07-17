from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.dependencies import get_extraction_service
from app.main import app
from app.rate_limit import InMemoryRateLimiter, get_rate_limiter
from app.services.extraction_service import ExtractionTransportError
from tests.conftest import TEST_ANALYST_API_KEY


class _UnreachableExtractionService:
    """Stands in for ExtractionService in tests that only assert on the
    POST /extractions response — the rate limiter runs before submission
    even reaches the background task, so the extraction outcome itself is
    irrelevant here.
    """

    async def extract(
        self, text: str, target_model: type[BaseModel], *, max_attempts: int = 3
    ) -> BaseModel:
        raise ExtractionTransportError("not exercised by rate limit tests")


def _submit_payload() -> dict[str, str]:
    return {"target_type": "term_sheet", "document_text": "some term sheet text"}


class TestInMemoryRateLimiter:
    def test_allows_requests_up_to_max(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)

        assert limiter.check("key-a") is None
        assert limiter.check("key-a") is None
        assert limiter.check("key-a") is None

    def test_blocks_once_max_exceeded(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        limiter.check("key-a")
        limiter.check("key-a")

        retry_after_seconds = limiter.check("key-a")

        assert retry_after_seconds is not None
        assert 0 < retry_after_seconds <= 60

    def test_distinct_identities_have_independent_windows(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)

        assert limiter.check("key-a") is None
        assert limiter.check("key-b") is None
        assert limiter.check("key-a") is not None
        assert limiter.check("key-b") is not None

    def test_window_resets_after_expiry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clock = {"value": 1000.0}
        monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: clock["value"])
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        assert limiter.check("key-a") is None
        assert limiter.check("key-a") is not None

        clock["value"] += 61

        assert limiter.check("key-a") is None


def test_exceeding_limit_returns_429_with_retry_after(client: TestClient) -> None:
    tight_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    app.dependency_overrides[get_extraction_service] = lambda: _UnreachableExtractionService()
    app.dependency_overrides[get_rate_limiter] = lambda: tight_limiter

    first_response = client.post("/extractions", json=_submit_payload())
    second_response = client.post("/extractions", json=_submit_payload())

    assert first_response.status_code == 202
    assert second_response.status_code == 429
    assert "Retry-After" in second_response.headers
    assert int(second_response.headers["Retry-After"]) > 0


def test_distinct_api_keys_have_independent_rate_limits(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    second_analyst_api_key = "test-analyst-key-2"
    monkeypatch.setattr(
        "app.auth._load_role_keys",
        lambda: {
            TEST_ANALYST_API_KEY: "loan_operations_analyst",
            second_analyst_api_key: "loan_operations_analyst",
        },
    )
    tight_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    app.dependency_overrides[get_extraction_service] = lambda: _UnreachableExtractionService()
    app.dependency_overrides[get_rate_limiter] = lambda: tight_limiter

    first_key_first_call = client.post("/extractions", json=_submit_payload())
    first_key_second_call = client.post("/extractions", json=_submit_payload())
    second_key_call = client.post(
        "/extractions",
        json=_submit_payload(),
        headers={"X-API-Key": second_analyst_api_key},
    )

    assert first_key_first_call.status_code == 202
    assert first_key_second_call.status_code == 429
    assert second_key_call.status_code == 202


def test_get_extraction_is_not_rate_limited(client: TestClient) -> None:
    tight_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    app.dependency_overrides[get_extraction_service] = lambda: _UnreachableExtractionService()
    app.dependency_overrides[get_rate_limiter] = lambda: tight_limiter

    submit_response = client.post("/extractions", json=_submit_payload())
    job_id = submit_response.json()["id"]

    first_poll = client.get(f"/extractions/{job_id}")
    second_poll = client.get(f"/extractions/{job_id}")

    assert first_poll.status_code == 200
    assert second_poll.status_code == 200
