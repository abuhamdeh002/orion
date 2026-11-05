"""Create, list, complete, and delete reminders stored in SQLite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field

from core.permissions import RiskLevel
from storage.reminder_repository import Reminder, ReminderRepository
from tools.base_tool import BaseTool, ToolResult


class ReminderArgs(BaseModel):
    action: Literal["create", "list", "complete", "delete"]
    title: str | None = Field(default=None, description="What to remind about, e.g. 'drink water'. Required for create.")
    due_in_minutes: int | None = Field(default=None, ge=0, le=60 * 24 * 365)
    due_in_seconds: int | None = Field(default=None, ge=1, le=60 * 60 * 24, description="For short timers, e.g. 10 seconds")
    due_at: str | None = Field(default=None, description="ISO-8601 local or UTC time")
    reminder_id: str | None = None
    recurrence: Literal["none", "daily", "weekly", "weekdays"] = "none"


class ReminderTool(BaseTool):
    name = "reminders"
    description = (
        "Create, list, complete, or delete reminders and timers. "
        "Always give a title (what to remind about). Use due_in_seconds or due_in_minutes for timers, "
        "or due_at as an ISO time. Recurrence is none, daily, or weekly. Use action 'list' to see reminders."
    )
    risk = RiskLevel.LOW

    def __init__(self, repository: ReminderRepository) -> None:
        self.repository = repository

    @property
    def input_schema(self) -> type[BaseModel]:
        return ReminderArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, ReminderArgs):
            arguments = ReminderArgs.model_validate(arguments)
        if arguments.action == "list":
            return self._list()
        if arguments.action == "create":
            return self._create(arguments)
        if arguments.action == "complete":
            return self._complete(arguments)
        return self._delete(arguments)

    def _create(self, arguments: ReminderArgs) -> ToolResult:
        if not arguments.title:
            return ToolResult(ok=False, message="A reminder needs a title.")
        due = _resolve_due(arguments)
        if isinstance(due, ToolResult):
            return due
        reminder = self.repository.create(
            Reminder(title=arguments.title.strip(), due_at=due, recurrence=arguments.recurrence)
        )
        local = reminder.due_at.astimezone()
        return ToolResult(
            ok=True,
            message=f"Reminder set: {reminder.title} at {local.strftime('%Y-%m-%d %H:%M')}.",
            data={"id": reminder.id, "due_at": reminder.due_at.isoformat()},
        )

    def _list(self) -> ToolResult:
        reminders = self.repository.list_open()
        if not reminders:
            return ToolResult(ok=True, message="You have no open reminders.", data={"reminders": []})
        lines = []
        payload = []
        for reminder in reminders:
            local = reminder.due_at.astimezone().strftime("%Y-%m-%d %H:%M")
            lines.append(f"{reminder.id[:8]} {local} {reminder.title} ({reminder.recurrence})")
            payload.append({"id": reminder.id, "title": reminder.title, "due_at": reminder.due_at.isoformat()})
        return ToolResult(ok=True, message="Open reminders:\n" + "\n".join(lines), data={"reminders": payload})

    def _complete(self, arguments: ReminderArgs) -> ToolResult:
        reminder = self._find(arguments.reminder_id)
        if isinstance(reminder, ToolResult):
            return reminder
        reminder.status = "completed"
        reminder.fired_at = datetime.now(timezone.utc)
        self.repository.update(reminder)
        return ToolResult(ok=True, message=f"Completed '{reminder.title}'.", data={"id": reminder.id})

    def _delete(self, arguments: ReminderArgs) -> ToolResult:
        reminder = self._find(arguments.reminder_id)
        if isinstance(reminder, ToolResult):
            return reminder
        self.repository.delete(reminder.id)
        return ToolResult(ok=True, message=f"Deleted '{reminder.title}'.", data={"id": reminder.id})

    def _find(self, reminder_id: str | None) -> Reminder | ToolResult:
        if not reminder_id:
            return ToolResult(ok=False, message="A reminder id is required.")
        matches = [
            item
            for item in self.repository.list_open()
            if item.id == reminder_id or item.id.startswith(reminder_id)
        ]
        if len(matches) != 1:
            return ToolResult(ok=False, message="No single open reminder matches that id.")
        return matches[0]


def _resolve_due(arguments: ReminderArgs) -> datetime | ToolResult:
    if arguments.due_in_seconds is not None:
        return datetime.now(timezone.utc) + timedelta(seconds=arguments.due_in_seconds)
    if arguments.due_in_minutes is not None:
        return datetime.now(timezone.utc) + timedelta(minutes=arguments.due_in_minutes)
    if arguments.due_at:
        try:
            parsed = datetime.fromisoformat(arguments.due_at)
        except ValueError:
            return ToolResult(ok=False, message="due_at must be an ISO-8601 timestamp.")
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.astimezone(timezone.utc)
    return ToolResult(ok=False, message="Provide due_in_minutes or due_at.")
