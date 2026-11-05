from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.reminder_scheduler import ReminderScheduler
from storage.database import Database
from storage.reminder_repository import Reminder, ReminderRepository
from tools.reminder_tool import ReminderArgs, ReminderTool


def _repo(tmp_path):
    database = Database(tmp_path / "orion.db")
    return database, ReminderRepository(database)


def test_create_list_complete_delete(tmp_path) -> None:
    database, repo = _repo(tmp_path)
    tool = ReminderTool(repo)
    created = tool.execute(ReminderArgs(action="create", title="Stand up", due_in_minutes=15))
    assert created.ok is True
    listed = tool.execute(ReminderArgs(action="list"))
    assert "Stand up" in listed.message
    reminder_id = created.data["id"]
    completed = tool.execute(ReminderArgs(action="complete", reminder_id=reminder_id[:8]))
    assert completed.ok is True
    assert tool.execute(ReminderArgs(action="list")).data["reminders"] == []
    database.close()


def test_scheduler_fires_and_advances_daily(tmp_path) -> None:
    database, repo = _repo(tmp_path)
    now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    repo.create(Reminder(title="Water", due_at=now - timedelta(minutes=1), recurrence="daily"))
    events: list[str] = []
    scheduler = ReminderScheduler(repo, on_fire=lambda reminder, kind: events.append(kind))
    scheduler.started_at = now - timedelta(minutes=5)
    fired = scheduler.tick(now)
    assert len(fired) == 1
    assert events == ["fired"]
    pending = repo.list_open()
    assert len(pending) == 1
    assert pending[0].due_at == now - timedelta(minutes=1) + timedelta(days=1)
    database.close()


def test_scheduler_marks_missed_after_restart(tmp_path) -> None:
    database, repo = _repo(tmp_path)
    now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    repo.create(Reminder(title="Old", due_at=now - timedelta(hours=3), recurrence="none"))
    scheduler = ReminderScheduler(repo)
    scheduler.started_at = now
    missed = scheduler.catch_up(now)
    assert len(missed) == 1
    stored = repo.get(missed[0].id)
    assert stored is not None
    assert stored.status == "missed"
    assert scheduler.tick(now) == []
    database.close()


def test_delete_requires_existing_id(tmp_path) -> None:
    database, repo = _repo(tmp_path)
    result = ReminderTool(repo).execute(ReminderArgs(action="delete", reminder_id="missing"))
    assert result.ok is False
    database.close()
