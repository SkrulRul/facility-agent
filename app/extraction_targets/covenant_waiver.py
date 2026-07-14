from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class CovenantWaiverNotice(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    agreement_reference: str
    waived_covenant_reference: str
    waiver_reason: str
    effective_date: date
