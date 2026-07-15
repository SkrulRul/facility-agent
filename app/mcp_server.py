from __future__ import annotations

from uuid import UUID

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from app.dependencies import get_agreement_repository, get_agreement_service
from app.domain import DefaultEvent, FacilityAgreement
from app.services.agreement_service import AgreementNotFoundError

mcp = FastMCP("facility-agent", mask_error_details=True)


@mcp.tool
def get_agreement(agreement_id: UUID) -> FacilityAgreement:
    """Fetch a facility agreement by ID."""
    service = get_agreement_service(get_agreement_repository())
    try:
        return service.get_agreement(agreement_id)
    except AgreementNotFoundError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool
def list_continuing_defaults(agreement_id: UUID) -> list[DefaultEvent]:
    """List default events on an agreement where is_continuing is True."""
    service = get_agreement_service(get_agreement_repository())
    try:
        return service.list_continuing_defaults(agreement_id)
    except AgreementNotFoundError as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run()
