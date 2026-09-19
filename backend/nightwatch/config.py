from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_prefix="NW_",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    application_name: str = "Nightwatch"
    version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "sqlite+aiosqlite:///./data/nightwatch.db"
    cors_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )
    websocket_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )
    heartbeat_interval_seconds: float = Field(default=5.0, gt=0, le=300)
    event_queue_size: int = Field(default=100, ge=1, le=10_000)
    monitoring_enabled: bool = True
    monitor_interval_seconds: float = Field(default=10.0, ge=2, le=300)
    monitor_failure_threshold: int = Field(default=3, ge=1, le=20)
    monitor_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    deployment_verify_attempts: int = Field(default=3, ge=1, le=10)
    deployment_verify_retry_seconds: float = Field(default=2.0, ge=0, le=30)
    beszel_url: str | None = None
    beszel_system_id: str | None = None
    beszel_email: str | None = None
    beszel_password: SecretStr | None = None
    dokploy_url: str | None = None
    dokploy_api_key: SecretStr | None = None
    dokploy_github_id: str | None = None
    # Optional read-only GitHub token. Public repositories are inspected without
    # it; private repositories require it for manifest inference.
    github_read_token: SecretStr | None = None
    deployment_secret_catalog: SecretStr | None = None
    demo_url: str | None = Field(
        default=None, validation_alias=AliasChoices("NW_DEMO_URL", "NIGHTWATCH_DEMO_URL")
    )
    log_level: str = "INFO"
    # The Investigator deliberately has one economical, capability-appropriate model.
    # Never add an automatic fallback here: provider availability must be explicit.
    codex_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    codex_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("OPENAI_API_KEY", "NW_CODEX_API_KEY")
    )
    codex_app_server_enabled: bool = True
    codex_app_server_command: str = "codex"
    codex_app_server_timeout_seconds: float = Field(default=25.0, gt=1, le=120)
    investigator_enabled: bool = True
    investigator_max_tool_calls: int = Field(default=12, ge=1, le=15)
    investigator_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    operator_token: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("NW_OPERATOR_TOKEN")
    )
    frontend_token: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("NW_FRONTEND_TOKEN")
    )
    realtime_ticket_ttl_seconds: int = Field(default=45, ge=10, le=120)
    public_demo_url: str | None = None
    # Phase 8 deliberately has one narrow mutable boundary: a mounted disposable demo Compose file.
    demo_compose_file: Path | None = None
    demo_compose_project: str | None = None
    demo_compose_service: str | None = None
    demo_internal_health_url: str | None = None
    demo_expected_port: int = Field(default=80, ge=1, le=65535)

    @field_validator("cors_origins", "websocket_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    @field_validator("database_url")
    @classmethod
    def require_sqlite(cls, value: str) -> str:
        if not value.startswith("sqlite+aiosqlite:///"):
            raise ValueError("Nightwatch control-plane persistence must use SQLite")
        return value

    @model_validator(mode="after")
    def require_production_access_controls(self) -> Settings:
        if self.environment != "production":
            return self
        token = self.frontend_token.get_secret_value() if self.frontend_token else ""
        if len(token) < 32:
            raise ValueError("NW_FRONTEND_TOKEN must be at least 32 characters in production")
        if not self.cors_origins or not self.websocket_origins:
            raise ValueError("Exact CORS and WebSocket origins are required in production")
        if any(not origin.startswith("https://") for origin in (*self.cors_origins, *self.websocket_origins)):
            raise ValueError("Production CORS and WebSocket origins must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
