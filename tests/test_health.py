from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import ClauseElement

from app.dependencies import get_engine
from app.main import app


def test_liveness_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ok_when_no_database_configured(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class _WorkingConnection:
    async def execute(self, _statement: ClauseElement) -> None:
        return None


class _WorkingConnect:
    async def __aenter__(self) -> _WorkingConnection:
        return _WorkingConnection()

    async def __aexit__(self, *_exc_info: object) -> None:
        return None


class _WorkingEngine:
    def connect(self) -> _WorkingConnect:
        return _WorkingConnect()


class _FailingConnect:
    async def __aenter__(self) -> None:
        raise SQLAlchemyError("connection refused")

    async def __aexit__(self, *_exc_info: object) -> None:
        return None


class _FailingEngine:
    def connect(self) -> _FailingConnect:
        return _FailingConnect()


def test_readiness_returns_ok_when_database_reachable(client: TestClient) -> None:
    app.dependency_overrides[get_engine] = lambda: _WorkingEngine()
    try:
        response = client.get("/health/ready")
    finally:
        del app.dependency_overrides[get_engine]
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_503_when_database_unreachable(client: TestClient) -> None:
    app.dependency_overrides[get_engine] = lambda: _FailingEngine()
    try:
        response = client.get("/health/ready")
    finally:
        del app.dependency_overrides[get_engine]
    assert response.status_code == 503
