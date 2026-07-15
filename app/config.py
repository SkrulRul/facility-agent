from __future__ import annotations

from pydantic import PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExtractionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr = SecretStr("")
    extraction_model: str = "claude-sonnet-5"
    transport_max_retries: int = 2


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: PostgresDsn | None = None

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg_scheme(cls, value: PostgresDsn | None) -> PostgresDsn | None:
        # create_async_engine() requires the +asyncpg driver; a bare
        # postgresql:// URL passes PostgresDsn's shape validation but fails
        # later with a cryptic "No module named 'psycopg2'" error instead of
        # a clear one — fail loudly here instead (ADR-0019/0021).
        if value is not None and value.scheme != "postgresql+asyncpg":
            raise ValueError(
                f"database_url must use the postgresql+asyncpg:// scheme, got "
                f"{value.scheme!r} — did you mean postgresql+asyncpg://...?"
            )
        return value
