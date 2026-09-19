from nightwatch.main import create_app


def test_health_is_public_and_reports_service() -> None:
    app = create_app()
    schema = app.openapi()
    assert "/api/health" in schema["paths"]
    assert app.title == "NightWatch"
