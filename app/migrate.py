"""One-time moves from the project's earlier names (Jarvis, Jarvis 2.0) to ORION.

Every step is idempotent: it checks its own marker or the files on disk, so
running this on each start costs a few stat calls and nothing else.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.brand import LEGACY_NAMES, NAME, SLUG

logger = logging.getLogger(f"{SLUG}.migrate")

_SIDE_FILES = ("-wal", "-shm")


def database_path(folder: Path) -> Path:
    return folder / f"{SLUG}.db"


def migrate_legacy(folder: Path) -> list[str]:
    """Run every legacy step against the data folder. Returns what was done, for the log."""
    done: list[str] = []
    done += _move_legacy_database(folder)
    done += _rewrite_names_once(database_path(folder))
    done += _park_legacy_logs(folder / "logs")
    done += _remove_legacy_autostart()
    for line in done:
        logger.info("Migration: %s", line)
    return done


def migrate_app_data_folder(base: Path) -> Path:
    """Rename %LOCALAPPDATA%/JARVIS2 to %LOCALAPPDATA%/ORION once, for packaged builds."""
    target = base / NAME
    if not target.exists():
        for legacy in LEGACY_NAMES:
            old = base / legacy
            if old.is_dir():
                old.rename(target)
                logger.info("Migration: moved %s to %s", old, target)
                break
    return target


def _move_legacy_database(folder: Path) -> list[str]:
    target = database_path(folder)
    done: list[str] = []
    for legacy_name in LEGACY_NAMES:
        legacy = folder / f"{legacy_name.lower()}.db"
        if legacy.exists() and not target.exists():
            # Fold the write-ahead log into the main file first, so nothing is left behind.
            connection = sqlite3.connect(str(legacy))
            try:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                connection.close()
            legacy.replace(target)
            for suffix in _SIDE_FILES:
                side = legacy.with_name(legacy.name + suffix)
                if side.exists():
                    side.unlink()
            done.append(f"moved {legacy.name} to {target.name}")
        # WAL/SHM files whose main database is gone cannot be merged. Keep them, out of the way.
        if not legacy.exists():
            orphans = [legacy.with_name(legacy.name + suffix) for suffix in _SIDE_FILES]
            orphans = [path for path in orphans if path.exists()]
            if orphans:
                parked = folder / "legacy"
                parked.mkdir(exist_ok=True)
                for path in orphans:
                    shutil.move(str(path), str(parked / path.name))
                done.append(f"parked orphaned {', '.join(path.name for path in orphans)} in legacy/")
    return done


def _rewrite_names_once(path: Path) -> list[str]:
    if not path.exists():
        return []
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS legacy_migrations (name TEXT PRIMARY KEY, done_at TEXT NOT NULL)"
        )
        if connection.execute("SELECT 1 FROM legacy_migrations WHERE name = 'rename_history'").fetchone():
            return []
        has_messages = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'messages'"
        ).fetchone()
        changed = 0
        if has_messages:
            for old in ("JARVIS", "Jarvis"):
                changed += connection.execute(
                    "UPDATE messages SET content = REPLACE(content, ?, 'Orion') WHERE content LIKE ?",
                    (old, f"%{old}%"),
                ).rowcount
        connection.execute(
            "INSERT INTO legacy_migrations (name, done_at) VALUES ('rename_history', ?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        connection.commit()
    finally:
        connection.close()
    return [f"renamed the assistant in {changed} stored messages"]


def _park_legacy_logs(logs: Path) -> list[str]:
    done: list[str] = []
    if not logs.is_dir():
        return done
    for legacy_name in LEGACY_NAMES:
        for path in logs.glob(f"{legacy_name.lower()}.log*"):
            parked = logs / "legacy"
            parked.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(parked / path.name))
            done.append(f"moved {path.name} to logs/legacy/")
    return done


def _remove_legacy_autostart() -> list[str]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    from service.autostart import RUN_KEY

    done: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            for legacy_name in LEGACY_NAMES:
                try:
                    winreg.DeleteValue(key, legacy_name)
                    done.append(f"removed the old {legacy_name} autostart entry")
                except FileNotFoundError:
                    continue
    except OSError:
        return done
    return done
