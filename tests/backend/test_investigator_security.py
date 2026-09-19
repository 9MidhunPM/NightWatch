from nightwatch.security.redaction import redact
from nightwatch.tools.investigation_tools import InvestigationToolRegistry


def test_investigator_tool_surface_has_no_mutations() -> None:
    names = {str(item["name"]) for item in InvestigationToolRegistry.definitions()}
    assert "docker_restart_container" not in names
    assert all(not name.startswith(("docker_stop", "docker_start", "shell_")) for name in names)


def test_investigator_tool_data_redacts_secrets() -> None:
    redacted = redact({"api_key": "secret", "message": "DATABASE_PASSWORD=secret Bearer secret-token", "url": "postgres://user:password@db/app?token=secret"})
    assert redacted["api_key"] == "[REDACTED]"
    assert "secret-token" not in redacted["message"]
    assert "DATABASE_PASSWORD=secret" not in redacted["message"]
    assert "password" not in redacted["url"]
