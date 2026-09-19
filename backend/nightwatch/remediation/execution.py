from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nightwatch.adapters.docker import DockerUnavailableError
from nightwatch.adapters.http import probe_http
from nightwatch.events.bus import EventBus
from nightwatch.events.models import EventType, RealtimeEvent
from nightwatch.models.incident import (
    ActionRecord,
    Approval,
    Incident,
    IncidentTimelineEvent,
    RepairChange,
    RepairPlan,
    VerificationCheck,
    VerificationRun,
)
from nightwatch.policy import PolicyDecision, PolicyEngine
from nightwatch.services.docker_service import DockerService
from nightwatch.services.topology_service import TopologyService


class RepairExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ComposeRouteSource:
    """One narrow persistent source adapter for the disposable demo Compose service."""

    def __init__(self, path: Path | None, project: str | None, service: str | None) -> None:
        self.path, self.project, self.service = path, project, service

    def read_port(self, field: str) -> str:
        document, labels = self._labels()
        del document
        value = labels.get(field)
        if not isinstance(value, (str, int)):
            raise RepairExecutionError("CURRENT_STATE_MISMATCH", "Compose route label is unavailable.")
        return str(value)

    def patch_port(self, field: str, expected: str, replacement: str) -> None:
        document, labels = self._labels()
        value = labels.get(field)
        if str(value) != expected:
            raise RepairExecutionError("CURRENT_STATE_MISMATCH", "Compose route changed after planning.")
        labels[field] = replacement
        assert self.path is not None
        temporary = self.path.with_suffix(self.path.suffix + ".nightwatch-tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(document, handle, sort_keys=False)
        os.replace(temporary, self.path)

    def redeploy(self) -> None:
        if self.path is None or self.project is None or self.service is None:
            raise RepairExecutionError("ACTION_FAILED", "Demo Compose source is not configured.")
        result = subprocess.run(
            ["docker", "compose", "--project-name", self.project, "--file", str(self.path), "up", "-d", "--no-deps", "--force-recreate", self.service],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode:
            raise RepairExecutionError("ACTION_FAILED", "Demo service redeploy failed.")

    def _labels(self) -> tuple[dict[str, Any], dict[str, Any]]:
        if self.path is None or self.project is None or self.service is None or not self.path.is_file():
            raise RepairExecutionError("ACTION_FAILED", "Dedicated demo Compose source is unavailable.")
        with self.path.open(encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
        if not isinstance(document, dict):
            raise RepairExecutionError("ACTION_FAILED", "Demo Compose source is invalid.")
        services = document.get("services")
        target = services.get(self.service) if isinstance(services, dict) else None
        labels = target.get("labels") if isinstance(target, dict) else None
        if not isinstance(labels, dict) or str(labels.get("nightwatch.demo")).lower() != "true":
            raise RepairExecutionError("TARGET_PROTECTED", "Only explicitly flagged demo services may be changed.")
        return document, labels


class RepairExecutionService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession], event_bus: EventBus, docker: DockerService,
        topology: TopologyService, source: ComposeRouteSource, public_url: str | None,
        internal_url: str | None, timeout_seconds: float,
    ) -> None:
        self._sessions, self._events, self._docker, self._topology = sessions, event_bus, docker, topology
        self._source, self._public_url, self._internal_url, self._timeout = source, public_url, internal_url, timeout_seconds
        self._policy = PolicyEngine()
        self._locks: dict[str, asyncio.Lock] = {}

    async def execute(self, plan_id: str) -> None:
        target = await self._target_for_plan(plan_id)
        lock = self._locks.setdefault(target, asyncio.Lock())
        async with lock:
            try:
                await self._execute_locked(plan_id)
            except RepairExecutionError as exc:
                await self._record_precondition_failure(plan_id, exc)

    async def _execute_locked(self, plan_id: str) -> None:
        async with self._sessions() as session:
            plan, change, approval = await self._preconditions(session, plan_id)
            action = ActionRecord(incident_id=plan.incident_id, repair_plan_id=plan.id, action_type=change.action_type,
                target_resource_id=change.target_resource_id, parameters={"field": change.field, "to_value": change.to_value},
                policy_decision="REQUIRE_APPROVAL", approval_id=approval.id, status="RUNNING", started_at=datetime.now(UTC),
                rollback_state={"field": change.field, "from_value": change.from_value, "source": str(self._source.path)})
            session.add(action)
            plan.status = "EXECUTING"
            self._timeline(session, plan.incident_id, "REPAIR_EXECUTION_STARTED", "Policy, approval, and current state verified.", {"action_id": action.id})
            await session.commit()
        await self._publish(EventType.REPAIR_EXECUTION_STARTED, plan.incident_id, action.id)
        patched = False
        try:
            assert change.from_value and change.to_value
            self._source.patch_port(change.field, change.from_value, change.to_value)
            patched = True
            await asyncio.to_thread(self._source.redeploy)
        except RepairExecutionError as exc:
            if patched:
                await self._restore_after_failed_apply(change)
            await self._failed(action.id, plan.incident_id, exc.code, str(exc))
            return
        except (OSError, subprocess.SubprocessError):
            if patched:
                await self._restore_after_failed_apply(change)
            await self._failed(action.id, plan.incident_id, "ACTION_FAILED", "Route change could not be applied.")
            return
        async with self._sessions() as session:
            stored = await session.get(ActionRecord, action.id)
            incident = await session.get(Incident, plan.incident_id)
            assert stored and incident
            stored.status, stored.completed_at = "SUCCEEDED", datetime.now(UTC)
            incident.state = "VERIFYING"
            self._timeline(session, incident.id, "REPAIR_EXECUTED", "Typed route change completed; independent verification started.", {"action_id": stored.id})
            await session.commit()
        await self._publish(EventType.REPAIR_EXECUTION_COMPLETED, plan.incident_id, action.id)
        await self.verify(action.id)

    async def _preconditions(self, session: AsyncSession, plan_id: str) -> tuple[RepairPlan, RepairChange, Approval]:
        plan = await session.get(RepairPlan, plan_id)
        if not plan or plan.status != "APPROVED":
            raise RepairExecutionError("APPROVAL_REQUIRED", "Current repair plan requires operator approval.")
        newer = await session.scalar(
            select(RepairPlan.id)
            .where(RepairPlan.incident_id == plan.incident_id, RepairPlan.version > plan.version)
            .limit(1)
        )
        if newer:
            raise RepairExecutionError("APPROVAL_STALE", "A newer repair plan supersedes this approval.")
        approval = await session.scalar(select(Approval).where(Approval.repair_plan_id == plan.id, Approval.plan_version == plan.version, Approval.decision == "APPROVED").order_by(Approval.created_at.desc()).limit(1))
        if not approval:
            raise RepairExecutionError("APPROVAL_STALE", "Approval does not match the current plan.")
        change = await session.scalar(select(RepairChange).where(RepairChange.repair_plan_id == plan.id).limit(1))
        if not change or change.action_type != "TRAEFIK_PATCH_SERVICE_PORT" or not change.from_value or not change.to_value or not change.to_value.isdigit() or not 1 <= int(change.to_value) <= 65535:
            raise RepairExecutionError("POLICY_DENIED", "Repair change is not an allowed route-port operation.")
        try:
            inventory = await self._docker.inventory(publish_event=False)
        except DockerUnavailableError as exc:
            raise RepairExecutionError("ACTION_FAILED", "Docker state is unavailable for execution.") from exc
        container = next((item for item in inventory.containers if "route:" in change.target_resource_id and item.compose_project == self._source.project and item.compose_service == self._source.service), None)
        protected_words = ("nightwatch", "traefik", "dokploy", "docker", "ssh", "tailscale")
        identity = " ".join((container.name, container.image, container.compose_project or "", container.compose_service or "")).lower() if container else ""
        protected = container is None or container.labels.get("nightwatch.demo") != "true" or any(word in identity for word in protected_words) or container.resource_type in {"REVERSE_PROXY", "DATABASE"}
        if self._policy.evaluate(change.action_type, protected=protected).decision != PolicyDecision.REQUIRE_APPROVAL:
            raise RepairExecutionError("TARGET_PROTECTED", "Target is not an approved disposable demo service.")
        assert container is not None
        routes = await self._topology.traefik_routes()
        route = next((item for item in routes if f"route:{item.id}" == change.target_resource_id and item.container_id == container.id), None)
        if route is None or str(route.target_port) != change.from_value or self._source.read_port(change.field) != change.from_value:
            raise RepairExecutionError("CURRENT_STATE_MISMATCH", "Route state changed after planning.")
        return plan, change, approval

    async def _restore_after_failed_apply(self, change: RepairChange) -> None:
        """Best-effort containment: never leave the persistent source at an unverified value."""
        assert change.from_value and change.to_value
        try:
            self._source.patch_port(change.field, change.to_value, change.from_value)
            await asyncio.to_thread(self._source.redeploy)
        except (RepairExecutionError, OSError, subprocess.SubprocessError):
            # The action record retains rollback state and reports failure; no success is implied here.
            return

    async def _record_precondition_failure(self, plan_id: str, error: RepairExecutionError) -> None:
        async with self._sessions() as session:
            plan = await session.get(RepairPlan, plan_id)
            if not plan:
                return
            change = await session.scalar(select(RepairChange).where(RepairChange.repair_plan_id == plan.id).limit(1))
            action = ActionRecord(
                incident_id=plan.incident_id,
                repair_plan_id=plan.id,
                action_type=change.action_type if change else "PLAN_VALIDATION",
                target_resource_id=plan.target_resource_id,
                parameters={}, policy_decision=plan.policy_decision, status="FAILED", error=error.code,
                completed_at=datetime.now(UTC),
            )
            session.add(action)
            self._timeline(session, plan.incident_id, "REPAIR_EXECUTION_FAILED", str(error), {"code": error.code, "action_id": action.id})
            await session.commit()
        await self._publish(EventType.REPAIR_EXECUTION_FAILED, plan.incident_id, action.id)

    async def rollback(self, action_id: str) -> None:
        """Restore only the captured route port after an operator-authorized rollback request."""
        async with self._sessions() as session:
            action = await session.get(ActionRecord, action_id)
            if not action or action.status != "SUCCEEDED":
                raise RepairExecutionError("ROLLBACK_FAILED", "Completed action is unavailable for rollback.")
            field = str(action.rollback_state.get("field", ""))
            old = str(action.rollback_state.get("from_value", ""))
            current = str(action.parameters.get("to_value", ""))
            if not field or not old or not current:
                raise RepairExecutionError("ROLLBACK_FAILED", "Rollback state is incomplete.")
            routes = await self._topology.traefik_routes()
            if not any(
                f"route:{item.id}" == action.target_resource_id and str(item.target_port) == current
                for item in routes
            ):
                raise RepairExecutionError("CURRENT_STATE_MISMATCH", "Route changed after repair execution.")
            action.status = "RUNNING"
            self._timeline(session, action.incident_id, "ROLLBACK_STARTED", "Restoring the captured route port.", {"action_id": action.id})
            await session.commit()
        await self._publish(EventType.ROLLBACK_STARTED, action.incident_id, action.id)
        try:
            self._source.patch_port(field, current, old)
            await asyncio.to_thread(self._source.redeploy)
            routes = await self._topology.traefik_routes()
            if not any(f"route:{item.id}" == action.target_resource_id and str(item.target_port) == old for item in routes):
                raise RepairExecutionError("ROLLBACK_FAILED", "Restored route port was not observed.")
            inventory = await self._docker.inventory(publish_event=False)
            if not any(
                item.compose_project == self._source.project
                and item.compose_service == self._source.service
                and item.state == "running"
                for item in inventory.containers
            ):
                raise RepairExecutionError("ROLLBACK_FAILED", "Restored demo service is not running.")
        except (RepairExecutionError, DockerUnavailableError, OSError, subprocess.SubprocessError) as exc:
            await self._failed(action.id, action.incident_id, "ROLLBACK_FAILED", str(exc))
            return
        async with self._sessions() as session:
            stored = await session.get(ActionRecord, action.id)
            assert stored
            stored.status, stored.completed_at = "ROLLED_BACK", datetime.now(UTC)
            run = VerificationRun(incident_id=stored.incident_id, action_record_id=stored.id, status="PASS", completed_at=datetime.now(UTC))
            session.add(run)
            await session.flush()
            session.add(VerificationCheck(verification_run_id=run.id, name="Rollback route target", status="PASS", observed=f"restored port {old}", evidence={"target_resource_id": stored.target_resource_id}))
            session.add(VerificationCheck(verification_run_id=run.id, name="Rollback application", status="PASS", observed="demo service running", evidence={}))
            self._timeline(session, stored.incident_id, "ROLLBACK_COMPLETED", "Rollback route state was independently observed.", {"action_id": stored.id, "verification_run_id": run.id})
            await session.commit()
        await self._publish(EventType.ROLLBACK_COMPLETED, action.incident_id, action.id)

    async def verify(self, action_id: str) -> None:
        async with self._sessions() as session:
            action = await session.get(ActionRecord, action_id)
            assert action
            run = VerificationRun(incident_id=action.incident_id, action_record_id=action.id)
            session.add(run)
            self._timeline(session, action.incident_id, "VERIFICATION_STARTED", "Verifier is independently checking the repaired route.", {"verification_run_id": run.id})
            await session.commit()
        await self._publish(EventType.VERIFICATION_STARTED, action.incident_id, action_id)
        checks = await self._verification_checks(action)
        async with self._sessions() as session:
            refreshed_run = await session.get(VerificationRun, run.id)
            incident = await session.get(Incident, action.incident_id)
            assert refreshed_run and incident
            run = refreshed_run
            for name, status, observed, evidence in checks:
                session.add(VerificationCheck(verification_run_id=run.id, name=name, status=status, observed=observed, evidence=evidence))
                self._timeline(session, incident.id, "VERIFICATION_CHECK_COMPLETED", f"{name}: {status}.", {"status": status})
            passed = all(item[1] == "PASS" for item in checks)
            run.status, run.completed_at = ("PASS" if passed else "FAIL"), datetime.now(UTC)
            incident.state = "RESOLVED" if passed else "VERIFICATION_FAILED"
            incident.resolved_at = datetime.now(UTC) if passed else None
            self._timeline(session, incident.id, "INCIDENT_RESOLVED" if passed else "VERIFICATION_FAILED", "Repair verified." if passed else "Repair completed but verification failed.", {"verification_run_id": run.id})
            await session.commit()
        for name, status, _, _ in checks:
            await self._events.publish(RealtimeEvent(type=EventType.VERIFICATION_CHECK_COMPLETED, incident_id=action.incident_id, payload={"name": name, "status": status}))
        await self._publish(EventType.VERIFICATION_COMPLETED, action.incident_id, action_id)
        await self._topology.snapshot(publish_event=True)

    async def _verification_checks(self, action: ActionRecord) -> list[tuple[str, str, str, dict[str, object]]]:
        expected = str(action.parameters.get("to_value", ""))
        try:
            inventory = await self._docker.inventory(publish_event=False)
            container = next((item for item in inventory.containers if item.compose_project == self._source.project and item.compose_service == self._source.service and item.labels.get("nightwatch.demo") == "true"), None)
        except DockerUnavailableError:
            container = None
        checks: list[tuple[str, str, str, dict[str, object]]] = []
        checks.append(("Application running", "PASS" if container and container.state == "running" else "FAIL", container.state if container else "container missing", {}))
        health_ok = container is not None and (container.health in {None, "healthy"})
        checks.append(("Application healthy", "PASS" if health_ok else "FAIL", container.health or "no healthcheck" if container else "container missing", {}))
        if self._internal_url:
            result = await probe_http(self._internal_url, self._timeout)
            checks.append(("Internal endpoint", "PASS" if result.reachable else "FAIL", str(result.status_code or result.error_type), result.model_dump(mode="json")))
        else:
            checks.append(("Internal endpoint", "ERROR", "internal probe is not configured", {}))
        routes = await self._topology.traefik_routes()
        route_ok = container is not None and any(f"route:{item.id}" == action.target_resource_id and item.container_id == container.id and str(item.target_port) == expected for item in routes)
        checks.append(("Route target", "PASS" if route_ok else "FAIL", f"expected port {expected}", {}))
        if self._public_url:
            result = await probe_http(self._public_url, self._timeout)
            public_status = "PASS" if result.reachable else "FAIL"
            checks.append(("Public endpoint", public_status, str(result.status_code or result.error_type), result.model_dump(mode="json")))
            checks.append(("Original failure", public_status, "not reproducible" if result.reachable else "still reproducible", result.model_dump(mode="json")))
        else:
            checks.append(("Public endpoint", "ERROR", "public probe is not configured", {}))
            checks.append(("Original failure", "ERROR", "public probe is not configured", {}))
        return checks

    async def _failed(self, action_id: str, incident_id: str, code: str, message: str) -> None:
        async with self._sessions() as session:
            action = await session.get(ActionRecord, action_id)
            plan = await session.get(RepairPlan, action.repair_plan_id) if action else None
            if action:
                action.status, action.error, action.completed_at = "FAILED", code, datetime.now(UTC)
            if plan:
                plan.status = "APPROVED"
            self._timeline(session, incident_id, "REPAIR_EXECUTION_FAILED", message, {"code": code, "action_id": action_id})
            await session.commit()
        await self._publish(EventType.REPAIR_EXECUTION_FAILED, incident_id, action_id)

    async def _target_for_plan(self, plan_id: str) -> str:
        async with self._sessions() as session:
            plan = await session.get(RepairPlan, plan_id)
            return plan.target_resource_id if plan else plan_id

    async def _publish(self, event: EventType, incident_id: str, action_id: str) -> None:
        await self._events.publish(RealtimeEvent(type=event, incident_id=incident_id, payload={"action_id": action_id}))

    @staticmethod
    def _timeline(session: AsyncSession, incident_id: str, event_type: str, summary: str, data: dict[str, object]) -> None:
        session.add(IncidentTimelineEvent(incident_id=incident_id, event_type=event_type, summary=summary, data=data))
