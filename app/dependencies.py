from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import DatabaseSettings
from app.repositories.agreement_repository import AgreementRepository
from app.repositories.in_memory_agreement_repository import InMemoryAgreementRepository
from app.repositories.postgres_agreement_repository import PostgresAgreementRepository
from app.services.agreement_service import AgreementService


@lru_cache
def get_engine() -> AsyncEngine | None:
    """The process-lifetime async engine, or None when running in-memory.

    create_async_engine() only builds a connection pool — it doesn't open a
    connection — so constructing this eagerly (via get_agreement_repository())
    is safe even before the first real query. Exposed so app/main.py's
    lifespan handler can dispose of it on shutdown (ADR-0020).
    """
    database_url = DatabaseSettings().database_url
    if database_url is None:
        return None
    return create_async_engine(str(database_url))


# One shared in-memory store (or Postgres engine) for the process lifetime.
# Tests swap this out per-function via app.dependency_overrides for isolation.
@lru_cache
def get_agreement_repository() -> AgreementRepository:
    engine = get_engine()
    if engine is None:
        return InMemoryAgreementRepository()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return PostgresAgreementRepository(session_factory)


def get_agreement_service(
    repository: Annotated[AgreementRepository, Depends(get_agreement_repository)],
) -> AgreementService:
    return AgreementService(repository)
