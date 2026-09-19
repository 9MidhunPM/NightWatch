from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightwatch.adapters.dokploy import DokployAdapter, DokployError
from nightwatch.models.conversation import AgentConversation, AgentTurn
from nightwatch.models.deployment import DeploymentApproval, DeploymentExecution, DeploymentPlan
from nightwatch.models.deployment_api import (
    DeploymentPlanRequest,
    DeploymentPlanResponse,
    DeploymentStatusResponse,
    GithubRepository,
    InferredDeploymentRequest,
)
from nightwatch.models.project_plan import ProjectPlan
from nightwatch.policy import PolicyDecision, PolicyEngine


class DeploymentService:
    """Approval-gated Dokploy deployment adapter with no GitHub write authority."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        dokploy: DokployAdapter,
        *,
        github_id: str | None,
        secret_catalog: str | None,
        app_server_enabled: bool,
        github_read_token: str | None = None,
        verification_attempts: int = 3,
        verification_retry_seconds: float = 2.0,
    ) -> None:
        self._sessions = sessions
        self._dokploy = dokploy
        self._github_id = github_id
        self._github_read_token = github_read_token
        self._app_server_enabled = app_server_enabled
        self._policy = PolicyEngine()
        self._execution_lock = asyncio.Lock()
        self._secret_catalog = self._parse_secret_catalog(secret_catalog)
        self._verification_attempts = verification_attempts
        self._verification_retry_seconds = verification_retry_seconds

    async def validated_status(self) -> DeploymentStatusResponse:
        if not self._dokploy.configured:
            return DeploymentStatusResponse(configured=False, github_provider_configured=bool(self._github_id), app_server_enabled=self._app_server_enabled, message="Configure NW_DOKPLOY_URL and NW_DOKPLOY_API_KEY to enable deployment planning.", diagnostic_code="DOKPLOY_NOT_CONFIGURED")
        if not self._github_id:
            return DeploymentStatusResponse(configured=False, github_provider_configured=False, app_server_enabled=self._app_server_enabled, message="Configure NW_DOKPLOY_GITHUB_ID using the provider ID shown in Dokploy's GitHub integration.", diagnostic_code="GITHUB_ID_MISSING")
        try:
            providers = await self._dokploy.github_providers()
            provider = next((item for item in providers if item.get("githubId") == self._github_id), None)
            if provider is None:
                return DeploymentStatusResponse(configured=False, github_provider_configured=True, app_server_enabled=self._app_server_enabled, message="The configured GitHub provider ID is not available to this Dokploy API key.", diagnostic_code="GITHUB_ID_NOT_FOUND", last_checked_at=datetime.now(UTC))
            await self._dokploy.test_github_connection(self._github_id)
            repositories = await self.repositories()
            git_provider = provider.get("gitProvider")
            provider_name = git_provider.get("name") if isinstance(git_provider, dict) and isinstance(git_provider.get("name"), str) else None
            return DeploymentStatusResponse(configured=True, github_provider_configured=True, app_server_enabled=self._app_server_enabled, message="GitHub and Dokploy are connected. Deployments require approval of the exact plan.", provider_name=provider_name, repository_count=len(repositories), last_checked_at=datetime.now(UTC), diagnostic_code="READY")
        except DokployError:
            return DeploymentStatusResponse(configured=False, github_provider_configured=True, app_server_enabled=self._app_server_enabled, message="Dokploy could not validate the configured GitHub provider. Check the API key, provider ID, and GitHub connection.", diagnostic_code="GITHUB_VALIDATION_FAILED", last_checked_at=datetime.now(UTC))

    def status(self) -> DeploymentStatusResponse:
        """Fast, non-network state for callers that cannot await validation."""
        ready = self._dokploy.configured and bool(self._github_id)
        return DeploymentStatusResponse(
            configured=ready,
            github_provider_configured=bool(self._github_id),
            app_server_enabled=self._app_server_enabled,
            message=(
                "Dokploy is configured; GitHub connection has not been validated yet."
                if ready
                else "Configure NW_DOKPLOY_URL, NW_DOKPLOY_API_KEY, and NW_DOKPLOY_GITHUB_ID to enable deployment planning."
            ),
        )

    async def repositories(self) -> list[GithubRepository]:
        if not self._github_id:
            return []
        raw = await self._dokploy.github_repositories(self._github_id)
        items: list[GithubRepository] = []
        for item in raw:
            owner = item.get("owner")
            if isinstance(owner, dict):
                owner = owner.get("login")
            name = item.get("name")
            if isinstance(owner, str) and isinstance(name, str):
                items.append(GithubRepository(owner=owner, name=name, private=bool(item.get("private")), default_branch=item.get("default_branch") if isinstance(item.get("default_branch"), str) else None))
        return sorted(items, key=lambda item: (item.owner.lower(), item.name.lower()))

    async def branches(self, owner: str, repository: str) -> list[str]:
        return await self._dokploy.github_branches(self._require_github_id(), owner, repository)

    async def create_plan(self, request: DeploymentPlanRequest) -> DeploymentPlanResponse:
        self._validate_domain(request.domain)
        self._require_github_id()
        if request.build_type == "compose":
            raise ValueError("Compose repositories require a manually reviewed Compose workflow in this MVP.")
        if request.secret_names and not self._secrets_available(request.secret_names):
            raise ValueError("One or more selected secret names are not available in the backend secret catalog.")
        policy = self._policy.evaluate("DOKPLOY_DEPLOY_APPLICATION", protected=False)
        if policy.decision is not PolicyDecision.REQUIRE_APPROVAL:
            raise ValueError("Dokploy deployment is not permitted by the active policy.")
        data = request.model_dump(mode="json")
        # Conversation ownership does not change the requested infrastructure.
        # Keeping it out of the digest lets an identical plan be safely reused.
        data.pop("conversation_id", None)
        digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        async with self._sessions() as session:
            existing = await session.scalar(select(DeploymentPlan).where(DeploymentPlan.plan_digest == digest))
            if existing is not None:
                if existing.status == "AWAITING_APPROVAL" and request.conversation_id:
                    existing.conversation_id = request.conversation_id
                    await self._supersede_pending_replacements(session, request, keep_plan_id=existing.id)
                    await session.commit()
                return await self._response(session, existing)
            await self._supersede_pending_replacements(session, request)
            plan = DeploymentPlan(
                owner=request.owner,
                repository=request.repository,
                branch=request.branch,
                project_name=request.project_name,
                environment_name=request.environment_name,
                service_name=request.service_name,
                build_type=request.build_type,
                build_path=request.build_path,
                dockerfile=request.dockerfile,
                port=request.port,
                domain=request.domain,
                secret_names=sorted(set(request.secret_names)),
                manifest_notes=request.manifest_notes,
                conversation_id=request.conversation_id,
                plan_digest=digest,
                policy_decision=policy.decision.value,
                policy_reason=policy.reason,
            )
            session.add(plan)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(select(DeploymentPlan).where(DeploymentPlan.plan_digest == digest))
                if existing is None:
                    raise
                return await self._response(session, existing)
            return await self._response(session, plan)

    @staticmethod
    async def _supersede_pending_replacements(
        session: AsyncSession, request: DeploymentPlanRequest, *, keep_plan_id: str | None = None
    ) -> None:
        query = select(DeploymentPlan).where(
            DeploymentPlan.status == "AWAITING_APPROVAL",
            DeploymentPlan.project_name == request.project_name,
            DeploymentPlan.environment_name == request.environment_name,
            DeploymentPlan.service_name == request.service_name,
        )
        query = query.where(
            DeploymentPlan.conversation_id == request.conversation_id
            if request.conversation_id else DeploymentPlan.conversation_id.is_(None)
        )
        for pending in (await session.scalars(query)).all():
            if pending.id != keep_plan_id:
                pending.status = "SUPERSEDED"

    async def action_context(self, conversation_id: str | None = None) -> dict[str, object]:
        """Control-plane facts, deliberately separate from runtime topology.

        Blank Dokploy projects cannot appear in Docker topology until they deploy,
        so follow-up agent turns must consult this inventory before claiming that
        an approved action did not happen.
        """
        projects: list[dict[str, object]] = []
        if self._dokploy.configured:
            try:
                projects = await self._dokploy.projects()
            except DokployError:
                projects = []
        async with self._sessions() as session:
            query = select(ProjectPlan).order_by(ProjectPlan.updated_at.desc()).limit(25)
            if conversation_id:
                query = query.where(ProjectPlan.conversation_id == conversation_id)
            project_plans = list((await session.scalars(query)).all())
            deploy_query = select(DeploymentPlan).order_by(DeploymentPlan.updated_at.desc()).limit(25)
            if conversation_id:
                deploy_query = deploy_query.where(DeploymentPlan.conversation_id == conversation_id)
            deployment_plans = list((await session.scalars(deploy_query)).all())
            return {
                "projects": projects,
                "project_actions": [self._project_plan_response(item) for item in project_plans],
                "deployment_actions": [
                    (await self._response(session, item)).model_dump(mode="json") for item in deployment_plans
                ],
            }

    async def pending_actions(self, conversation_id: str) -> list[dict[str, object]]:
        """Return only current, version-bound actions eligible for approval."""
        async with self._sessions() as session:
            turns = list((await session.scalars(select(AgentTurn).where(AgentTurn.conversation_id == conversation_id))).all())
            referenced_ids = {
                item
                for turn in turns
                for item in re.findall(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", turn.content, flags=re.IGNORECASE)
            }
            project_query = select(ProjectPlan).where(
                or_(ProjectPlan.conversation_id == conversation_id, ProjectPlan.id.in_(referenced_ids)),
                ProjectPlan.status == "AWAITING_APPROVAL",
            ).order_by(ProjectPlan.updated_at.desc())
            deploy_query = select(DeploymentPlan).where(
                or_(DeploymentPlan.conversation_id == conversation_id, DeploymentPlan.id.in_(referenced_ids)),
                DeploymentPlan.status == "AWAITING_APPROVAL",
            ).order_by(DeploymentPlan.updated_at.desc())
            projects = list((await session.scalars(project_query)).all())
            deployments = list((await session.scalars(deploy_query)).all())
            actions: list[dict[str, object]] = [
                {
                    "kind": "PROJECT",
                    "id": plan.id,
                    "version": plan.version,
                    "project_name": plan.project_name,
                    "service_name": plan.service_name,
                    "updated_at": plan.updated_at,
                }
                for plan in projects
            ]
            actions.extend(
                {
                    "kind": "DEPLOYMENT",
                    "id": plan.id,
                    "version": plan.version,
                    "project_name": plan.project_name,
                    "service_name": plan.service_name,
                    "repository": f"{plan.owner}/{plan.repository}",
                    "domain": plan.domain,
                    "updated_at": plan.updated_at,
                }
                for plan in deployments
            )
            return sorted(actions, key=lambda item: str(item["updated_at"]), reverse=True)

    async def infer_plan(self, request: InferredDeploymentRequest) -> DeploymentPlanResponse:
        """Prepare, but never execute, a deploy plan from bounded repository facts."""
        repository = next((item for item in await self.repositories() if item.owner.casefold() == request.owner.casefold() and item.name.casefold() == request.repository.casefold()), None)
        if repository is None:
            raise ValueError("That repository is not available through the configured Dokploy GitHub provider.")
        project = await self._dokploy.project_by_name(request.project_name)
        application = await self._dokploy.application_by_name(request.project_name, request.environment_name, request.service_name)
        if project is None or application is None:
            raise ValueError("The requested Dokploy project and blank service must exist before a deployment can be planned.")
        facts = await self._repository_facts(request.owner, request.repository, repository.default_branch or "main", repository.private)
        if facts is None:
            raise ValueError("Nightwatch could not safely inspect this repository. Configure NW_GITHUB_READ_TOKEN for a private repository or provide its build method and application port.")
        build_type, inferred_port, dockerfile, notes = facts
        port = request.port or inferred_port
        if request.port is not None:
            notes = f"Application port {port} was explicitly requested by the operator. {notes}"
        return await self.create_plan(DeploymentPlanRequest(
            owner=request.owner, repository=request.repository, branch=repository.default_branch or "main",
            project_name=request.project_name, environment_name=request.environment_name, service_name=request.service_name,
            build_type=build_type, build_path="/", dockerfile=dockerfile, port=port, domain=request.domain,
            manifest_notes=notes, conversation_id=request.conversation_id,
        ))

    async def _repository_facts(self, owner: str, repository: str, branch: str, private: bool) -> tuple[str, int, str | None, str] | None:
        headers = {"accept": "application/vnd.github+json", "user-agent": "nightwatch"}
        if self._github_read_token:
            headers["authorization"] = f"Bearer {self._github_read_token}"
        if private and not self._github_read_token:
            return None
        base = f"https://api.github.com/repos/{owner}/{repository}/contents"
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                listing = await client.get(base, params={"ref": branch}, headers=headers)
                if not listing.is_success or not isinstance(listing.json(), list):
                    return None
                names = {str(item.get("name")) for item in listing.json() if isinstance(item, dict)}
                if "Dockerfile" in names:
                    dockerfile = await client.get(f"{base}/Dockerfile", params={"ref": branch}, headers=headers)
                    if not dockerfile.is_success or not isinstance(dockerfile.json(), dict):
                        return None
                    import base64
                    content = dockerfile.json().get("content")
                    if not isinstance(content, str):
                        return None
                    text = base64.b64decode(content).decode("utf-8")
                    exposed = re.search(r"(?im)^\s*EXPOSE\s+(\d+)", text)
                    if exposed:
                        return ("dockerfile", int(exposed.group(1)), "/Dockerfile", f"Dockerfile detected at repository root and declares EXPOSE {exposed.group(1)}.")
                    return ("dockerfile", 3000, "/Dockerfile", "Dockerfile detected at repository root but declares no EXPOSE port; Nightwatch falls back to 3000.")
                if "package.json" not in names:
                    return None
                package = await client.get(f"{base}/package.json", params={"ref": branch}, headers=headers)
                if not package.is_success or not isinstance(package.json(), dict):
                    return None
                import base64
                content = package.json().get("content")
                if not isinstance(content, str):
                    return None
                manifest = json.loads(base64.b64decode(content).decode("utf-8"))
                scripts = manifest.get("scripts") if isinstance(manifest, dict) else None
                if not isinstance(scripts, dict) or not isinstance(scripts.get("build"), str):
                    return None
                dependencies = {**(manifest.get("dependencies") or {}), **(manifest.get("devDependencies") or {})}
                if "next" in dependencies:
                    return ("dockerfile", 3000, None, "Next.js package detected. Dokploy will build the repository; expected application port is 3000.")
                return ("static", 80, None, "Static Node build detected from package.json; Dokploy will serve the build output on port 80.")
        except (httpx.HTTPError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    async def create_project_plan(self, project_name: str, service_name: str | None = None, conversation_id: str | None = None) -> dict[str, object]:
        cleaned = project_name.strip()
        if len(cleaned) < 2 or len(cleaned) > 80:
            raise ValueError("Project names must contain 2 to 80 characters.")
        policy = self._policy.evaluate("DOKPLOY_CREATE_PROJECT", protected=False)
        if policy.decision is not PolicyDecision.REQUIRE_APPROVAL:
            raise ValueError("Dokploy project creation is not permitted by the active policy.")
        cleaned_service = service_name.strip() if isinstance(service_name, str) and service_name.strip() else None
        if cleaned_service is not None and not 2 <= len(cleaned_service) <= 80:
            raise ValueError("Service names must contain 2 to 80 characters.")
        async with self._sessions() as session:
            existing = await session.scalar(select(ProjectPlan).where(ProjectPlan.project_name == cleaned))
            if existing is None:
                existing = ProjectPlan(project_name=cleaned, service_name=cleaned_service, conversation_id=conversation_id, policy_reason=policy.reason)
                session.add(existing)
                await session.commit()
            elif existing.status == "AWAITING_APPROVAL":
                # A pending plan is an exact, reusable request.  It must always
                # belong to the conversation that is currently presenting it;
                # otherwise the operator is shown prose with no action to approve.
                if existing.service_name is None and cleaned_service is not None:
                    existing.service_name = cleaned_service
                if conversation_id:
                    existing.conversation_id = conversation_id
                await session.commit()
            return self._project_plan_response(existing)

    async def approve_project_plan(self, plan_id: str, version: int, decision: str, conversation_id: str | None = None) -> dict[str, object] | None:
        async with self._sessions() as session:
            plan = await session.get(ProjectPlan, plan_id)
            if plan is None or plan.version != version:
                return None
            # Approval clicks are safely repeatable. A network retry must report
            # the already-started/completed operation rather than look like a
            # failed approval to the operator.
            if plan.status != "AWAITING_APPROVAL":
                return self._project_plan_response(plan)
            plan.status = "APPROVED" if decision == "APPROVED" else "REJECTED"
            if conversation_id:
                plan.conversation_id = conversation_id
            await session.commit()
        if decision == "APPROVED":
            asyncio.create_task(self._execute_project_plan(plan_id), name=f"nightwatch-project-{plan_id}")
        async with self._sessions() as session:
            plan = await session.get(ProjectPlan, plan_id)
            return self._project_plan_response(plan) if plan else None

    async def project_plan(self, plan_id: str) -> dict[str, object] | None:
        async with self._sessions() as session:
            plan = await session.get(ProjectPlan, plan_id)
            return self._project_plan_response(plan) if plan else None

    async def project_plans(self, conversation_id: str | None = None) -> list[dict[str, object]]:
        async with self._sessions() as session:
            query = select(ProjectPlan).order_by(ProjectPlan.updated_at.desc()).limit(50)
            if conversation_id:
                query = query.where(ProjectPlan.conversation_id == conversation_id)
            return [self._project_plan_response(item) for item in (await session.scalars(query)).all()]

    async def _execute_project_plan(self, plan_id: str, *, resume: bool = False) -> None:
        async with self._execution_lock:
            async with self._sessions() as session:
                plan = await session.get(ProjectPlan, plan_id)
                if plan is None or (plan.status != "APPROVED" and not (resume and plan.status == "RUNNING")):
                    return
                plan.status = "RUNNING"
                await session.commit()
            try:
                project = await self._dokploy.project_by_name(plan.project_name)
                created_project = project is None
                if project is None:
                    try:
                        await self._dokploy.create_project(plan.project_name)
                    except DokployError:
                        # A successful write with an unexpected response must be
                        # reconciled against Dokploy before it is called a failure.
                        pass
                    project = await self._dokploy.project_by_name(plan.project_name)
                if project is None or not isinstance(project.get("projectId"), str):
                    raise DokployError("Dokploy did not expose the requested project after creation.")
                project_id = project["projectId"]
                environment = await self._dokploy.environment_by_name(plan.project_name, plan.environment_name)
                if environment is None:
                    try:
                        await self._dokploy.create_environment(project_id, plan.environment_name)
                    except DokployError:
                        pass
                    environment = await self._dokploy.environment_by_name(plan.project_name, plan.environment_name)
                if environment is None or not isinstance(environment.get("environmentId"), str):
                    raise DokployError("Dokploy did not expose the requested environment after creation.")
                application_id: str | None = None
                created_service = False
                if plan.service_name:
                    application = await self._dokploy.application_by_name(plan.project_name, plan.environment_name, plan.service_name)
                    created_service = application is None
                    if application is None:
                        try:
                            await self._dokploy.create_application(environment["environmentId"], plan.service_name)
                        except DokployError:
                            pass
                        application = await self._dokploy.application_by_name(plan.project_name, plan.environment_name, plan.service_name)
                    if application is None or not isinstance(application.get("applicationId"), str):
                        raise DokployError("Dokploy did not expose the requested service after creation.")
                    application_id = application["applicationId"]
                outcome = self._project_outcome(plan.project_name, project_id, plan.service_name, application_id, created_project, created_service)
                async with self._sessions() as session:
                    plan = await session.get(ProjectPlan, plan_id)
                    if plan:
                        plan.status, plan.detail = "VERIFIED", outcome
                        await session.commit()
                await self._append_project_outcome(plan_id, outcome, successful=True)
            except DokployError as exc:
                detail = f"Dokploy could not verify this action: {str(exc)[:400]}"
                async with self._sessions() as session:
                    plan = await session.get(ProjectPlan, plan_id)
                    if plan:
                        plan.status, plan.detail = "FAILED", detail
                        await session.commit()
                await self._append_project_outcome(plan_id, detail, successful=False)

    @staticmethod
    def _project_plan_response(plan: ProjectPlan) -> dict[str, object]:
        return {"id": plan.id, "version": plan.version, "project_name": plan.project_name, "environment_name": plan.environment_name, "service_name": plan.service_name, "conversation_id": plan.conversation_id, "status": plan.status, "policy_reason": plan.policy_reason, "detail": plan.detail, "kind": "CREATE_DOKPLOY_PROJECT"}

    @staticmethod
    def _project_outcome(project_name: str, project_id: str, service_name: str | None, application_id: str | None, created_project: bool, created_service: bool) -> str:
        project_verb = "Created" if created_project else "Reused"
        result = f"{project_verb} and verified Dokploy project {project_name} ({project_id})."
        if service_name and application_id:
            service_verb = "Created" if created_service else "Reused"
            result += f" {service_verb} and verified blank application service {service_name} ({application_id}) in production."
        return result

    async def _append_project_outcome(self, plan_id: str, detail: str, *, successful: bool) -> None:
        async with self._sessions() as session:
            plan = await session.get(ProjectPlan, plan_id)
            if plan is None or not plan.conversation_id:
                return
            conversation = await session.get(AgentConversation, plan.conversation_id)
            if conversation is None:
                return
            heading = "## Action completed" if successful else "## Action needs attention"
            session.add(AgentTurn(conversation_id=conversation.id, role="assistant", content=f"{heading}\n\n{detail}"))
            conversation.updated_at = datetime.now(UTC)
            await session.commit()

    async def plans(self, conversation_id: str | None = None) -> list[DeploymentPlanResponse]:
        async with self._sessions() as session:
            query = select(DeploymentPlan).order_by(DeploymentPlan.updated_at.desc()).limit(50)
            if conversation_id:
                query = query.where(DeploymentPlan.conversation_id == conversation_id)
            plans = list((await session.scalars(query)).all())
            return [await self._response(session, plan) for plan in plans]

    async def approve(self, plan_id: str, version: int, decision: str, conversation_id: str | None = None) -> DeploymentPlanResponse | None:
        async with self._sessions() as session:
            plan = await session.get(DeploymentPlan, plan_id)
            if plan is None or plan.version != version:
                return None
            if plan.status == "SUPERSEDED" or plan.status == "REJECTED":
                return None
            if plan.status != "AWAITING_APPROVAL":
                return await self._response(session, plan)
            plan.status = "APPROVED" if decision == "APPROVED" else "REJECTED"
            if conversation_id:
                plan.conversation_id = conversation_id
            session.add(DeploymentApproval(deployment_plan_id=plan.id, plan_version=version, decision=decision, actor="operator"))
            await session.commit()
            response = await self._response(session, plan)
        if decision == "APPROVED":
            asyncio.create_task(self.execute(plan_id), name=f"nightwatch-deploy-{plan_id}")
        return response

    async def recover_incomplete_plans(self) -> int:
        """Resume only persisted, approval-backed work after a control-plane restart."""
        async with self._sessions() as session:
            project_plans = list(
                (await session.scalars(select(ProjectPlan).where(ProjectPlan.status.in_(("APPROVED", "RUNNING")))))
                .all()
            )
            deployments = list(
                (
                    await session.scalars(
                        select(DeploymentPlan).where(
                            DeploymentPlan.status.in_(("APPROVED", "RUNNING", "VERIFYING"))
                        )
                    )
                ).all()
            )
        tasks: list[asyncio.Task[None]] = []
        for project_plan in project_plans:
            tasks.append(
                asyncio.create_task(
                    self._execute_project_plan(
                        project_plan.id, resume=project_plan.status == "RUNNING"
                    ),
                    name=f"nightwatch-recover-project-{project_plan.id}",
                )
            )
        for deployment_plan in deployments:
            if deployment_plan.status == "VERIFYING":
                tasks.append(
                    asyncio.create_task(
                        self._verify(deployment_plan.id, deployment_plan.domain),
                        name=f"nightwatch-recover-verify-{deployment_plan.id}",
                    )
                )
            else:
                tasks.append(
                    asyncio.create_task(
                        self.execute(
                            deployment_plan.id, resume=deployment_plan.status == "RUNNING"
                        ),
                        name=f"nightwatch-recover-deploy-{deployment_plan.id}",
                    )
                )
        if tasks:
            await asyncio.gather(*tasks)
        return len(tasks)

    async def execute(self, plan_id: str, *, resume: bool = False) -> None:
        async with self._execution_lock:
            async with self._sessions() as session:
                plan = await session.get(DeploymentPlan, plan_id)
                if plan is None or (plan.status != "APPROVED" and not (resume and plan.status == "RUNNING")):
                    return
                existing = await session.scalar(select(DeploymentExecution).where(DeploymentExecution.deployment_plan_id == plan.id))
                if existing is not None and not resume:
                    return
                if existing is None:
                    execution = DeploymentExecution(deployment_plan_id=plan.id, status="RUNNING", detail="Reconciling Dokploy project and service.")
                    session.add(execution)
                else:
                    existing.status = "RUNNING"
                    existing.detail = "Resuming persisted Dokploy deployment reconciliation."
                plan.status = "RUNNING"
                await session.commit()
            try:
                project = await self._dokploy.project_by_name(plan.project_name)
                if project is None:
                    try:
                        await self._dokploy.create_project(plan.project_name)
                    except DokployError:
                        pass
                    project = await self._dokploy.project_by_name(plan.project_name)
                if project is None or not isinstance(project.get("projectId"), str):
                    raise DokployError("Dokploy did not expose the deployment project.")
                project_id = project["projectId"]
                environment = await self._dokploy.environment_by_name(plan.project_name, plan.environment_name)
                if environment is None:
                    try:
                        await self._dokploy.create_environment(project_id, plan.environment_name)
                    except DokployError:
                        pass
                    environment = await self._dokploy.environment_by_name(plan.project_name, plan.environment_name)
                if environment is None or not isinstance(environment.get("environmentId"), str):
                    raise DokployError("Dokploy did not expose the deployment environment.")
                environment_id = environment["environmentId"]
                application = await self._dokploy.application_by_name(plan.project_name, plan.environment_name, plan.service_name)
                if application is None:
                    try:
                        await self._dokploy.create_application(environment_id, plan.service_name)
                    except DokployError:
                        pass
                    application = await self._dokploy.application_by_name(plan.project_name, plan.environment_name, plan.service_name)
                if application is None or not isinstance(application.get("applicationId"), str):
                    raise DokployError("Dokploy did not expose the deployment service.")
                application_id = application["applicationId"]
                await self._dokploy.configure_application(application_id, self._application_configuration(plan))
                await self._dokploy.save_github_provider(application_id, self._github_configuration(plan))
                await self._dokploy.save_build_type(application_id, self._build_configuration(plan))
                await self._verify_application_configuration(application_id, plan)
                if plan.secret_names:
                    await self._dokploy.save_application_environment(application_id, self._environment_for(plan.secret_names))
                if plan.domain:
                    await self._dokploy.create_domain(application_id, plan.domain, plan.port)
                await self._dokploy.deploy_application(application_id)
                await self._complete(plan.id, "VERIFYING", "Dokploy accepted the deployment; waiting for service verification.", project_id, environment_id, application_id)
                await self._verify(plan.id, plan.domain)
            except DokployError as exc:
                await self._failed(plan.id, str(exc))
            except (OSError, TypeError, ValueError):
                await self._failed(plan.id, "Deployment could not complete safely. Review the Dokploy deployment log.")

    async def _verify(self, plan_id: str, domain: str | None) -> None:
        if not domain:
            await self._complete(plan_id, "VERIFYING", "No domain was selected; verify the application from Dokploy.")
            return
        detail = "HTTPS endpoint is not reachable yet."
        for attempt in range(1, self._verification_attempts + 1):
            try:
                status_code = await self._probe_domain(domain)
                if self._is_healthy_status(status_code):
                    await self._complete(
                        plan_id,
                        "VERIFIED",
                        f"HTTPS endpoint returned healthy HTTP {status_code} on verification attempt {attempt}.",
                    )
                    return
                detail = f"HTTPS endpoint returned HTTP {status_code}, which is not a healthy deployment response."
            except httpx.HTTPError:
                detail = "HTTPS endpoint is not reachable yet."
            if attempt < self._verification_attempts:
                await asyncio.sleep(self._verification_retry_seconds)
        await self._complete(
            plan_id,
            "VERIFYING",
            f"{detail} Verify the intended application in Dokploy, then retry verification.",
        )

    @staticmethod
    async def _probe_domain(domain: str) -> int:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.get(f"https://{domain}")
        return response.status_code

    @staticmethod
    def _is_healthy_status(status_code: int) -> bool:
        return 200 <= status_code < 400

    async def _complete(self, plan_id: str, status: str, detail: str, project_id: str | None = None, environment_id: str | None = None, application_id: str | None = None) -> None:
        async with self._sessions() as session:
            plan = await session.get(DeploymentPlan, plan_id)
            execution = await session.scalar(select(DeploymentExecution).where(DeploymentExecution.deployment_plan_id == plan_id))
            if plan is None or execution is None:
                return
            plan.status = status
            execution.status, execution.detail = status, detail[:1024]
            if project_id:
                execution.project_id = project_id
            if environment_id:
                execution.environment_id = environment_id
            if application_id:
                execution.application_id = application_id
            await session.commit()
        if status in {"VERIFIED", "FAILED"}:
            await self._append_deployment_outcome(plan_id, detail, successful=status == "VERIFIED")

    async def _append_deployment_outcome(self, plan_id: str, detail: str, *, successful: bool) -> None:
        async with self._sessions() as session:
            plan = await session.get(DeploymentPlan, plan_id)
            if plan is None or not plan.conversation_id:
                return
            conversation = await session.get(AgentConversation, plan.conversation_id)
            if conversation is None:
                return
            heading = "## Deployment completed" if successful else "## Deployment needs attention"
            session.add(AgentTurn(conversation_id=conversation.id, role="assistant", content=f"{heading}\n\n{detail}"))
            conversation.updated_at = datetime.now(UTC)
            await session.commit()

    async def _failed(self, plan_id: str, detail: str) -> None:
        await self._complete(plan_id, "FAILED", detail)

    async def _response(self, session: AsyncSession, plan: DeploymentPlan) -> DeploymentPlanResponse:
        execution = await session.scalar(select(DeploymentExecution).where(DeploymentExecution.deployment_plan_id == plan.id))
        return DeploymentPlanResponse(
            id=plan.id, version=plan.version, status=plan.status, owner=plan.owner, repository=plan.repository,
            branch=plan.branch, project_name=plan.project_name, environment_name=plan.environment_name,
            service_name=plan.service_name, build_type=plan.build_type, build_path=plan.build_path,
            dockerfile=plan.dockerfile, port=plan.port, domain=plan.domain, secret_names=plan.secret_names,
            manifest_notes=plan.manifest_notes, conversation_id=plan.conversation_id, plan_digest=plan.plan_digest, policy_decision=plan.policy_decision,
            policy_reason=plan.policy_reason, execution_status=execution.status if execution else None,
            execution_detail=execution.detail if execution else None, created_at=plan.created_at, updated_at=plan.updated_at,
        )

    def _application_configuration(self, plan: DeploymentPlan) -> dict[str, object]:
        return {
            "sourceType": "github", "port": plan.port, "autoDeploy": False,
        }

    def _github_configuration(self, plan: DeploymentPlan) -> dict[str, object]:
        return {"githubId": self._require_github_id(), "owner": plan.owner, "repository": plan.repository, "branch": plan.branch, "buildPath": plan.build_path, "triggerType": "push"}

    @staticmethod
    def _build_configuration(plan: DeploymentPlan) -> dict[str, object]:
        return {"buildType": plan.build_type, "dockerfile": plan.dockerfile, "dockerContextPath": plan.build_path, "dockerBuildStage": None, "publishDirectory": None, "isStaticSpa": False}

    async def _verify_application_configuration(self, application_id: str, plan: DeploymentPlan) -> None:
        application = await self._dokploy.application_one(application_id)
        expected = {
            "sourceType": "github", "githubId": self._require_github_id(), "owner": plan.owner,
            "repository": plan.repository, "branch": plan.branch, "buildType": plan.build_type,
            "port": plan.port, "autoDeploy": False,
        }
        mismatches = [field for field, value in expected.items() if application.get(field) != value]
        if plan.dockerfile is not None and application.get("dockerfile") != plan.dockerfile:
            mismatches.append("dockerfile")
        if mismatches:
            raise DokployError(f"Dokploy configuration verification failed for: {', '.join(mismatches)}.")

    def _environment_for(self, names: list[str]) -> str:
        return "\n".join(f"{name}={self._secret_catalog[name]}" for name in names)

    def _secrets_available(self, names: list[str]) -> bool:
        return all(name in self._secret_catalog for name in names)

    def _require_github_id(self) -> str:
        if not self._github_id:
            raise DokployError("NW_DOKPLOY_GITHUB_ID is not configured.")
        return self._github_id

    @staticmethod
    def _parse_secret_catalog(value: str | None) -> dict[str, str]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return {key: item for key, item in parsed.items() if isinstance(key, str) and isinstance(item, str)} if isinstance(parsed, dict) else {}

    @staticmethod
    def _validate_domain(domain: str | None) -> None:
        if domain is None:
            return
        parsed = urlparse(f"https://{domain}")
        if not parsed.hostname or parsed.hostname != domain or "/" in domain:
            raise ValueError("Domain must be a hostname without a protocol or path.")
