from pathlib import Path
from typing import cast

import pytest

from nightwatch.agents.investigator import InvestigatorService
from nightwatch.events.bus import EventBus
from nightwatch.services.incident_service import IncidentService
from nightwatch.storage.database import Base, create_database
from nightwatch.tools.investigation_tools import InvestigationToolRegistry


def test_investigator_replays_response_items_without_output_status() -> None:
    output = [
        {
            "id": "fc_123",
            "type": "function_call",
            "status": "completed",
            "call_id": "call_123",
            "name": "host_get_metrics",
            "arguments": "{}",
        },
        {
            "id": "rs_123",
            "type": "reasoning",
            "status": "completed",
            "summary": [],
            "content": None,
        },
    ]

    assert InvestigatorService._replay_output(output) == [
        {
            "id": "fc_123",
            "type": "function_call",
            "call_id": "call_123",
            "name": "host_get_metrics",
            "arguments": "{}",
        },
        {"id": "rs_123", "type": "reasoning", "summary": []},
    ]


@pytest.mark.anyio
async def test_repeated_monitoring_failures_create_one_incident(tmp_path: Path) -> None:
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'incidents.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    service = IncidentService(sessions, EventBus(10))
    kwargs = {
        "key": "http:https://demo.invalid",
        "title": "Public route unavailable: demo.invalid",
        "severity": "CRITICAL",
        "trigger": {"type": "HTTP_FAILURE"},
        "affected_resource_ids": ["domain:demo.invalid"],
        "observation_summary": "Public endpoint returned HTTP_ERROR.",
        "observation_data": {"error_type": "HTTP_ERROR"},
    }

    first = await service.report_failure(**kwargs)
    second = await service.report_failure(**kwargs)

    assert first.id == second.id
    assert len(await service.list_incidents()) == 1
    recovered = await service.report_recovery(kwargs["key"], "Public endpoint recovered.")
    assert recovered is not None
    assert recovered.state == "RECOVERED_EXTERNALLY"
    await engine.dispose()


@pytest.mark.anyio
async def test_root_cause_confirmation_requires_persisted_supporting_evidence(tmp_path: Path) -> None:
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'evidence.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    service = IncidentService(sessions, EventBus(10))
    incident = await service.report_failure(
        key="http:https://demo.invalid", title="Public route unavailable", severity="CRITICAL",
        trigger={"type": "HTTP_FAILURE"}, affected_resource_ids=["domain:demo.invalid"],
        observation_summary="Public endpoint failed.", observation_data={},
    )
    await service.begin_investigation(incident.id)
    incomplete = await service.apply_investigation_outcome(
        incident.id, summary="No proof.", confirmed_title="Route mismatch", next_step="Request review.",
        hypotheses=[{"title": "Route mismatch", "description": "No supporting observation.", "status": "CONFIRMED", "supporting_evidence_ids": []}],
    )
    assert incomplete is not None
    assert incomplete.state == "HUMAN_REQUIRED"
    await engine.dispose()


@pytest.mark.anyio
async def test_missing_provider_keeps_incident_visible_for_human_review(tmp_path: Path) -> None:
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'provider.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    service = IncidentService(sessions, EventBus(10))
    incident = await service.report_failure(
        key="http:https://demo.invalid", title="Public route unavailable", severity="CRITICAL",
        trigger={"type": "HTTP_FAILURE"}, affected_resource_ids=["domain:demo.invalid"],
        observation_summary="Public endpoint failed.", observation_data={},
    )
    investigator = InvestigatorService(service, cast(InvestigationToolRegistry, None), api_key=None, model="gpt-5.6-luna", max_tool_calls=12, timeout_seconds=1)
    await investigator.investigate(incident.id)
    current = await service.get_incident(incident.id)
    assert current is not None
    assert current.state == "HUMAN_REQUIRED"
    assert any(item.event_type == "INVESTIGATION_FAILED" for item in current.timeline)
    await engine.dispose()
