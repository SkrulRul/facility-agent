from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.dependencies import get_engine
from app.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])

EngineDep = Annotated[AsyncEngine | None, Depends(get_engine)]


@router.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(engine: EngineDep) -> dict[str, str]:
    if engine is not None:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            logger.warning("Readiness check failed: database unreachable")
            raise HTTPException(status_code=503, detail="Service unavailable") from exc
    return {"status": "ok"}
