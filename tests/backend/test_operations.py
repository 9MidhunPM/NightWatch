import asyncio

from nightwatch.agents.operations_tools import OperationsToolBroker
from nightwatch.models.deployment_api import DeploymentPlanRequest
from nightwatch.services.operations_service import OperationsService


class ProjectBroker:
    async def execute(self, name: str, arguments: object) -> dict[str, object]:
        assert name == "nw_find_project_containers"
        assert arguments == {"project": "ani reminder"}
        return {
            "ok": True,
            "matches": [
                {
                    "project": "AniReminder",
                    "containers": [
                        {"name": "anireminder-api", "id": "container:api"},
                        {"name": "anireminder-worker", "id": "container:worker"},
                    ],
                }
            ],
        }


def test_project_container_question_never_falls_back_to_memory_ranking() -> None:
    service = OperationsService(None, None, None, tool_broker=ProjectBroker())  # type: ignore[arg-type]

    reply = asyncio.run(service._local_evidence_answer(
        "what container runs my ani reminder project", None
    ))

    assert "anireminder-api" in reply.answer
    assert "anireminder-worker" in reply.answer
    assert "memory consumers" not in reply.answer.lower()


def test_agent_can_prepare_but_not_execute_a_deployment() -> None:
    class Plan:
        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {"id": "plan-1", "version": 1, "status": "AWAITING_APPROVAL"}

    class Deployment:
        async def create_plan(self, request: DeploymentPlanRequest) -> Plan:
            assert request.project_name == "NightWatch-Test"
            return Plan()

    async def exercise() -> None:
        broker = OperationsToolBroker(None, None, Deployment())  # type: ignore[arg-type]
        result = await broker.execute("nw_prepare_deployment", {
            "owner": "9MidhunPM", "repository": "NightWatch-Demo", "branch": "main",
            "project_name": "NightWatch-Test", "service_name": "web", "port": 3000,
            "manifest_notes": "Create an approval-gated test deployment.",
        })
        assert result["ok"] is True
        assert result["plan"] == {"id": "plan-1", "version": 1, "status": "AWAITING_APPROVAL"}
        assert "no Dokploy project" in str(result["message"])

    asyncio.run(exercise())
