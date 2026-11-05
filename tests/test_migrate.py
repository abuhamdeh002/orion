"""Legacy Jarvis -> ORION migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.migrate import database_path, migrate_app_data_folder, migrate_legacy


def _legacy_db(path: Path, text: str) -> None:
    connection = sqlite3.connect(str(path))
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE messages (id TEXT, role TEXT, content TEXT, created_at TEXT)")
    connection.execute("INSERT INTO messages VALUES ('1', 'assistant', ?, 'now')", (text,))
    connection.commit()
    connection.close()


def _contents(path: Path) -> list[str]:
    connection = sqlite3.connect(str(path))
    try:
        return [row[0] for row in connection.execute("SELECT content FROM messages")]
    finally:
        connection.close()


def test_moves_jarvis_db_and_renames_history_once(tmp_path: Path):
    _legacy_db(tmp_path / "jarvis.db", "Jarvis here. JARVIS online.")
    first = migrate_legacy(tmp_path)
    target = database_path(tmp_path)
    assert target.exists() and not (tmp_path / "jarvis.db").exists()
    assert not (tmp_path / "jarvis.db-wal").exists()
    assert _contents(target) == ["Orion here. Orion online."]
    assert any("moved jarvis.db" in line for line in first)

    # A second start does nothing, even if someone writes "Jarvis" on purpose later.
    connection = sqlite3.connect(str(target))
    connection.execute("INSERT INTO messages VALUES ('2', 'user', 'Who was Jarvis?', 'later')")
    connection.commit()
    connection.close()
    assert migrate_legacy(tmp_path) == []
    assert "Who was Jarvis?" in _contents(target)


def test_parks_orphaned_wal_files(tmp_path: Path):
    (tmp_path / "jarvis.db-wal").write_bytes(b"x")
    (tmp_path / "jarvis.db-shm").write_bytes(b"y")
    migrate_legacy(tmp_path)
    assert not (tmp_path / "jarvis.db-wal").exists()
    assert (tmp_path / "legacy" / "jarvis.db-wal").read_bytes() == b"x"


def test_parks_old_logs(tmp_path: Path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "jarvis.log").write_text("old")
    (logs / "orion.log").write_text("new")
    migrate_legacy(tmp_path)
    assert (logs / "legacy" / "jarvis.log").exists()
    assert (logs / "orion.log").exists()


def test_renames_the_packaged_app_data_folder(tmp_path: Path):
    (tmp_path / "JARVIS2").mkdir()
    (tmp_path / "JARVIS2" / "settings.json").write_text("{}")
    target = migrate_app_data_folder(tmp_path)
    assert target.name == "ORION"
    assert (target / "settings.json").exists()
    assert not (tmp_path / "JARVIS2").exists()
