"""Filesystem locations for logs, settings, and local data."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repository_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_data_dir() -> Path:
    override = os.environ.get("ORION_DATA_DIR")
    if override:
        path = Path(override)
    elif is_frozen():
        from app.migrate import migrate_app_data_folder

        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = migrate_app_data_folder(base)
    else:
        path = repository_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_file() -> Path:
    """The repo .env when running from source, or the one beside the exe, or the folder it was started from."""
    override = os.environ.get("ORION_ENV_FILE")
    if override:
        return Path(override)
    candidates = [repository_root() / ".env", Path.cwd() / ".env"]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def settings_path() -> Path:
    if is_frozen():
        beside = Path.cwd() / "data" / "settings.json"
        if beside.is_file():
            return beside
    return app_data_dir() / "settings.json"
