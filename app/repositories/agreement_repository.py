from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain import FacilityAgreement


class AgreementRepository(Protocol):
    """Port for agreement persistence (structural subtyping, not ABC).

    All methods are async so one Protocol serves both the in-memory and
    Postgres-backed implementations uniformly (ADR-0020). ``update`` is the
    explicit durable-write path that replaces ADR-0013's mutation-by-reference
    contract — see ADR-0021 for why that contract stopped being sufficient
    once a backend can return copies instead of references.

    Implementations: ``InMemoryAgreementRepository`` (in_memory_agreement_repository.py),
    ``PostgresAgreementRepository`` (postgres_agreement_repository.py).
    """

    async def add(self, agreement: FacilityAgreement) -> None: ...

    async def get(self, agreement_id: UUID) -> FacilityAgreement | None: ...

    async def list_all(self) -> list[FacilityAgreement]: ...

    async def update(self, agreement: FacilityAgreement) -> None: ...
