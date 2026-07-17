from __future__ import annotations

import time
from functools import lru_cache
from threading import Lock
from typing import Annotated

from fastapi import Depends, HTTPException

from app.auth import Identity, get_current_identity
from app.config import RateLimitSettings


class InMemoryRateLimiter:
    """Fixed-window request counter, one window per identity key.

    In-process, single-worker only — matches ADR-0027's posture for the
    extraction job store (no Redis, no cross-process visibility). A real
    Lock guards state because sync FastAPI dependencies run via
    run_in_threadpool, so concurrent requests can call check() from
    different threads.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = Lock()

    def check(self, identity_key: str) -> float | None:
        """Records a request for identity_key if the window allows it.

        Returns None when allowed, or the number of seconds until the
        current window resets when the identity has exceeded its limit.
        """
        now = time.monotonic()
        with self._lock:
            window_start, count = self._windows.get(identity_key, (now, 0))
            elapsed = now - window_start
            if elapsed >= self._window_seconds:
                window_start, count, elapsed = now, 0, 0.0
            if count >= self._max_requests:
                return self._window_seconds - elapsed
            self._windows[identity_key] = (window_start, count + 1)
            return None


@lru_cache
def get_rate_limiter() -> InMemoryRateLimiter:
    settings = RateLimitSettings()
    return InMemoryRateLimiter(
        max_requests=settings.extraction_rate_limit_max_requests,
        window_seconds=settings.extraction_rate_limit_window_seconds,
    )


def enforce_extraction_rate_limit(
    identity: Annotated[Identity, Depends(get_current_identity)],
    limiter: Annotated[InMemoryRateLimiter, Depends(get_rate_limiter)],
) -> None:
    retry_after_seconds = limiter.check(identity.key_fingerprint)
    if retry_after_seconds is not None:
        raise HTTPException(
            status_code=429,
            detail=(
                "Extraction request rate limit exceeded. "
                f"Please retry after {int(retry_after_seconds) + 1} seconds."
            ),
            headers={"Retry-After": str(int(retry_after_seconds) + 1)},
        )
