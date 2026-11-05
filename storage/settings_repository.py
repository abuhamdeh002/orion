"""User preference persistence without storing secrets."""

from __future__ import annotations

from pathlib import Path

from app.config import UserPreferences, load_preferences, save_preferences
from app.paths import settings_path


class SettingsRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_path()

    def load(self) -> UserPreferences:
        return load_preferences(self.path)

    def save(self, preferences: UserPreferences) -> None:
        save_preferences(preferences, self.path)
