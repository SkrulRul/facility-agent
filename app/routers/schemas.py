from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain import AgreementStatus, Currency

# ---------------------------------------------------------------------------
# Nested value-object DTOs (shared by request and response — identical shape).
#
# These are LAX (default Pydantic config, no strict=True). JSON has no native
# Decimal/UUID type; a lax DTO accepts JSON numbers/strings and coerces them to
# the annotated Python types. The service then builds strict domain models from
# the already-typed values, so no coercion happens at the domain boundary.
# ---------------------------------------------------------------------------


class FixedInterestTermsDTO(BaseModel):
    type: Literal["fixed"]
    rate_pct: Decimal
    day_count_convention: Literal["ACT/360", "ACT/365", "30/360"]


class FloatingInterestTermsDTO(BaseModel):
    type: Literal["floating"]
    reference_rate: Literal["SOFR", "EURIBOR", "ESTR"]
    margin_pct: Decimal
    reset_frequency: Literal["monthly", "quarterly"]
    day_count_convention: Literal["ACT/360", "ACT/365", "30/360"]


InterestTermsDTO = Annotated[
    FixedInterestTermsDTO | FloatingInterestTermsDTO,
    Field(discriminator="type"),
]


class InstallmentDTO(BaseModel):
    due_date: date
    principal_amount: Decimal


class BulletRepaymentScheduleDTO(BaseModel):
    type: Literal["bullet"]


class AmortizingRepaymentScheduleDTO(BaseModel):
    type: Literal["amortizing"]
    installments: list[InstallmentDTO]


RepaymentScheduleDTO = Annotated[
    BulletRepaymentScheduleDTO | AmortizingRepaymentScheduleDTO,
    Field(discriminator="type"),
]


class FinancialCovenantDTO(BaseModel):
    type: Literal["financial"]
    id: UUID
    description: str
    financial_metric: Literal["leverage_ratio", "interest_cover_ratio", "dscr"]
    operator: Literal["<=", ">=", "<", ">"]
    threshold: Decimal
    frequency: Literal["quarterly", "annually"]


class NonFinancialCovenantDTO(BaseModel):
    type: Literal["non_financial"]
    id: UUID
    category: Literal["reporting", "negative_pledge", "change_of_control", "restricted_payments"]
    description: str


CovenantDTO = Annotated[
    FinancialCovenantDTO | NonFinancialCovenantDTO,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Request DTOs
# ---------------------------------------------------------------------------


class CreateAgreementRequest(BaseModel):
    agreement_date: date
    effective_date: date
    maturity_date: date
    currency: Currency
    facility_amount: Decimal
    facility_type: Literal["term_loan", "revolving_credit"]
    borrower_id: UUID
    lender_ids: list[UUID]
    facility_agent_id: UUID | None = None
    interest_terms: InterestTermsDTO
    repayment_schedule: RepaymentScheduleDTO
    covenants: list[CovenantDTO] = Field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]


class CovenantTestResultRequest(BaseModel):
    test_date: date
    result: Literal["pass", "fail", "waived"]
    tested_by: str


class DefaultEventRequest(BaseModel):
    event_type: Literal[
        "payment_default", "covenant_breach", "cross_default",
        "insolvency", "misrepresentation", "change_of_control",
    ]
    occurred_date: date
    related_covenant_id: UUID | None = None
    related_external_reference: str | None = None
    remediation_status: Literal["outstanding", "remedied"] = "outstanding"
    waiver_status: Literal["none", "waived"] = "none"


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


class CovenantTestResultResponse(BaseModel):
    id: UUID
    covenant_id: UUID
    test_date: date
    result: Literal["pass", "fail", "waived"]
    tested_by: str


class DefaultEventResponse(BaseModel):
    id: UUID
    event_type: Literal[
        "payment_default", "covenant_breach", "cross_default",
        "insolvency", "misrepresentation", "change_of_control",
    ]
    occurred_date: date
    recorded_at: datetime
    related_covenant_id: UUID | None
    related_external_reference: str | None
    remediation_status: Literal["outstanding", "remedied"]
    waiver_status: Literal["none", "waived"]
    is_continuing: bool


class AgreementResponse(BaseModel):
    id: UUID
    agreement_date: date
    effective_date: date
    maturity_date: date
    currency: Currency
    facility_amount: Decimal
    facility_type: Literal["term_loan", "revolving_credit"]
    borrower_id: UUID
    lender_ids: list[UUID]
    facility_agent_id: UUID | None
    interest_terms: InterestTermsDTO
    repayment_schedule: RepaymentScheduleDTO
    covenants: list[CovenantDTO]
    default_events: list[DefaultEventResponse]
    covenant_test_results: list[CovenantTestResultResponse]
    created_at: datetime
    status: AgreementStatus
    is_in_covenant_breach: bool


class PaginatedResponse[ItemT](BaseModel):
    items: list[ItemT]
    count: int
    limit: int
    offset: int
