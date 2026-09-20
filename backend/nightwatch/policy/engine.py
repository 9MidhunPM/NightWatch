from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    risk_level: str
    reason: str


class PolicyEngine:
    """Deterministic, fail-closed policy for typed future repair actions."""

    _BLOCKED = (
        "DELETE",
        "REMOVE",
        "FORMAT",
        "SHELL",
        "FIREWALL",
        "SSH",
        "VOLUME",
        "DATABASE",
    )

    def evaluate(self, action_type: str, *, protected: bool) -> PolicyResult:
        normalized = action_type.upper()
        # Dokploy action plans are typed by the service layer.  Every one remains
        # approval-gated; database/volume deletion is never registered there.
        if normalized.startswith("DOKPLOY_ACTION_") and not protected:
            return PolicyResult(
                PolicyDecision.REQUIRE_APPROVAL,
                "MEDIUM" if "DELETE" not in normalized else "HIGH",
                "A human approval is required before this Dokploy operation.",
            )
        if protected or any(token in normalized for token in self._BLOCKED):
            return PolicyResult(
                PolicyDecision.DENY,
                "BLOCKED",
                "Protected or destructive action is denied.",
            )
        if normalized in {
            "TRAEFIK_PATCH_SERVICE_PORT",
            "DOCKER_RESTART_CONTAINER",
            "DOCKER_START_CONTAINER",
            "DOKPLOY_CREATE_PROJECT",
            "DOKPLOY_CREATE_ENVIRONMENT",
            "DOKPLOY_CREATE_APPLICATION",
            "DOKPLOY_CONFIGURE_APPLICATION",
            "DOKPLOY_BIND_APPLICATION_SECRETS",
            "DOKPLOY_CREATE_DOMAIN",
            "DOKPLOY_DEPLOY_APPLICATION",
        }:
            return PolicyResult(
                PolicyDecision.REQUIRE_APPROVAL,
                "MEDIUM",
                "A human approval is required before this infrastructure change.",
            )
        return PolicyResult(
            PolicyDecision.DENY,
            "BLOCKED",
            "Action type is not allowlisted for Nightwatch.",
        )
