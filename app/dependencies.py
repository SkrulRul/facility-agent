from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.repositories.agreement_repository import (
    AgreementRepository,
    InMemoryAgreementRepository,
)
from app.services.agreement_service import AgreementService

# Module-level singleton: one shared in-memory store for the process lifetime.
# Tests swap this out per-function via app.dependency_overrides for isolation.
_repository: AgreementRepository = InMemoryAgreementRepository()


def get_agreement_repository() -> AgreementRepository:
    return _repository


def get_agreement_service(
    repository: Annotated[AgreementRepository, Depends(get_agreement_repository)],
) -> AgreementService:
    return AgreementService(repository)
