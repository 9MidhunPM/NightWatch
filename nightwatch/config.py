from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_prefix="NW_",
        extra="ignore",
        case_sensitive=False,
    )

    application_name: str = "NightWatch"
    version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./data/nightwatch.db"
    cors_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )
    websocket_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )
    frontend_token: SecretStr | None = None
    operator_token: SecretStr | None = None

    @field_validator("cors_origins", "websocket_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @field_validator("database_url")
    @classmethod
    def require_sqlite(cls, value: str) -> str:
        if not value.startswith("sqlite+aiosqlite:///"):
            raise ValueError("NightWatch persistence must use SQLite")
        return value

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        if self.environment == "production":
            token = self.frontend_token.get_secret_value() if self.frontend_token else ""
            if len(token) < 32:
                raise ValueError("NW_FRONTEND_TOKEN must be at least 32 characters in production")
            if not self.cors_origins or not self.websocket_origins:
                raise ValueError("Exact CORS and WebSocket origins are required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
