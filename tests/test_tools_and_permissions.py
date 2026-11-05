from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError
import pytest

from core.permissions import PermissionAction, PermissionGate, RiskLevel, ToolPermissionPolicy
from tools.base_tool import BaseTool, ToolResult
from tools.registry import ToolRegistry


class EchoArgs(BaseModel):
    text: str = Field(min_length=1)


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo text"
    risk = RiskLevel.LOW

    @property
    def input_schema(self) -> type[BaseModel]:
        return EchoArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        assert isinstance(arguments, EchoArgs)
        return ToolResult(ok=True, message=arguments.text, data={"text": arguments.text})


def test_registry_rejects_duplicates() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    with pytest.raises(ValueError):
        registry.register(EchoTool())


def test_schema_validation_rejects_empty_text() -> None:
    tool = EchoTool()
    with pytest.raises(ValidationError):
        tool.validate_args({"text": ""})


def test_low_risk_tool_is_allowed() -> None:
    gate = PermissionGate()
    decision = gate.decide("echo", RiskLevel.LOW, requires_confirmation=False)
    assert decision.action == PermissionAction.ALLOW


def test_high_risk_requires_confirmation() -> None:
    gate = PermissionGate()
    decision = gate.decide("messaging.send", RiskLevel.HIGH, requires_confirmation=True)
    assert decision.action == PermissionAction.CONFIRM


def test_tool_schemas_drop_null_unions(app_config) -> None:
    from tools.registry import create_default_registry

    schemas = create_default_registry(app_config).openai_tool_schemas()
    blob = str(schemas)
    assert "anyOf" not in blob
    names = {item["function"]["name"] for item in schemas}
    assert "time_date" in names


def test_disabled_tool_is_denied() -> None:
    gate = PermissionGate([ToolPermissionPolicy(name="echo", risk=RiskLevel.LOW, allowed=False)])
    decision = gate.decide("echo", RiskLevel.LOW, requires_confirmation=False)
    assert decision.action == PermissionAction.DENY
