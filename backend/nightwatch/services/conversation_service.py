from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightwatch.models.conversation import AgentConversation, AgentTurn
from nightwatch.models.deployment_api import DeploymentPlanRequest
from nightwatch.models.operations_api import (
    AgentActivity,
    AgentConversationDetail,
    AgentConversationSummary,
    AgentConversationTurn,
    AgentMessageResponse,
)
from nightwatch.services.deployment_service import DeploymentService
from nightwatch.services.operations_service import OperationsService

EventSink = Callable[[dict[str, object]], Awaitable[None]]


class ConversationService:
    """Durable user-visible conversation history around scoped Codex threads."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], operations: OperationsService, deployment: DeploymentService) -> None:
        self._sessions = sessions
        self._operations = operations
        self._deployment = deployment

    async def create(self) -> AgentConversationDetail:
        async with self._sessions() as session:
            conversation = AgentConversation()
            session.add(conversation)
            await session.commit()
            return self._detail(conversation, [], [])

    async def list(self, *, include_archived: bool = False) -> list[AgentConversationSummary]:
        async with self._sessions() as session:
            query = select(AgentConversation).order_by(AgentConversation.updated_at.desc()).limit(100)
            if not include_archived:
                query = query.where(AgentConversation.archived_at.is_(None))
            rows = list((await session.scalars(query)).all())
            return [self._summary(row) for row in rows]

    async def get(self, conversation_id: str) -> AgentConversationDetail | None:
        async with self._sessions() as session:
            conversation = await session.get(AgentConversation, conversation_id)
            if conversation is None:
                return None
            turns = list((await session.scalars(select(AgentTurn).where(AgentTurn.conversation_id == conversation_id).order_by(AgentTurn.created_at.asc()).limit(200))).all())
            summary = self._summary(conversation)
        return AgentConversationDetail(**summary.model_dump(), turns=[self._turn(turn) for turn in turns], pending_actions=await self._deployment.pending_actions(conversation_id))

    async def archive(self, conversation_id: str) -> bool:
        async with self._sessions() as session:
            conversation = await session.get(AgentConversation, conversation_id)
            if conversation is None:
                return False
            conversation.archived_at = datetime.now(UTC)
            await session.commit()
            return True

    async def delete(self, conversation_id: str) -> bool:
        async with self._sessions() as session:
            conversation = await session.get(AgentConversation, conversation_id)
            if conversation is None:
                return False
            if not await self._deployment.delete_for_conversation(conversation_id, session):
                return False
            await session.execute(delete(AgentTurn).where(AgentTurn.conversation_id == conversation_id))
            await session.delete(conversation)
            await session.commit()
            return True

    async def respond(self, conversation_id: str | None, message: str, on_event: EventSink | None = None) -> tuple[AgentMessageResponse, str]:
        if conversation_id is None:
            created = await self.create()
            conversation_id = created.id
        async with self._sessions() as session:
            conversation = await session.get(AgentConversation, conversation_id)
            if conversation is None or conversation.archived_at is not None:
                raise ValueError("Conversation is unavailable. Start a new conversation.")
            session.add(AgentTurn(conversation_id=conversation.id, role="user", content=message))
            if conversation.title == "New infrastructure conversation":
                conversation.title = self._title(message)
            conversation.updated_at = datetime.now(UTC)
            await session.commit()
            thread_id = conversation.codex_thread_id
        approval = await self._approve_from_message(conversation_id, message, on_event)
        prepared = await self._prepare_hosted_deployment_from_message(conversation_id, message, on_event) if approval is None else None
        if prepared is None and approval is None:
            prepared = await self._prepare_project_from_message(conversation_id, message, on_event)
        reply = approval if approval is not None else prepared if prepared is not None else await self._operations.answer(message, on_event, conversation_id=conversation_id, codex_thread_id=thread_id)
        reply.pending_actions = await self._deployment.pending_actions(conversation_id)
        async with self._sessions() as session:
            conversation = await session.get(AgentConversation, conversation_id)
            if conversation is None:
                raise ValueError("Conversation was removed while the agent was responding.")
            resolved_thread = self._operations.conversation_thread_id(conversation_id)
            if resolved_thread:
                conversation.codex_thread_id = resolved_thread
            conversation.updated_at = datetime.now(UTC)
            session.add(AgentTurn(
                conversation_id=conversation_id, role="assistant", content=reply.answer,
                activity=[item.model_dump(mode="json") for item in reply.activity],
                findings=[item.model_dump(mode="json") for item in reply.findings],
                citations=[item.model_dump(mode="json") for item in reply.citations],
            ))
            await session.commit()
        return reply, conversation_id

    async def _approve_from_message(
        self, conversation_id: str, message: str, on_event: EventSink | None
    ) -> AgentMessageResponse | None:
        if not re.fullmatch(r"\s*(?:i\s+)?(?:approve|approve\s+(?:it|this|that)|yes\s*,?\s*(?:approve|deploy)|yes\s*,?\s*deploy)\s*[.!]?\s*", message, flags=re.IGNORECASE):
            return None
        actions = await self._deployment.pending_actions(conversation_id)
        if not actions:
            return AgentMessageResponse(answer="## No pending action\n\nThere is no version-valid Dokploy action awaiting approval in this conversation.")
        if len(actions) > 1:
            targets = "\n".join(
                f"- **{item['project_name']}** / **{item.get('service_name') or 'project'}** — `{str(item['kind']).lower()}`"
                for item in actions
            )
            return AgentMessageResponse(answer=f"## Choose an action to approve\n\nMore than one action is pending. Use the side approval panel to select the exact action:\n\n{targets}")
        action = actions[0]
        action_id, action_version, action_kind = str(action["id"]), int(str(action["version"])), str(action["kind"])
        if on_event:
            await on_event({"type": "tool", "tool": "nightwatch_approve_pending_action", "status": "running", "arguments": {"kind": action_kind, "plan_id": action_id, "version": action_version}})
        if action_kind == "PROJECT":
            project_result = await self._deployment.approve_project_plan(action_id, action_version, "APPROVED", conversation_id)
            accepted = project_result is not None
            detail = project_result.get("detail") if project_result else None
            state = project_result.get("status") if project_result else None
        else:
            deployment_result = await self._deployment.approve(action_id, action_version, "APPROVED", conversation_id)
            accepted = deployment_result is not None
            detail = deployment_result.execution_detail if deployment_result else None
            state = deployment_result.status if deployment_result else None
        if on_event:
            await on_event({"type": "tool", "tool": "nightwatch_approve_pending_action", "status": "completed" if accepted else "failed", "result": {"status": state, "detail": detail}})
        if not accepted:
            return AgentMessageResponse(answer="## Approval could not be applied\n\nThat action changed before approval. Refresh the conversation and approve its replacement plan.")
        action_name = f"**{action['project_name']}**" + (f" / **{action['service_name']}**" if action.get("service_name") else "")
        return AgentMessageResponse(
            answer=f"## Approval accepted\n\nNightwatch is executing and independently verifying {action_name}. A completion message will appear here when Dokploy reports the terminal result.",
            activity=[AgentActivity(tool="nightwatch_approve_pending_action", label="Approve pending Dokploy action", status="completed", detail=f"{action_kind.lower()} action accepted")],
        )

    async def _prepare_project_from_message(
        self, conversation_id: str, message: str, on_event: EventSink | None
    ) -> AgentMessageResponse | None:
        """Turn explicit create-project language into a persisted typed action.

        This runs before Codex so an approval card is never based on model prose.
        """
        project_match = re.search(
            r"\bcreate\s+(?:a\s+)?(?:new\s+)?(?:dokploy\s+)?project\s+(?:called|named)\s+(.+?)(?=\s+(?:and\s+)?create\b|[,.]|$)",
            message,
            flags=re.IGNORECASE,
        )
        if project_match is None:
            return None
        project_name = project_match.group(1).strip(" \t\"'`")
        # Only inspect the tail after the project clause.  Otherwise the first
        # word "project" can be mistaken for part of a service name.
        service_match = re.search(
            r"\bcreate\s+(?:a\s+|an\s+)?(?:blank\s+)?(?:(.+?)\s+)?service(?:\s+(?:in|within)\b|[,.]|$)",
            message[project_match.end():],
            flags=re.IGNORECASE,
        )
        service_name = service_match.group(1).strip(" \t\"'`") if service_match and service_match.group(1) else None
        if on_event:
            await on_event({"type": "tool", "tool": "nw_prepare_project", "status": "running", "arguments": {"project_name": project_name, "service_name": service_name}})
        try:
            plan = await self._deployment.create_project_plan(project_name, service_name, conversation_id)
        except ValueError as exc:
            return AgentMessageResponse(answer=f"## I could not prepare that action\n\n{exc}")
        if on_event:
            await on_event({"type": "tool", "tool": "nw_prepare_project", "status": "completed", "result": {"plan": plan}})
        target = f"**{plan['project_name']}**" + (f" / **{plan['service_name']}**" if plan.get("service_name") else "")
        if plan.get("status") == "AWAITING_APPROVAL":
            return AgentMessageResponse(
                answer=f"## Approval required\n\nI prepared the exact Dokploy creation action for {target}. Review it in the approval panel, then click **Approve exact action** or reply **I approve**.",
                activity=[AgentActivity(tool="nw_prepare_project", label="Prepare Dokploy creation action", detail="A version-bound action is awaiting approval.", arguments={"project_name": project_name, "service_name": service_name}, result={"plan": plan})],
            )
        return AgentMessageResponse(
            answer=f"## Existing action\n\nThe recorded action for {target} is **{plan.get('status', 'unknown')}**. Nightwatch will not create a duplicate.",
            activity=[AgentActivity(tool="nw_prepare_project", label="Inspect Dokploy creation action", detail="An existing action was reused.", arguments={"project_name": project_name, "service_name": service_name}, result={"plan": plan})],
        )

    async def _prepare_hosted_deployment_from_message(
        self, conversation_id: str, message: str, on_event: EventSink | None
    ) -> AgentMessageResponse | None:
        """Prepare one deploy action when the message requests a hosted service.

        A deployment plan already reconciles its project and application before it
        configures GitHub, a build type, domain, and deployment.  Preparing a
        separate blank-service action first drops those requested settings.
        """
        project_match = re.search(
            r"\bcreate\s+(?:a\s+)?(?:new\s+)?(?:dokploy\s+)?project\s+(?:called|named)\s+(.+?)(?=\s+(?:and\s+)?create\b|[,.]|$)",
            message,
            flags=re.IGNORECASE,
        )
        if project_match is None or not re.search(r"\bdockerfile\b", message, flags=re.IGNORECASE):
            return None
        service_match = re.search(
            r"\bcreate\s+(?:a\s+|an\s+)?(?:(?:simple|blank)\s+)?service\s+(?:called|named)\s+([A-Za-z0-9_.-]+)",
            message[project_match.end():],
            flags=re.IGNORECASE,
        )
        repository_match = re.search(
            r"\bconnect(?:\s+it)?\s+to\s+(?:my\s+)?([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)\s+repository\b",
            message,
            flags=re.IGNORECASE,
        )
        domain_match = re.search(r"\bhost(?:\s+it)?\s+on\s+([A-Za-z0-9.-]+)", message, flags=re.IGNORECASE)
        port_match = re.search(r"\b(?:via\s+)?port\s+(\d{1,5})\b", message, flags=re.IGNORECASE)
        if service_match is None or repository_match is None or domain_match is None or port_match is None:
            return None
        project_name = project_match.group(1).strip(" \t\"'`")
        service_name = service_match.group(1).strip(" \t\"'`")
        repository_ref = repository_match.group(1)
        repositories = await self._deployment.repositories()
        if "/" in repository_ref:
            owner, repository = repository_ref.split("/", maxsplit=1)
            selected = next(
                (item for item in repositories if item.owner.casefold() == owner.casefold() and item.name.casefold() == repository.casefold()),
                None,
            )
        else:
            matches = [item for item in repositories if item.name.casefold() == repository_ref.casefold()]
            selected = matches[0] if len(matches) == 1 else None
        if selected is None:
            return AgentMessageResponse(
                answer="## I could not prepare that deployment\n\nThe requested repository was not uniquely available through the connected Dokploy GitHub provider. Use `owner/repository` in the request."
            )
        port = int(port_match.group(1))
        if not 1 <= port <= 65535:
            return AgentMessageResponse(answer="## I could not prepare that deployment\n\nThe requested application port must be between 1 and 65535.")
        request = DeploymentPlanRequest(
            owner=selected.owner,
            repository=selected.name,
            branch=selected.default_branch or "main",
            project_name=project_name,
            service_name=service_name,
            build_type="dockerfile",
            build_path="/",
            dockerfile="Dockerfile",
            port=port,
            domain=domain_match.group(1).lower(),
            manifest_notes=f"Operator requested Dockerfile deployment for {selected.owner}/{selected.name} on port {port} with domain {domain_match.group(1).lower()}.",
            conversation_id=conversation_id,
        )
        try:
            plan = await self._deployment.create_plan(request)
        except ValueError as exc:
            return AgentMessageResponse(answer=f"## I could not prepare that deployment\n\n{exc}")
        arguments = {
            "project_name": project_name,
            "service_name": service_name,
            "repository": f"{selected.owner}/{selected.name}",
            "branch": request.branch,
            "port": port,
            "domain": request.domain,
            "build_type": "dockerfile",
        }
        if on_event:
            await on_event({"type": "tool", "tool": "nw_prepare_deployment", "status": "completed", "arguments": arguments, "result": {"plan": plan.model_dump(mode="json")}})
        return AgentMessageResponse(
            answer=(
                "## Approval required\n\n"
                f"I prepared one exact hosted-service deployment for **{project_name}** / **{service_name}**. "
                "Approval will create or reuse the project and service, configure the repository and Dockerfile, attach the domain, and deploy it."
            ),
            activity=[AgentActivity(tool="nw_prepare_deployment", label="Prepare hosted Dokploy deployment", detail="One version-bound deployment action is awaiting approval.", arguments=arguments, result={"plan": plan.model_dump(mode="json")})],
        )

    @staticmethod
    def _title(message: str) -> str:
        compact = " ".join(message.split())
        return compact[:157] + "..." if len(compact) > 160 else compact

    @staticmethod
    def _summary(item: AgentConversation) -> AgentConversationSummary:
        return AgentConversationSummary(id=item.id, title=item.title, updated_at=item.updated_at, archived=item.archived_at is not None)

    def _turn(self, turn: AgentTurn) -> AgentConversationTurn:
        return AgentConversationTurn(
            id=turn.id, role=turn.role, content=turn.content, activity=turn.activity or [], findings=turn.findings or [], citations=turn.citations or [], created_at=turn.created_at
        )

    def _detail(self, item: AgentConversation, turns: Sequence[AgentTurn], pending_actions: Sequence[dict[str, object]]) -> AgentConversationDetail:
        return AgentConversationDetail(**self._summary(item).model_dump(), turns=[self._turn(turn) for turn in turns], pending_actions=list(pending_actions))
