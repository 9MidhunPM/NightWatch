import pytest
from pydantic import ValidationError

from nightwatch.config import Settings


def test_configuration_loads_comma_separated_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "NW_CORS_ORIGINS", "http://localhost:3000,https://nightwatch.test"
    )
    settings = Settings()
    assert settings.cors_origins == ("http://localhost:3000", "https://nightwatch.test")


def test_configuration_rejects_non_sqlite_control_plane_database() -> None:
    with pytest.raises(ValidationError, match="must use SQLite"):
        Settings(database_url="postgresql+asyncpg://localhost/nightwatch")


def test_optional_codex_and_demo_configuration_loads_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NW_CODEX_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "codex-key")
    monkeypatch.setenv("NW_PUBLIC_DEMO_URL", "https://demo.example.test")

    settings = Settings()

    assert settings.codex_model == "gpt-5.6-luna"
    assert settings.codex_api_key is not None
    assert settings.codex_api_key.get_secret_value() == "codex-key"
    assert settings.public_demo_url == "https://demo.example.test"
