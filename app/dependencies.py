from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.repositories.agreement_repository import (
    AgreementRepository,
    InMemoryAgreementRepository,
)
from app.services.agreement_service import AgreementService


# One shared in-memory store for the process lifetime.
# Tests swap this out per-function via app.dependency_overrides for isolation.
@lru_cache
def get_agreement_repository() -> AgreementRepository:
    return InMemoryAgreementRepository()


def get_agreement_service(
    repository: Annotated[AgreementRepository, Depends(get_agreement_repository)],
) -> AgreementService:
    return AgreementService(repository)
