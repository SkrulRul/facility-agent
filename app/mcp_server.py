from __future__ import annotations

from uuid import UUID

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from app.dependencies import get_agreement_repository, get_agreement_service
from app.domain import DefaultEvent, FacilityAgreement
from app.logging import get_logger, new_correlation_id
from app.services.agreement_service import AgreementNotFoundError

mcp = FastMCP("facility-agent", mask_error_details=True)
logger = get_logger(__name__)


@mcp.tool
async def get_agreement(agreement_id: UUID) -> FacilityAgreement:
    """Fetch a facility agreement by ID."""
    with new_correlation_id():
        logger.info(
            "MCP tool call started",
            extra={"tool": "get_agreement", "agreement_id": str(agreement_id)},
        )
        service = get_agreement_service(get_agreement_repository())
        try:
            result = await service.get_agreement(agreement_id)
        except AgreementNotFoundError as exc:
            logger.warning(
                "MCP tool call not found",
                extra={"tool": "get_agreement", "agreement_id": str(agreement_id)},
            )
            raise ToolError(str(exc)) from exc
        except Exception:
            logger.error(
                "MCP tool call failed",
                exc_info=True,
                extra={"tool": "get_agreement", "agreement_id": str(agreement_id)},
            )
            raise
        logger.info(
            "MCP tool call succeeded",
            extra={"tool": "get_agreement", "agreement_id": str(agreement_id)},
        )
        return result


@mcp.tool
async def list_continuing_defaults(agreement_id: UUID) -> list[DefaultEvent]:
    """List default events on an agreement where is_continuing is True."""
    with new_correlation_id():
        logger.info(
            "MCP tool call started",
            extra={"tool": "list_continuing_defaults", "agreement_id": str(agreement_id)},
        )
        service = get_agreement_service(get_agreement_repository())
        try:
            result = await service.list_continuing_defaults(agreement_id)
        except AgreementNotFoundError as exc:
            logger.warning(
                "MCP tool call not found",
                extra={"tool": "list_continuing_defaults", "agreement_id": str(agreement_id)},
            )
            raise ToolError(str(exc)) from exc
        except Exception:
            logger.error(
                "MCP tool call failed",
                exc_info=True,
                extra={"tool": "list_continuing_defaults", "agreement_id": str(agreement_id)},
            )
            raise
        logger.info(
            "MCP tool call succeeded",
            extra={"tool": "list_continuing_defaults", "agreement_id": str(agreement_id)},
        )
        return result


if __name__ == "__main__":
    mcp.run()
