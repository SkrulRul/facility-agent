from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class OrmFacilityAgreement(Base):
    __tablename__ = "agreements"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    agreement_date: Mapped[date] = mapped_column(Date)
    effective_date: Mapped[date] = mapped_column(Date)
    maturity_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String)
    facility_amount: Mapped[Decimal] = mapped_column(Numeric)
    facility_type: Mapped[str] = mapped_column(String)
    borrower_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    lender_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PgUUID(as_uuid=True)))
    facility_agent_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    # Discriminated unions (InterestTerms, RepaymentSchedule) and the covenants
    # list are stored as opaque JSONB, serialized via Pydantic model_dump/
    # model_validate — see ADR-0021. None of the three are queried at the SQL
    # level, so no relational schema is warranted for them.
    interest_terms: Mapped[dict[str, object]] = mapped_column(JSONB)
    repayment_schedule: Mapped[dict[str, object]] = mapped_column(JSONB)
    covenants: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Persists FacilityAgreement._base_status (a PrivateAttr, excluded from
    # default Pydantic serialization) — reconstructed via activate()/
    # terminate() in PostgresAgreementRepository, not through model_validate.
    base_status: Mapped[str] = mapped_column(String)

    covenant_test_results: Mapped[list[OrmCovenantTestResult]] = relationship(
        back_populates="agreement", cascade="all, delete-orphan"
    )
    default_events: Mapped[list[OrmDefaultEvent]] = relationship(
        back_populates="agreement", cascade="all, delete-orphan"
    )


class OrmCovenantTestResult(Base):
    __tablename__ = "covenant_test_results"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    agreement_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agreements.id", ondelete="CASCADE")
    )
    # No DB-level FK to a covenant: covenants live in the parent row's
    # `covenants` JSONB column, not their own table — see ADR-0021.
    covenant_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True))
    test_date: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String)
    tested_by: Mapped[str] = mapped_column(String)

    agreement: Mapped[OrmFacilityAgreement] = relationship(back_populates="covenant_test_results")


class OrmDefaultEvent(Base):
    __tablename__ = "default_events"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    agreement_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agreements.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String)
    occurred_date: Mapped[date] = mapped_column(Date)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    related_covenant_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    related_external_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    remediation_status: Mapped[str] = mapped_column(String)
    waiver_status: Mapped[str] = mapped_column(String)

    agreement: Mapped[OrmFacilityAgreement] = relationship(back_populates="default_events")
