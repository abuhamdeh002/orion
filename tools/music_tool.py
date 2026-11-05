"""Open a configured music app or send Windows media keys."""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel

from app.config import AppConfig
from core.permissions import RiskLevel
from tools.application_tool import AppLaunchArgs, ApplicationTool
from tools.base_tool import BaseTool, ToolResult

_MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
}


class MusicArgs(BaseModel):
    action: Literal["open", "play_pause", "next", "previous"]


class MusicTool(BaseTool):
    name = "music"
    description = "Open the configured music application or control system media playback."
    risk = RiskLevel.LOW

    def __init__(self, config: AppConfig, launcher: ApplicationTool | None = None) -> None:
        self.config = config
        self.launcher = launcher

    @property
    def input_schema(self) -> type[BaseModel]:
        return MusicArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, MusicArgs):
            arguments = MusicArgs.model_validate(arguments)
        if arguments.action == "open":
            return self._open()
        return self._media_key(arguments.action)

    def _open(self) -> ToolResult:
        alias = (self.config.music_app_alias or "").strip()
        if not alias or self.launcher is None:
            return ToolResult(
                ok=False,
                message="No music app is configured. Set a music app alias in Settings to an allowlisted application.",
            )
        return self.launcher.execute(AppLaunchArgs(app_name=alias))

    def _media_key(self, action: str) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult(ok=False, message="Media keys are only supported on Windows.")
        try:
            import ctypes

            key = _MEDIA_KEYS[action]
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)
        except Exception as exc:
            return ToolResult(ok=False, message=f"Media control is unsupported here: {exc}")
        return ToolResult(ok=True, message=f"Sent the {action.replace('_', ' ')} media command.")
