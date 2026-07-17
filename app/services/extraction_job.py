from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ExtractionTargetType = Literal["term_sheet", "covenant_waiver_notice"]
ExtractionJobStatus = Literal["pending", "succeeded", "failed"]


class ExtractionJobNotFoundError(Exception):
    """Raised when a job lookup fails — mapped to HTTP 404 in main.py.

    Not a DomainNotFoundError subclass: agreement_service.py (which defines
    that base) imports app.routers.schemas, which imports this module for the
    extraction DTOs' shared types — subclassing it here would cycle back.
    main.py registers _domain_not_found_handler for both types independently.
    """


class ExtractionJob(BaseModel):
    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: UUID
    target_type: ExtractionTargetType
    status: ExtractionJobStatus
    submitted_at: datetime
    completed_at: datetime | None
    result: dict[str, Any] | None
    error_message: str | None
