"""Remember and recall personal facts. Every memory is visible in the Memory screen."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.permissions import RiskLevel
from storage.memory_repository import MemoryRepository
from tools.base_tool import BaseTool, ToolResult


class MemoryArgs(BaseModel):
    action: Literal["remember", "recall", "forget", "list"]
    text: str = ""
    memory_id: str = ""


class MemoryTool(BaseTool):
    name = "memory"
    description = "Save a personal fact, recall related facts, list them, or forget one by id."
    risk = RiskLevel.LOW

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    @property
    def input_schema(self) -> type[BaseModel]:
        return MemoryArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, MemoryArgs):
            arguments = MemoryArgs.model_validate(arguments)
        if arguments.action == "remember":
            if not arguments.text.strip():
                return ToolResult(ok=False, message="Nothing to remember.")
            memory_id = self.repository.remember(arguments.text)
            return ToolResult(ok=True, message="Saved.", data={"id": memory_id})
        if arguments.action == "forget":
            removed = self.repository.forget(arguments.memory_id)
            return ToolResult(ok=removed, message="Forgotten." if removed else "That memory was not found.")
        if arguments.action == "list":
            items = self.repository.list_all()
            return ToolResult(ok=True, message=f"{len(items)} memories.", data={"items": items})
        items = self.repository.recall(arguments.text or "")
        if not items:
            return ToolResult(ok=True, message="No matching memories.", data={"items": []})
        lines = "\n".join(item["text"] for item in items)
        return ToolResult(ok=True, message=lines, data={"items": items})
