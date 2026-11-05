"""Persist conversation messages in SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from core.conversation_manager import ChatMessage
from storage.database import Database


class ConversationRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, message: ChatMessage) -> None:
        tool_calls = json.dumps(message.tool_calls) if message.tool_calls else None
        with self._db._lock:
            self._db.connection.execute(
                """
                INSERT OR REPLACE INTO messages
                    (id, role, content, created_at, tool_name, tool_call_id, tool_calls_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.role,
                    message.content,
                    message.created_at.isoformat(),
                    message.tool_name,
                    message.tool_call_id,
                    tool_calls,
                ),
            )
            self._db.connection.commit()

    def load_recent(self, limit: int) -> list[ChatMessage]:
        with self._db._lock:
            rows = self._db.connection.execute(
                """
                SELECT * FROM messages
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        messages = [self._row_to_message(row) for row in reversed(rows)]
        return messages

    def clear(self) -> None:
        with self._db._lock:
            self._db.connection.execute("DELETE FROM messages")
            self._db.connection.commit()

    def prune(self, retention_days: int, now: datetime | None = None) -> int:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        with self._db._lock:
            cursor = self._db.connection.execute(
                "DELETE FROM messages WHERE created_at < ?",
                (cutoff.isoformat(),),
            )
            self._db.connection.commit()
            return cursor.rowcount

    @staticmethod
    def _row_to_message(row) -> ChatMessage:
        tool_calls = json.loads(row["tool_calls_json"]) if row["tool_calls_json"] else None
        created = datetime.fromisoformat(row["created_at"])
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return ChatMessage(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            created_at=created,
            tool_name=row["tool_name"],
            tool_call_id=row["tool_call_id"],
            tool_calls=tool_calls,
        )
