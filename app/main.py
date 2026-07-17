from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.config import LogSettings
from app.dependencies import get_engine
from app.logging import CorrelationIdMiddleware, configure_logging, get_logger
from app.routers.agreements import router as agreements_router
from app.routers.extractions import router as extractions_router
from app.services.agreement_service import DomainNotFoundError
from app.services.extraction_job import ExtractionJobNotFoundError

configure_logging(LogSettings().log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    yield
    engine = get_engine()
    if engine is not None:
        await engine.dispose()


app = FastAPI(title="facility-agent", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)


async def _domain_not_found_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.warning("Resource not found", extra={"detail": str(exc)})
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    # Domain models are built in the service layer (lax DTO -> strict domain),
    # so their business-rule ValidationErrors are raised outside FastAPI's
    # request-body validation. Surface them as 422 per ADR-008, matching the
    # shape of FastAPI's own request-validation errors.
    errors = exc.errors() if isinstance(exc, ValidationError) else []
    # Log field locations/messages only — never "input", which can carry the
    # raw submitted values (facility terms, party PII) per docs/specs/logging.md.
    logger.warning(
        "Validation error",
        extra={
            "validation_error_count": len(errors),
            "validation_error_locations": [error["loc"] for error in errors],
        },
    )
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


app.add_exception_handler(DomainNotFoundError, _domain_not_found_handler)
app.add_exception_handler(ExtractionJobNotFoundError, _domain_not_found_handler)
app.add_exception_handler(ValidationError, _validation_error_handler)
# No handler registered for the bare Exception type here: Starlette routes
# that specifically to ServerErrorMiddleware, which sits *outside* user
# middleware and always re-raises after responding — too late for
# CorrelationIdMiddleware to stamp X-Request-ID or see a live correlation id.
# CorrelationIdMiddleware (app/logging.py) is the catch-all instead — see
# docs/specs/logging.md for the full mechanics.
app.include_router(agreements_router)
app.include_router(extractions_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
