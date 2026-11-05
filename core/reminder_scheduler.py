"""Fires due reminders and catches up after a restart.

Recurrence: after a reminder fires, daily adds 1 day and weekly adds 7 days,
repeated until due_at is in the future. The same row stays pending.
A reminder that was already due before this process started is marked missed
instead of spoken as if it just happened. Recurring missed reminders still
advance to the next future time.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from storage.reminder_repository import Reminder, ReminderRepository

FireCallback = Callable[[Reminder, str], None]
GRACE = timedelta(minutes=2)


class ReminderScheduler:
    def __init__(self, repository: ReminderRepository, on_fire: FireCallback | None = None, workdays: frozenset[int] | None = None) -> None:
        from core.when import WORKDAYS

        self.repository = repository
        self.on_fire = on_fire
        self.workdays = workdays or WORKDAYS
        self.started_at = datetime.now(timezone.utc)

    def catch_up(self, now: datetime | None = None) -> list[Reminder]:
        moment = _utc(now)
        missed: list[Reminder] = []
        for reminder in self.repository.due(moment):
            if reminder.due_at >= self.started_at - GRACE:
                continue
            missed.append(reminder.model_copy(deep=True))
            self._settle(reminder, moment, status="missed")
            if self.on_fire:
                self.on_fire(reminder, "missed")
        return missed

    def tick(self, now: datetime | None = None) -> list[Reminder]:
        moment = _utc(now)
        fired: list[Reminder] = []
        for reminder in self.repository.due(moment):
            if reminder.due_at < self.started_at - GRACE:
                continue
            fired.append(reminder.model_copy(deep=True))
            self._settle(reminder, moment, status="fired")
            if self.on_fire:
                self.on_fire(reminder, "fired")
        return fired

    def _settle(self, reminder: Reminder, now: datetime, status: str) -> None:
        reminder.fired_at = now
        if reminder.recurrence == "none":
            reminder.status = "missed" if status == "missed" else "fired"
            self.repository.update(reminder)
            return
        step = timedelta(days=7 if reminder.recurrence == "weekly" else 1)
        next_due = reminder.due_at
        while next_due <= now or (reminder.recurrence == "weekdays" and next_due.astimezone().weekday() not in self.workdays):
            next_due += step
        reminder.due_at = next_due
        reminder.status = "pending"
        self.repository.update(reminder)


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)
