from nightwatch.adapters.dokploy import DokployAdapter


def test_parses_trpc_project_data() -> None:
    payload = {
        "result": {
            "data": {
                "json": [
                    {
                        "name": "PRISM",
                        "environments": [
                            {
                                "applications": [{"applicationId": "app-1", "name": "prism-api"}],
                                "compose": [{"composeId": "compose-1", "name": "prism-stack"}],
                            }
                        ],
                    }
                ]
            }
        }
    }
    assert DokployAdapter._projects(payload)[0]["name"] == "PRISM"


def test_extracts_trpc_service_detail_app_name() -> None:
    assert DokployAdapter._data({"result": {"data": {"json": {"appName": "prism-api-live"}}}}) == {
        "appName": "prism-api-live"
    }


def test_accepts_direct_dokploy_list_payloads() -> None:
    payload = [{"name": "NightWatch", "owner": {"login": "9MidhunPM"}}]
    assert DokployAdapter._data(payload) == payload
