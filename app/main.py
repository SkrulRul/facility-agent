from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.dependencies import get_engine
from app.routers.agreements import router as agreements_router
from app.services.agreement_service import DomainNotFoundError


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    yield
    engine = get_engine()
    if engine is not None:
        await engine.dispose()


app = FastAPI(title="facility-agent", lifespan=lifespan)


async def _domain_not_found_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    # Domain models are built in the service layer (lax DTO -> strict domain),
    # so their business-rule ValidationErrors are raised outside FastAPI's
    # request-body validation. Surface them as 422 per ADR-008, matching the
    # shape of FastAPI's own request-validation errors.
    errors = exc.errors() if isinstance(exc, ValidationError) else []
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


app.add_exception_handler(DomainNotFoundError, _domain_not_found_handler)
app.add_exception_handler(ValidationError, _validation_error_handler)
app.include_router(agreements_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
