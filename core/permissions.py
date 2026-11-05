"""Permission gate for tool execution. Tools are a security boundary."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PermissionAction(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class PermissionDecision(BaseModel):
    action: PermissionAction
    reason: str


class ToolPermissionPolicy(BaseModel):
    name: str
    risk: RiskLevel
    requires_confirmation: bool = False
    allowed: bool = True
    description: str = ""


class PermissionGate:
    """Least-privilege checks. High-risk tools always require confirmation."""

    HIGH_RISK_DEFAULTS = frozenset(
        {"messaging.send", "files.delete", "system.change_settings", "purchase"}
    )

    def __init__(self, policies: list[ToolPermissionPolicy] | None = None) -> None:
        self._policies = {policy.name: policy for policy in (policies or [])}

    def register(self, policy: ToolPermissionPolicy) -> None:
        self._policies[policy.name] = policy

    def decide(self, tool_name: str, risk: RiskLevel, requires_confirmation: bool) -> PermissionDecision:
        policy = self._policies.get(tool_name)
        if policy and not policy.allowed:
            return PermissionDecision(action=PermissionAction.DENY, reason="This tool is disabled in settings.")
        if tool_name in self.HIGH_RISK_DEFAULTS or risk == RiskLevel.HIGH or requires_confirmation:
            return PermissionDecision(
                action=PermissionAction.CONFIRM,
                reason="This action needs your confirmation before it can run.",
            )
        return PermissionDecision(action=PermissionAction.ALLOW, reason="Read-only or low-risk action.")
