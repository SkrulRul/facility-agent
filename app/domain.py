from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field, model_validator

AgreementStatus = Literal["draft", "active", "defaulted", "matured", "terminated"]

Currency = Literal["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "SEK", "NOK"]

class Party(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    id: UUID
    legal_name: str
    role: Literal["borrower", "lender", "facility_agent"]
    jurisdiction: str
    lei: str | None = None


class FixedInterestTerms(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    type: Literal["fixed"]
    rate_pct: Decimal
    day_count_convention: Literal["ACT/360", "ACT/365", "30/360"]


class FloatingInterestTerms(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    type: Literal["floating"]
    reference_rate: Literal["SOFR", "EURIBOR", "ESTR"]
    margin_pct: Decimal  # may be negative
    reset_frequency: Literal["monthly", "quarterly"]
    day_count_convention: Literal["ACT/360", "ACT/365", "30/360"]


InterestTerms = Annotated[
    FixedInterestTerms | FloatingInterestTerms,
    Field(discriminator="type"),
]


class Installment(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    due_date: date
    principal_amount: Decimal


# NO facility_amount on AmortizingRepaymentSchedule — sum validated at FacilityAgreement
class BulletRepaymentSchedule(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    type: Literal["bullet"]


class AmortizingRepaymentSchedule(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    type: Literal["amortizing"]
    installments: list[Installment]


RepaymentSchedule = Annotated[
    BulletRepaymentSchedule | AmortizingRepaymentSchedule,
    Field(discriminator="type"),
]


class FinancialCovenant(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    type: Literal["financial"]
    id: UUID
    description: str
    financial_metric: Literal["leverage_ratio", "interest_cover_ratio", "dscr"]
    operator: Literal["<=", ">=", "<", ">"]
    threshold: Decimal
    frequency: Literal["quarterly", "annually"]


class NonFinancialCovenant(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    type: Literal["non_financial"]
    id: UUID
    category: Literal["reporting", "negative_pledge", "change_of_control", "restricted_payments"]
    description: str


Covenant = Annotated[
    FinancialCovenant | NonFinancialCovenant,
    Field(discriminator="type"),
]


class CovenantTestResult(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    id: UUID
    covenant_id: UUID
    test_date: date
    result: Literal["pass", "fail", "waived"]
    tested_by: str


# validate_assignment=True so _validate_covenant_breach re-runs on event_type reassignment
class DefaultEvent(BaseModel):
    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: UUID
    event_type: Literal[
        "payment_default", "covenant_breach", "cross_default",
        "insolvency", "misrepresentation", "change_of_control",
    ]
    occurred_date: date
    recorded_at: datetime
    related_covenant_id: UUID | None = None
    related_external_reference: str | None = None
    remediation_status: Literal["outstanding", "remedied"] = "outstanding"
    waiver_status: Literal["none", "waived"] = "none"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_continuing(self) -> bool:
        return not (self.remediation_status == "remedied" or self.waiver_status == "waived")

    @model_validator(mode="after")
    def _validate_covenant_breach(self) -> DefaultEvent:
        if self.event_type == "covenant_breach" and self.related_covenant_id is None:
            raise ValueError("covenant_breach event requires related_covenant_id")
        return self


class FacilityAgreement(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    id: UUID
    agreement_date: date
    effective_date: date
    maturity_date: date
    currency: Currency
    facility_amount: Decimal
    facility_type: Literal["term_loan", "revolving_credit"]
    borrower_id: UUID
    lender_ids: list[UUID]
    facility_agent_id: UUID | None = None
    interest_terms: InterestTerms
    repayment_schedule: RepaymentSchedule
    covenants: list[Covenant] = Field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    default_events: list[DefaultEvent] = Field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    covenant_test_results: list[CovenantTestResult] = Field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    created_at: datetime

    _base_status: Literal["draft", "active", "terminated"] = PrivateAttr(default="draft")

    def activate(self) -> None:
        self._base_status = "active"

    def terminate(self) -> None:
        self._base_status = "terminated"

    def get_base_status(self) -> Literal["draft", "active", "terminated"]:
        return self._base_status

    @model_validator(mode="after")
    def _validate_agreement(self) -> FacilityAgreement:
        if self.borrower_id in self.lender_ids:
            raise ValueError("borrower_id must not appear in lender_ids")
        if len(self.lender_ids) == 0:
            raise ValueError("lender_ids must not be empty")
        if len(self.lender_ids) > 1 and self.facility_agent_id is None:
            raise ValueError("facility_agent_id required for syndicated facilities")
        if self.facility_amount <= Decimal(0):
            raise ValueError("facility_amount must be positive")
        if not (self.agreement_date <= self.effective_date < self.maturity_date):
            raise ValueError(
                "Date ordering must satisfy: agreement_date <= effective_date < maturity_date"
            )
        if isinstance(self.repayment_schedule, AmortizingRepaymentSchedule):
            installments = self.repayment_schedule.installments
            total = sum((inst.principal_amount for inst in installments), Decimal(0))
            if total != self.facility_amount:
                raise ValueError(
                    f"Amortizing installments sum {total} != facility_amount {self.facility_amount}"
                )
            due_dates = [inst.due_date for inst in installments]
            for prev, curr in zip(due_dates, due_dates[1:], strict=False):
                if curr <= prev:
                    raise ValueError("Installment due_dates must be strictly increasing")
            if any(due_date > self.maturity_date for due_date in due_dates):
                raise ValueError("All installment due_dates must be <= maturity_date")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> AgreementStatus:
        return compute_agreement_status(self)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_in_covenant_breach(self) -> bool:
        latest: dict[UUID, CovenantTestResult] = {}
        for result in self.covenant_test_results:
            existing = latest.get(result.covenant_id)
            if existing is None or result.test_date > existing.test_date:
                latest[result.covenant_id] = result
        return any(result.result == "fail" for result in latest.values())


def compute_agreement_status(agreement: FacilityAgreement) -> AgreementStatus:
    """Option C — service-layer status derivation pattern.

    Contrast to Option A: FacilityAgreement.status computed field delegates here,
    giving both patterns a single source of truth. A true service-layer caller
    would invoke this function directly on a loaded agreement instance.

    Priority: defaulted > matured > _base_status.
    """
    if any(event.is_continuing for event in agreement.default_events):
        return "defaulted"
    if agreement.maturity_date <= date.today():
        return "matured"
    return agreement.get_base_status()
