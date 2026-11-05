"""Base contract for registered tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from core.permissions import RiskLevel


class ToolResult(BaseModel):
    ok: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    name: str
    description: str
    risk: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    requires_pin: bool = False
    required_permissions: tuple[str, ...] = ()

    @property
    @abstractmethod
    def input_schema(self) -> type[BaseModel]:
        raise NotImplementedError

    def needs_confirmation_for(self, arguments: dict[str, Any]) -> bool:
        """Per-call confirmation on top of the tool-wide flag. Override for risky actions only."""
        return False

    def validate_args(self, arguments: dict[str, Any]) -> BaseModel:
        return self.input_schema.model_validate(arguments)

    @abstractmethod
    def execute(self, arguments: BaseModel) -> ToolResult:
        raise NotImplementedError
