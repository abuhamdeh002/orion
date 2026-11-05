"""Reminder storage. due_at is always UTC."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from storage.database import Database

Recurrence = Literal["none", "daily", "weekly", "weekdays"]
ReminderStatus = Literal["pending", "completed", "fired", "missed"]


class Reminder(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    due_at: datetime
    recurrence: Recurrence = "none"
    status: ReminderStatus = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fired_at: datetime | None = None


class ReminderRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, reminder: Reminder) -> Reminder:
        with self._db._lock:
            self._db.connection.execute(
                """
                INSERT INTO reminders (id, title, due_at, recurrence, status, created_at, fired_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                self._values(reminder),
            )
            self._db.connection.commit()
        return reminder

    def get(self, reminder_id: str) -> Reminder | None:
        with self._db._lock:
            row = self._db.connection.execute(
                "SELECT * FROM reminders WHERE id = ?",
                (reminder_id,),
            ).fetchone()
        return self._row(row) if row else None

    def list_open(self) -> list[Reminder]:
        with self._db._lock:
            rows = self._db.connection.execute(
                """
                SELECT * FROM reminders
                WHERE status = 'pending'
                ORDER BY due_at ASC
                """
            ).fetchall()
        return [self._row(row) for row in rows]

    def due(self, now: datetime) -> list[Reminder]:
        moment = _as_utc(now).isoformat()
        with self._db._lock:
            rows = self._db.connection.execute(
                """
                SELECT * FROM reminders
                WHERE status = 'pending' AND due_at <= ?
                ORDER BY due_at ASC
                """,
                (moment,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def last_fired(self) -> Reminder | None:
        """The reminder that went off most recently (what "snooze" means)."""
        with self._db._lock:
            row = self._db.connection.execute(
                "SELECT * FROM reminders WHERE fired_at IS NOT NULL AND status IN ('fired', 'pending') ORDER BY fired_at DESC LIMIT 1"
            ).fetchone()
        return self._row(row) if row else None

    def update(self, reminder: Reminder) -> None:
        with self._db._lock:
            self._db.connection.execute(
                """
                UPDATE reminders
                SET title = ?, due_at = ?, recurrence = ?, status = ?, created_at = ?, fired_at = ?
                WHERE id = ?
                """,
                (
                    reminder.title,
                    _as_utc(reminder.due_at).isoformat(),
                    reminder.recurrence,
                    reminder.status,
                    _as_utc(reminder.created_at).isoformat(),
                    _as_utc(reminder.fired_at).isoformat() if reminder.fired_at else None,
                    reminder.id,
                ),
            )
            self._db.connection.commit()

    def delete(self, reminder_id: str) -> bool:
        with self._db._lock:
            cursor = self._db.connection.execute(
                "DELETE FROM reminders WHERE id = ?",
                (reminder_id,),
            )
            self._db.connection.commit()
            return cursor.rowcount > 0

    def _values(self, reminder: Reminder) -> tuple:
        return (
            reminder.id,
            reminder.title,
            _as_utc(reminder.due_at).isoformat(),
            reminder.recurrence,
            reminder.status,
            _as_utc(reminder.created_at).isoformat(),
            _as_utc(reminder.fired_at).isoformat() if reminder.fired_at else None,
        )

    @staticmethod
    def _row(row) -> Reminder:
        return Reminder(
            id=row["id"],
            title=row["title"],
            due_at=_parse(row["due_at"]),
            recurrence=row["recurrence"],
            status=row["status"],
            created_at=_parse(row["created_at"]),
            fired_at=_parse(row["fired_at"]) if row["fired_at"] else None,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
