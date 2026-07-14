from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain import Currency


class TermSheetExtract(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    borrower_legal_name: str
    currency: Currency
    facility_amount: Decimal
    facility_type: Literal["term_loan", "revolving_credit"]
    maturity_date: date
    interest_rate_pct: Decimal

    @model_validator(mode="after")
    def _validate_facility_amount(self) -> TermSheetExtract:
        if self.facility_amount <= Decimal(0):
            raise ValueError("facility_amount must be greater than 0")
        return self
