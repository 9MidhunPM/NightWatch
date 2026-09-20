from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightwatch.adapters.dokploy import DokployAdapter, DokployError
from nightwatch.models.deployment_api import DokployActionRequest
from nightwatch.models.dokploy_action import DokployActionPlan
from nightwatch.policy.engine import PolicyDecision, PolicyEngine


class DokployActionService:
    """Persisted, version-bound operational changes for existing Dokploy resources."""

    _database_kinds = {"postgres", "mysql", "mariadb", "mongo", "redis"}
    _allowed = {
        "application": {"start", "stop", "redeploy", "deploy", "cancel_deployment", "reload", "update", "delete"},
        "compose": {"start", "stop", "redeploy", "deploy", "cancel_deployment", "update", "delete"},
        "postgres": {"start", "stop", "reload", "update"}, "mysql": {"start", "stop", "reload", "update"},
        "mariadb": {"start", "stop", "reload", "update"}, "mongo": {"start", "stop", "reload", "update"},
        "redis": {"start", "stop", "reload", "update"},
        "domain": {"domain_toggle", "domain_update", "delete"},
        "project": {"update", "delete"}, "environment": {"update", "delete"},
    }

    def __init__(self, sessions: async_sessionmaker[AsyncSession], dokploy: DokployAdapter) -> None:
        self._sessions, self._dokploy, self._policy = sessions, dokploy, PolicyEngine()

    @staticmethod
    def _snapshot(record: dict[str, object]) -> str:
        stable = {key: record.get(key) for key in ("name", "applicationId", "composeId", "domainId", "projectId", "environmentId", "appName", "applicationStatus", "composeStatus", "host", "port", "enabled") if key in record}
        return json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _safe_parameters(value: dict[str, object]) -> dict[str, object]:
        encoded = json.dumps(value, sort_keys=True, default=str)
        if len(encoded) > 4096:
            raise ValueError("Action parameters are too large.")
        forbidden = {"password", "secret", "token", "apikey", "api_key", "privatekey", "private_key"}
        if any(str(key).casefold().replace("-", "_") in forbidden for key in value):
            raise ValueError("Secret values are never accepted in operational action parameters.")
        return value

    async def create_plan(self, request: DokployActionRequest) -> dict[str, object]:
        if request.action not in self._allowed.get(request.target_kind, set()):
            raise ValueError("That operation is not supported for this Dokploy resource type.")
        if request.target_kind in self._database_kinds and request.action == "delete":
            raise ValueError("NightWatch never deletes databases or volumes.")
        result = self._policy.evaluate(f"DOKPLOY_ACTION_{request.action.upper()}", protected=False)
        if result.decision != PolicyDecision.REQUIRE_APPROVAL:
            raise ValueError(result.reason)
        parameters = self._safe_parameters(request.parameters)
        record = await self._dokploy.resource_one(request.target_kind, request.target_id)
        observed_name = str(record.get("name") or record.get("host") or "").strip()
        if not observed_name or observed_name.casefold() != request.target_name.strip().casefold():
            raise ValueError("The Dokploy target no longer matches the requested resource name.")
        expected_state = self._snapshot(record)
        digest = hashlib.sha256(json.dumps({"action": request.action, "kind": request.target_kind, "id": request.target_id, "parameters": parameters, "state": expected_state}, sort_keys=True).encode()).hexdigest()
        async with self._sessions() as session:
            existing = await session.scalar(select(DokployActionPlan).where(DokployActionPlan.request_digest == digest, DokployActionPlan.status == "AWAITING_APPROVAL"))
            if existing:
                return self._response(existing)
            plan = DokployActionPlan(action=request.action, target_kind=request.target_kind, target_id=request.target_id, target_name=observed_name, project_name=request.project_name, parameters=parameters, expected_state=expected_state, request_digest=digest, policy_reason=result.reason, conversation_id=request.conversation_id)
            session.add(plan)
            await session.commit()
            return self._response(plan)

    async def plans(self, conversation_id: str | None = None) -> list[dict[str, object]]:
        async with self._sessions() as session:
            query = select(DokployActionPlan).order_by(DokployActionPlan.updated_at.desc()).limit(100)
            if conversation_id:
                query = query.where(DokployActionPlan.conversation_id == conversation_id)
            return [self._response(item) for item in (await session.scalars(query)).all()]

    async def pending_actions(self, conversation_id: str) -> list[dict[str, object]]:
        return [{"kind": "ACTION", "id": item["id"], "version": item["version"], "project_name": item.get("project_name") or "Dokploy", "service_name": item["target_name"]} for item in await self.plans(conversation_id) if item["status"] == "AWAITING_APPROVAL"]

    async def approve(self, plan_id: str, version: int, decision: str, confirmation: str | None = None) -> dict[str, object] | None:
        async with self._sessions() as session:
            plan = await session.get(DokployActionPlan, plan_id)
            if plan is None or plan.status != "AWAITING_APPROVAL" or plan.version != version:
                return None
            if decision == "REJECTED":
                plan.status, plan.detail = "REJECTED", "Rejected by the operator."
                await session.commit()
                return self._response(plan)
            if plan.action == "delete" and (confirmation or "").strip().casefold() != plan.target_name.casefold():
                raise ValueError("Type the exact target name before approving deletion.")
            plan.status, plan.detail = "EXECUTING", "Approved; validating the target before Dokploy execution."
            await session.commit()
        try:
            record = await self._dokploy.resource_one(plan.target_kind, plan.target_id)
            if self._snapshot(record) != plan.expected_state:
                raise ValueError("Dokploy target changed after the plan was prepared.")
            await self._dokploy.perform_action(plan.target_kind, plan.target_id, plan.action, plan.parameters)
            if plan.action != "delete":
                await self._dokploy.resource_one(plan.target_kind, plan.target_id)
            status, detail = "VERIFIED", "Dokploy accepted the action and the target was read back."
        except (DokployError, ValueError) as exc:
            status, detail = "FAILED", str(exc)
        async with self._sessions() as session:
            current = await session.get(DokployActionPlan, plan_id)
            if current is None:
                return None
            current.status, current.detail = status, detail
            await session.commit()
            return self._response(current)

    async def delete_plan(self, plan_id: str) -> bool:
        async with self._sessions() as session:
            plan = await session.get(DokployActionPlan, plan_id)
            if plan is None or plan.status not in {"VERIFIED", "FAILED", "REJECTED"}:
                return False
            await session.delete(plan)
            await session.commit()
            return True

    async def delete_for_conversation(self, conversation_id: str, session: AsyncSession) -> None:
        for plan in (await session.scalars(select(DokployActionPlan).where(DokployActionPlan.conversation_id == conversation_id))).all():
            await session.delete(plan)

    @staticmethod
    def _response(plan: DokployActionPlan) -> dict[str, object]:
        return {"id": plan.id, "version": plan.version, "status": plan.status, "action": plan.action, "target_kind": plan.target_kind, "target_id": plan.target_id, "target_name": plan.target_name, "project_name": plan.project_name, "parameters": plan.parameters, "policy_reason": plan.policy_reason, "detail": plan.detail, "conversation_id": plan.conversation_id, "created_at": plan.created_at.isoformat(), "updated_at": plan.updated_at.isoformat(), "requires_exact_confirmation": plan.action == "delete"}
