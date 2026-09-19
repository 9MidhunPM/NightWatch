import pytest
from sqlalchemy import select

from nightwatch.adapters.dokploy import DokployAdapter, DokployError
from nightwatch.models.conversation import AgentConversation, AgentTurn
from nightwatch.models.deployment import DeploymentPlan
from nightwatch.models.deployment_api import DeploymentPlanRequest, InferredDeploymentRequest
from nightwatch.models.project_plan import ProjectPlan
from nightwatch.policy import PolicyDecision, PolicyEngine
from nightwatch.services.conversation_service import ConversationService
from nightwatch.services.deployment_service import DeploymentService
from nightwatch.storage.database import Base, create_database


def test_deployment_request_keeps_only_secret_names_at_the_public_boundary() -> None:
    service = DeploymentService(
        None,  # type: ignore[arg-type]
        DokployAdapter("https://dokploy.test", "test-key"),
        github_id="github-provider",
        secret_catalog='{"DATABASE_URL":"never-returned"}',
        app_server_enabled=True,
    )
    request = DeploymentPlanRequest(
        owner="9MidhunPM",
        repository="sample-app",
        branch="main",
        project_name="sample-app",
        service_name="sample-app-web",
        build_type="dockerfile",
        build_path="/",
        dockerfile="Dockerfile",
        port=3000,
        domain="sample.midhunpm.in",
        secret_names=["DATABASE_URL"],
        manifest_notes="Dockerfile exposes port 3000 and reads DATABASE_URL.",
    )
    assert request.secret_names == ["DATABASE_URL"]
    assert service._secrets_available(request.secret_names)
    assert service._environment_for(request.secret_names) == "DATABASE_URL=never-returned"
    assert service.status().configured is True


def test_dokploy_actions_are_explicitly_approval_gated() -> None:
    policy = PolicyEngine()
    assert policy.evaluate("DOKPLOY_CREATE_PROJECT", protected=False).decision == PolicyDecision.REQUIRE_APPROVAL
    assert policy.evaluate("DOKPLOY_DEPLOY_APPLICATION", protected=False).decision == PolicyDecision.REQUIRE_APPROVAL
    assert policy.evaluate("DOKPLOY_DELETE_PROJECT", protected=False).decision == PolicyDecision.DENY


def test_deployment_health_accepts_only_success_or_redirect_responses() -> None:
    assert DeploymentService._is_healthy_status(200)
    assert DeploymentService._is_healthy_status(302)
    assert not DeploymentService._is_healthy_status(404)
    assert not DeploymentService._is_healthy_status(503)


class _AmbiguousCreateDokploy:
    """Simulates Dokploy committing writes before returning an unusable body."""

    configured = True

    def __init__(self) -> None:
        self.project_created = False
        self.application_created = False

    async def project_by_name(self, name: str):
        if not self.project_created:
            return None
        return {"projectId": "project-1", "name": name, "environments": [{"environmentId": "production-1", "name": "production", "applications": [{"applicationId": "app-1", "name": "nightwatch-web"}] if self.application_created else []}]}

    async def environment_by_name(self, project_name: str, name: str):
        project = await self.project_by_name(project_name)
        return project["environments"][0] if project else None

    async def application_by_name(self, project_name: str, environment_name: str, name: str):
        environment = await self.environment_by_name(project_name, environment_name)
        if environment is None:
            return None
        return next((item for item in environment["applications"] if item["name"] == name), None)

    async def create_project(self, name: str) -> str:
        self.project_created = True
        raise DokployError("Dokploy did not return projectId.")

    async def create_environment(self, project_id: str, name: str) -> str:
        return "production-1"

    async def create_application(self, environment_id: str, name: str) -> str:
        self.application_created = True
        raise DokployError("Dokploy did not return applicationId.")


@pytest.mark.anyio
async def test_project_action_reconciles_ambiguous_dokploy_writes_and_persists_outcome(tmp_path) -> None:
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'project-actions.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        service = DeploymentService(sessions, _AmbiguousCreateDokploy(), github_id=None, secret_catalog=None, app_server_enabled=True)  # type: ignore[arg-type]
        async with sessions() as session:
            conversation = AgentConversation(title="Create service")
            session.add(conversation)
            await session.commit()
            conversation_id = conversation.id
        plan = await service.create_project_plan("NightWatch-Test", "nightwatch-web")
        async with sessions() as session:
            stored = await session.get(ProjectPlan, plan["id"])
            assert stored is not None
            stored.status = "APPROVED"
            stored.conversation_id = conversation_id
            await session.commit()
        await service._execute_project_plan(str(plan["id"]))
        result = await service.project_plan(str(plan["id"]))
        assert result is not None
        assert result["status"] == "VERIFIED"
        assert "Created and verified Dokploy project NightWatch-Test (project-1)." in str(result["detail"])
        assert "Created and verified blank application service nightwatch-web (app-1)" in str(result["detail"])
        async with sessions() as session:
            turns = list((await session.scalars(select(AgentTurn))).all())
            assert len(turns) == 1
            assert "Action completed" in turns[0].content
    finally:
        await engine.dispose()


class _UnusedOperations:
    def conversation_thread_id(self, conversation_id: str) -> None:
        return None


@pytest.mark.anyio
async def test_project_request_creates_a_conversation_bound_approvable_action(tmp_path) -> None:
    """Regression: a narrated project request must have an approval-card action."""
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'conversation-actions.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        deployment = DeploymentService(sessions, _AmbiguousCreateDokploy(), github_id=None, secret_catalog=None, app_server_enabled=True)  # type: ignore[arg-type]
        conversations = ConversationService(sessions, _UnusedOperations(), deployment)  # type: ignore[arg-type]
        reply, conversation_id = await conversations.respond(
            None, "create a project called NightWatch-Test-6 and create a NightWatch-Sample Service in it"
        )
        assert len(reply.pending_actions) == 1
        action = reply.pending_actions[0]
        assert action["kind"] == "PROJECT"
        assert action["project_name"] == "NightWatch-Test-6"
        assert action["service_name"] == "NightWatch-Sample"
        detail = await conversations.get(conversation_id)
        assert detail is not None
        assert [item["id"] for item in detail.pending_actions] == [action["id"]]
        async with sessions() as session:
            plan = await session.get(ProjectPlan, action["id"])
            assert plan is not None
            assert plan.conversation_id == conversation_id
            assert plan.status == "AWAITING_APPROVAL"
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_pending_project_plan_is_rebound_to_the_active_conversation(tmp_path) -> None:
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'rebound-actions.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        service = DeploymentService(sessions, _AmbiguousCreateDokploy(), github_id=None, secret_catalog=None, app_server_enabled=True)  # type: ignore[arg-type]
        async with sessions() as session:
            conversation = AgentConversation(title="Rebound action")
            session.add(conversation)
            await session.commit()
            conversation_id = conversation.id
        original = await service.create_project_plan("NightWatch-Test", "web")
        rebound = await service.create_project_plan("NightWatch-Test", "web", conversation_id)
        assert rebound["id"] == original["id"]
        assert (await service.pending_actions(conversation_id))[0]["id"] == original["id"]
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_chat_approval_uses_the_pending_conversation_action(tmp_path) -> None:
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'chat-approval.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        deployment = DeploymentService(sessions, _AmbiguousCreateDokploy(), github_id=None, secret_catalog=None, app_server_enabled=True)  # type: ignore[arg-type]
        conversations = ConversationService(sessions, _UnusedOperations(), deployment)  # type: ignore[arg-type]
        _prepared, conversation_id = await conversations.respond(None, "create a project called NightWatch-Approve")
        reply, _ = await conversations.respond(conversation_id, "I approve")
        assert "Approval accepted" in reply.answer
        assert reply.pending_actions == []
    finally:
        await engine.dispose()


def _deployment_request(*, port: int, conversation_id: str) -> DeploymentPlanRequest:
    return DeploymentPlanRequest(
        owner="9MidhunPM", repository="prompt-to-website", branch="main",
        project_name="NightWatch-Test", environment_name="production", service_name="nightwatch-web",
        build_type="dockerfile", build_path="/", dockerfile="Dockerfile", port=port,
        domain="nightwatch-test.midhunpm.in", manifest_notes="The Dockerfile and exposed application port were reviewed.",
        conversation_id=conversation_id,
    )


@pytest.mark.anyio
async def test_replacement_deployment_plan_supersedes_the_old_approval(tmp_path) -> None:
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'replacement-plans.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        service = DeploymentService(sessions, _AmbiguousCreateDokploy(), github_id="github-provider", secret_catalog=None, app_server_enabled=True)  # type: ignore[arg-type]
        async with sessions() as session:
            conversation = AgentConversation(title="Revise deployment")
            session.add(conversation)
            await session.commit()
            conversation_id = conversation.id
        original = await service.create_plan(_deployment_request(port=3000, conversation_id=conversation_id))
        replacement = await service.create_plan(_deployment_request(port=80, conversation_id=conversation_id))
        reused_replacement = await service.create_plan(_deployment_request(port=80, conversation_id=conversation_id))
        assert replacement.port == 80
        assert reused_replacement.id == replacement.id
        assert (await service.approve(original.id, original.version, "APPROVED", conversation_id)) is None
        actions = await service.pending_actions(conversation_id)
        assert [item["id"] for item in actions] == [replacement.id]
        async with sessions() as session:
            stale = await session.get(DeploymentPlan, original.id)
            assert stale is not None and stale.status == "SUPERSEDED"
    finally:
        await engine.dispose()


def test_application_configuration_includes_the_dokploy_github_provider() -> None:
    service = DeploymentService(None, _AmbiguousCreateDokploy(), github_id="github-provider", secret_catalog=None, app_server_enabled=True)  # type: ignore[arg-type]
    plan = DeploymentPlan(**_deployment_request(port=80, conversation_id="conversation").model_dump(), plan_digest="digest", policy_decision="REQUIRE_APPROVAL", policy_reason="Approval required")
    application = service._application_configuration(plan)
    github = service._github_configuration(plan)
    build = service._build_configuration(plan)
    assert application == {"sourceType": "github", "port": 80, "autoDeploy": False}
    assert github["githubId"] == "github-provider"
    assert github["repository"] == "prompt-to-website"
    assert build["buildType"] == "dockerfile"
    assert build["dockerfile"] == "Dockerfile"


def test_inferred_deployment_request_preserves_an_explicit_application_port() -> None:
    request = InferredDeploymentRequest(
        owner="9MidhunPM", repository="prompt-to-website", project_name="NightWatch-Test",
        service_name="web", domain="nightwatch-test.midhunpm.in", port=80,
    )
    assert request.port == 80


class _ConfiguredDokploy:
    configured = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def project_by_name(self, name: str):
        return {"projectId": "project-1", "name": name}

    async def environment_by_name(self, project_name: str, name: str):
        return {"environmentId": "environment-1", "name": name}

    async def application_by_name(self, project_name: str, environment_name: str, name: str):
        return {"applicationId": "application-1", "name": name}

    async def configure_application(self, application_id: str, payload: dict[str, object]) -> None:
        self.calls.append(("application.update", payload))

    async def save_github_provider(self, application_id: str, payload: dict[str, object]) -> None:
        self.calls.append(("application.saveGithubProvider", payload))

    async def save_build_type(self, application_id: str, payload: dict[str, object]) -> None:
        self.calls.append(("application.saveBuildType", payload))

    async def application_one(self, application_id: str):
        return {
            "sourceType": "github", "githubId": "github-provider", "owner": "9MidhunPM",
            "repository": "prompt-to-website", "branch": "main", "buildType": "dockerfile",
            "port": 80, "autoDeploy": False, "dockerfile": "Dockerfile",
        }

    async def deploy_application(self, application_id: str) -> None:
        self.calls.append(("application.deploy", {}))


@pytest.mark.anyio
async def test_deployment_execution_persists_github_and_dockerfile_before_deploy(tmp_path) -> None:
    engine, sessions = create_database(f"sqlite+aiosqlite:///{tmp_path / 'configuration-execution.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        dokploy = _ConfiguredDokploy()
        service = DeploymentService(sessions, dokploy, github_id="github-provider", secret_catalog=None, app_server_enabled=True)  # type: ignore[arg-type]
        async with sessions() as session:
            conversation = AgentConversation(title="Configure Dockerfile deployment")
            session.add(conversation)
            await session.commit()
            conversation_id = conversation.id
        request = _deployment_request(port=80, conversation_id=conversation_id)
        request.domain = None
        plan = await service.create_plan(request)
        async with sessions() as session:
            stored = await session.get(DeploymentPlan, plan.id)
            assert stored is not None
            stored.status = "APPROVED"
            await session.commit()
        await service.execute(plan.id)
        assert [name for name, _payload in dokploy.calls] == [
            "application.update", "application.saveGithubProvider", "application.saveBuildType", "application.deploy",
        ]
        assert dokploy.calls[0][1]["port"] == 80
        assert dokploy.calls[1][1]["repository"] == "prompt-to-website"
        assert dokploy.calls[2][1]["buildType"] == "dockerfile"
        result = next(item for item in await service.plans() if item.id == plan.id)
        assert result.status == "VERIFYING"
    finally:
        await engine.dispose()
