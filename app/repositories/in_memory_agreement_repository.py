from __future__ import annotations

from uuid import UUID

from app.domain import FacilityAgreement


class InMemoryAgreementRepository:
    """Dict-backed implementation of ``AgreementRepository`` (agreement_repository.py).

    All methods are trivial async wrappers around synchronous dict
    operations — no real I/O, no real await — so this backend stays usable in
    tests/local dev with zero external dependency while still satisfying the
    (now-async) Protocol.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, FacilityAgreement] = {}

    async def add(self, agreement: FacilityAgreement) -> None:
        self._store[agreement.id] = agreement

    async def get(self, agreement_id: UUID) -> FacilityAgreement | None:
        return self._store.get(agreement_id)

    async def list_all(self) -> list[FacilityAgreement]:
        return list(self._store.values())

    async def update(self, agreement: FacilityAgreement) -> None:
        self._store[agreement.id] = agreement
