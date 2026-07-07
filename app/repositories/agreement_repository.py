from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain import FacilityAgreement


class AgreementRepository(Protocol):
    """Port for agreement persistence (structural subtyping, not ABC).

    No ``update``/``save`` method: ``FacilityAgreement`` list fields
    (``covenant_test_results``, ``default_events``) are ordinary mutable
    Python lists. The repository stores object references, so appending to a
    fetched agreement's list *is* the persistence write (see ADR-0013).
    """

    def add(self, agreement: FacilityAgreement) -> None: ...

    def get(self, agreement_id: UUID) -> FacilityAgreement | None: ...

    def list_all(self) -> list[FacilityAgreement]: ...


class InMemoryAgreementRepository:
    """Dict-backed in-memory implementation of ``AgreementRepository``."""

    def __init__(self) -> None:
        self._store: dict[UUID, FacilityAgreement] = {}

    def add(self, agreement: FacilityAgreement) -> None:
        self._store[agreement.id] = agreement

    def get(self, agreement_id: UUID) -> FacilityAgreement | None:
        return self._store.get(agreement_id)

    def list_all(self) -> list[FacilityAgreement]:
        return list(self._store.values())
