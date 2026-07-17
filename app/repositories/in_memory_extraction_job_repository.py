from __future__ import annotations

from uuid import UUID

from app.services.extraction_job import ExtractionJob


class InMemoryExtractionJobRepository:
    """Dict-backed store for extraction jobs (in_memory_agreement_repository.py's shape).

    A plain concrete class, not a Protocol — unlike AgreementRepository, only
    one backend exists for extraction jobs today. Jobs are ephemeral
    submission records, not part of the audited FacilityAgreement aggregate,
    so no Postgres-backed implementation is planned; if a durability
    requirement ever appears, extract a Protocol at that point (two
    concrete implementations, not one, is this project's bar for that).
    """

    def __init__(self) -> None:
        self._store: dict[UUID, ExtractionJob] = {}

    async def add(self, job: ExtractionJob) -> None:
        self._store[job.id] = job

    async def get(self, job_id: UUID) -> ExtractionJob | None:
        return self._store.get(job_id)

    async def update(self, job: ExtractionJob) -> None:
        self._store[job.id] = job
