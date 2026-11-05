"""SQLite connection and schema migrations."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        tool_name TEXT,
        tool_call_id TEXT,
        tool_calls_json TEXT
    );
    CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        due_at TEXT NOT NULL,
        recurrence TEXT NOT NULL DEFAULT 'none',
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        fired_at TEXT
    );
    """,
]


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row["version"]
                for row in self.connection.execute("SELECT version FROM schema_migrations")
            }
            for index, script in enumerate(MIGRATIONS, start=1):
                if index in applied:
                    continue
                self.connection.executescript(script)
                self.connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (index, datetime.now(timezone.utc).isoformat()),
                )
            self.connection.commit()

    def close(self) -> None:
        with self._lock:
            self.connection.close()
