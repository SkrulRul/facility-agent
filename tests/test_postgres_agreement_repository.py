from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.domain import BulletRepaymentSchedule, FacilityAgreement, FixedInterestTerms
from app.repositories.orm_models import OrmFacilityAgreement

# Reaching into module-private helpers deliberately: unit-testing base_status
# reconstruction/persistence in isolation, without a Postgres connection,
# requires exercising these functions directly rather than only through
# PostgresAgreementRepository's public add/get/update methods.
from app.repositories.postgres_agreement_repository import (
    _scalar_fields,  # pyright: ignore[reportPrivateUsage]
    _to_domain,  # pyright: ignore[reportPrivateUsage]
)


def build_agreement(**overrides: object) -> FacilityAgreement:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "agreement_date": date(2025, 1, 1),
        "effective_date": date(2025, 1, 15),
        "maturity_date": date(2099, 1, 15),
        "currency": "USD",
        "facility_amount": Decimal("1000000.00"),
        "facility_type": "term_loan",
        "borrower_id": uuid4(),
        "lender_ids": [uuid4()],
        "facility_agent_id": None,
        "interest_terms": FixedInterestTerms(
            type="fixed", rate_pct=Decimal("5.25"), day_count_convention="ACT/360"
        ),
        "repayment_schedule": BulletRepaymentSchedule(type="bullet"),
        "covenants": [],
        "default_events": [],
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return FacilityAgreement(**defaults)  # type: ignore[arg-type]


def build_orm_agreement(**overrides: object) -> OrmFacilityAgreement:
    """A transient OrmFacilityAgreement — never added to a session, so this
    stays a plain Python object with no engine/DB required (relationship
    collections default to empty lists on an unflushed instance).

    maturity_date defaults far in the future so FacilityAgreement.status
    resolves purely from base_status, not the "matured" priority branch.
    interest_terms/repayment_schedule use JSON-primitive-shaped dicts (plain
    strings, not Decimal) to match what a real JSONB round-trip produces —
    exactly the shape _to_domain's strict=False path is built to handle.
    """
    defaults: dict[str, object] = {
        "id": uuid4(),
        "agreement_date": date(2025, 1, 1),
        "effective_date": date(2025, 1, 15),
        "maturity_date": date(2099, 1, 15),
        "currency": "USD",
        "facility_amount": Decimal("1000000.00"),
        "facility_type": "term_loan",
        "borrower_id": uuid4(),
        "lender_ids": [uuid4()],
        "facility_agent_id": None,
        "interest_terms": {"type": "fixed", "rate_pct": "5.25", "day_count_convention": "ACT/360"},
        "repayment_schedule": {"type": "bullet"},
        "covenants": [],
        "created_at": datetime.now(UTC),
        "base_status": "draft",
    }
    defaults.update(overrides)
    return OrmFacilityAgreement(**defaults)


def test_to_domain_reconstructs_active_status() -> None:
    row = build_orm_agreement(base_status="active")

    agreement = _to_domain(row)

    assert agreement.get_base_status() == "active"
    assert agreement.status == "active"


def test_to_domain_reconstructs_terminated_status() -> None:
    row = build_orm_agreement(base_status="terminated")

    agreement = _to_domain(row)

    assert agreement.get_base_status() == "terminated"
    assert agreement.status == "terminated"


def test_to_domain_reconstructs_draft_status_by_default() -> None:
    """"draft" is the real value _to_row/_scalar_fields persist for an agreement
    that was never activated or terminated (FacilityAgreement._base_status's own
    default) — the case where _to_domain must call neither activate() nor
    terminate() and leave the freshly-validated agreement's default alone.
    """
    row = build_orm_agreement(base_status="draft")

    agreement = _to_domain(row)

    assert agreement.get_base_status() == "draft"
    assert agreement.status == "draft"


def test_scalar_fields_reflects_activated_status() -> None:
    agreement = build_agreement()
    agreement.activate()

    fields = _scalar_fields(agreement)

    assert fields["base_status"] == "active"


def test_scalar_fields_reflects_terminated_status() -> None:
    agreement = build_agreement()
    agreement.terminate()

    fields = _scalar_fields(agreement)

    assert fields["base_status"] == "terminated"


def test_scalar_fields_reflects_draft_status_by_default() -> None:
    agreement = build_agreement()

    fields = _scalar_fields(agreement)

    assert fields["base_status"] == "draft"
