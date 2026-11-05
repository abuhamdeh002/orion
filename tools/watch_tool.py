"""Leave a folder watch running in the background."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.background import BackgroundTasks
from core.permissions import RiskLevel
from tools.base_tool import BaseTool, ToolResult


class WatchArgs(BaseModel):
    folder: str = Field(min_length=1)


class WatchTool(BaseTool):
    name = "watch"
    description = "Watch a folder and report when a new file appears. Use this for downloads finishing."
    risk = RiskLevel.LOW

    def __init__(self, background: BackgroundTasks) -> None:
        self.background = background

    @property
    def input_schema(self) -> type[BaseModel]:
        return WatchArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, WatchArgs):
            arguments = WatchArgs.model_validate(arguments)
        job_id = f"watch-{len(self.background.jobs) + 1}"
        message = self.background.watch_folder(arguments.folder, job_id)
        return ToolResult(ok=not message.startswith("That folder"), message=message)
