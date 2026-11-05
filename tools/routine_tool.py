"""Named routines. Each one runs a fixed, curated sequence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.permissions import RiskLevel
from tools.base_tool import BaseTool, ToolResult
from tools.computer_tool import _set_volume


class RoutineArgs(BaseModel):
    name: Literal["goodnight", "focus"]


class RoutineTool(BaseTool):
    name = "routines"
    description = "Run a named routine. goodnight mutes the PC. focus marks a quiet period."
    risk = RiskLevel.MEDIUM
    requires_confirmation = True

    @property
    def input_schema(self) -> type[BaseModel]:
        return RoutineArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, RoutineArgs):
            arguments = RoutineArgs.model_validate(arguments)
        if arguments.name == "goodnight":
            _set_volume(0)
            return ToolResult(ok=True, message="Goodnight. Volume is muted. Lock the PC from the computer tool if you want the session closed.")
        return ToolResult(ok=True, message="Focus routine acknowledged. Turn on focus mode in settings to mute nudges.")
