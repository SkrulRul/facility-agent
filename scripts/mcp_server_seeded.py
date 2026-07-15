"""Test-only MCP server entry point, pre-seeded with one example agreement.

Used exclusively by scripts/smoke_test_mcp_server.py to exercise the success
path (not just not-found errors) over the real stdio wire protocol. This is
NOT the production entry point — that's `app/mcp_server.py`, run via
`uv run python -m app.mcp_server` (see README.md / .mcp.json), which has no
write or seed capability by design (see docs/specs/mcp_server.md "Known
limitation" — no write-capable MCP tool, no persistence bridge).

This script reuses the real `mcp` object from app.mcp_server unmodified —
same tools, same code — and seeds one agreement directly into the repository
before mcp.run() starts, since there's no MCP tool (and never should be one)
that could do this over the wire. Not run by `uv run poe check`. Always seeds
into whatever backend get_agreement_repository() resolves to (in-memory by
design here — see docs/specs/mcp_server.md — since this script's only job is
exercising the stdio wire protocol, not proving Postgres durability, which
scripts/smoke_test_persistence.py covers instead).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from app.dependencies import get_agreement_repository
from app.domain import (
    BulletRepaymentSchedule,
    DefaultEvent,
    FacilityAgreement,
    FixedInterestTerms,
)
from app.mcp_server import mcp

# Fixed, not random, so scripts/smoke_test_mcp_server.py can assert against it
# without any inter-process communication beyond the MCP protocol itself.
SEEDED_AGREEMENT_ID = UUID("1a08e2ef-0ff9-4bae-ac8d-840c5820a94f")


async def seed() -> None:
    continuing_default = DefaultEvent(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        event_type="payment_default",
        occurred_date=date(2026, 1, 1),
        recorded_at=datetime.now(UTC),
        remediation_status="outstanding",
        waiver_status="none",
    )
    remedied_default = DefaultEvent(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        event_type="covenant_breach",
        occurred_date=date(2025, 6, 1),
        recorded_at=datetime.now(UTC),
        related_covenant_id=UUID("00000000-0000-0000-0000-000000000003"),
        remediation_status="remedied",
        waiver_status="none",
    )
    agreement = FacilityAgreement(
        id=SEEDED_AGREEMENT_ID,
        agreement_date=date(2025, 1, 1),
        effective_date=date(2025, 1, 15),
        maturity_date=date(2030, 1, 15),
        currency="USD",
        facility_amount=Decimal("1000000.00"),
        facility_type="term_loan",
        borrower_id=UUID("00000000-0000-0000-0000-000000000004"),
        lender_ids=[UUID("00000000-0000-0000-0000-000000000005")],
        facility_agent_id=None,
        interest_terms=FixedInterestTerms(
            type="fixed", rate_pct=Decimal("5.25"), day_count_convention="ACT/360"
        ),
        repayment_schedule=BulletRepaymentSchedule(type="bullet"),
        covenants=[],
        default_events=[continuing_default, remedied_default],
        created_at=datetime.now(UTC),
    )
    await get_agreement_repository().add(agreement)


if __name__ == "__main__":
    asyncio.run(seed())
    mcp.run()
