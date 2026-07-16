from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict

from app.config import AuthSettings

Role = Literal["loan_operations_analyst", "credit_risk_officer"]

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class Identity(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    role: Role


def _split_keys(raw: str) -> list[str]:
    return [key.strip() for key in raw.split(",") if key.strip()]


@lru_cache
def _load_role_keys() -> dict[str, Role]:
    settings = AuthSettings()
    role_keys: dict[str, Role] = {}
    for key in _split_keys(settings.loan_operations_analyst_api_keys.get_secret_value()):
        role_keys[key] = "loan_operations_analyst"
    for key in _split_keys(settings.credit_risk_officer_api_keys.get_secret_value()):
        role_keys[key] = "credit_risk_officer"
    return role_keys


def get_current_identity(
    api_key: Annotated[str | None, Security(_api_key_header)],
) -> Identity:
    role = _load_role_keys().get(api_key) if api_key is not None else None
    if role is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return Identity(role=role)


def require_role(*allowed_roles: Role) -> Callable[[Identity], Identity]:
    def _check(identity: Annotated[Identity, Depends(get_current_identity)]) -> Identity:
        if identity.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return identity

    return _check
