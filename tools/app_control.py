"""Open installed apps and drive a few of them. No model-written commands."""

from __future__ import annotations

import json
import logging
import subprocess
import time
import urllib.parse
from typing import Literal

from pydantic import BaseModel, Field

from core.permissions import RiskLevel
from tools.base_tool import BaseTool, ToolResult
from tools.computer_tool import _clipboard_write, _focus, _window_titles

logger = logging.getLogger("orion.tools.apps")

SAFE_APPS = {
    "discord",
    "spotify",
    "steam",
    "brave",
    "chrome",
    "google chrome",
    "visual studio code",
    "code",
    "notepad",
    "calculator",
    "calc",
    "paint",
    "explorer",
    "file explorer",
    "whatsapp",
}
SEARCH_KEYS = {
    "discord": "^k",
    "spotify": "^l",
    "chrome": "^l",
    "google chrome": "^l",
    "brave": "^l",
}
MEDIA_KEYS = {"pause": 0xB3, "next": 0xB0, "previous": 0xB1}


class AppArgs(BaseModel):
    action: Literal["open", "play", "media", "discord_message", "discord_open", "search", "whatsapp"]
    name: str = ""
    target: str = ""
    text: str = ""
    query: str = ""


class AppControlTool(BaseTool):
    name = "apps"

    def needs_confirmation_for(self, arguments: dict) -> bool:
        return needs_confirmation(arguments)

    description = (
        "Open an installed app, play or control Spotify, search inside an app, "
        "or send a Discord message after the user has confirmed."
    )
    risk = RiskLevel.MEDIUM

    @property
    def input_schema(self) -> type[BaseModel]:
        return AppArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, AppArgs):
            arguments = AppArgs.model_validate(arguments)
        action = arguments.action
        if action == "open":
            return open_app(arguments.name)
        if action == "play":
            return play_spotify(arguments.query or arguments.name)
        if action == "media":
            return media_key(arguments.name or "pause")
        if action == "discord_open":
            return discord_jump(arguments.target or arguments.name, send=False, message="")
        if action == "discord_message":
            return discord_jump(arguments.target, send=True, message=arguments.text)
        if action == "search":
            return search_in_app(arguments.name, arguments.query)
        if action == "whatsapp":
            return whatsapp_message(arguments.text)
        return ToolResult(ok=False, message="Unknown app action.")


def needs_confirmation(arguments: dict) -> bool:
    action = str(arguments.get("action") or "")
    if action in {"discord_message", "whatsapp"}:
        return True
    if action == "open":
        return _clean(str(arguments.get("name") or "")) not in SAFE_APPS
    return False


_APPS_CACHE: tuple[float, list[dict[str, str]]] | None = None
_APPS_TTL = 600.0


def discover_apps() -> list[dict[str, str]]:
    """Start Menu apps. PowerShell takes seconds, so the list is reused for ten minutes."""
    import time

    global _APPS_CACHE
    if _APPS_CACHE is not None and time.monotonic() - _APPS_CACHE[0] < _APPS_TTL:
        return list(_APPS_CACHE[1])
    found = _discover_apps_now()
    if found:
        _APPS_CACHE = (time.monotonic(), found)
    return found


def _discover_apps_now() -> list[dict[str, str]]:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress",
        ],
        capture_output=True,
        text=True,
        timeout=25,
        shell=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    payload = json.loads(completed.stdout)
    if isinstance(payload, dict):
        payload = [payload]
    return [
        {"name": str(item.get("Name") or ""), "app_id": str(item.get("AppID") or "")}
        for item in payload
        if item.get("Name") and item.get("AppID")
    ]


def open_app(name: str) -> ToolResult:
    wanted = _clean(name)
    if not wanted:
        return ToolResult(ok=False, message="Tell me which app to open.")
    match = _find_app(wanted)
    if match is None:
        return ToolResult(ok=False, message=f"I can't find {name} in the Start Menu.")
    app_id = match["app_id"]
    if app_id.lower().endswith(".exe") or ":\\" in app_id:
        subprocess.Popen([app_id], shell=False)
    else:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"], shell=False)
    logger.info("Opened %s", match["name"])
    return ToolResult(ok=True, message=f"Opened {match['name']}.", data={"app": match["name"]})


def play_spotify(query: str) -> ToolResult:
    cleaned = query.strip()
    if not cleaned:
        return ToolResult(ok=False, message="Tell me what to play.")
    open_app("spotify")
    encoded = urllib.parse.quote(cleaned)
    subprocess.Popen(["explorer.exe", f"spotify:search:{encoded}"], shell=False)
    time.sleep(1.4)
    focused = _focus("spotify")
    if not focused.ok:
        return ToolResult(ok=False, message="Spotify did not open, so nothing was played.")
    _keys("^l")
    time.sleep(0.2)
    _paste(cleaned)
    _keys("{ENTER}")
    time.sleep(0.9)
    _keys("{DOWN}{ENTER}")
    return ToolResult(ok=True, message=f"Playing {cleaned} on Spotify.")


def media_key(name: str) -> ToolResult:
    import ctypes

    key = MEDIA_KEYS.get(name.lower())
    if key is None:
        return ToolResult(ok=False, message="I can pause, go next, or go back.")
    ctypes.windll.user32.keybd_event(key, 0, 0, 0)
    ctypes.windll.user32.keybd_event(key, 0, 2, 0)
    spoken = {"pause": "Paused.", "next": "Next track.", "previous": "Previous track."}[name.lower()]
    return ToolResult(ok=True, message=spoken)


def discord_jump(target: str, send: bool, message: str) -> ToolResult:
    if not target.strip():
        return ToolResult(ok=False, message="Tell me who to open on Discord.")
    if not any("discord" in title.lower() for title in _window_titles()):
        opened = open_app("discord")
        if not opened.ok:
            return opened
        time.sleep(2.0)
    focused = _focus("discord")
    if not focused.ok:
        return ToolResult(ok=False, message="Discord is not open, so I did not type anything.")
    time.sleep(0.3)
    _keys("^k")
    time.sleep(0.25)
    _paste(target.strip())
    _keys("{ENTER}")
    time.sleep(0.5)
    if not send:
        return ToolResult(ok=True, message=f"Opened {target} on Discord.")
    if not message.strip():
        return ToolResult(ok=False, message="There is no message to send.")
    _paste(message.strip())
    _keys("{ENTER}")
    return ToolResult(ok=True, message=f"Sent that to {target} on Discord.")


def search_in_app(app: str, query: str) -> ToolResult:
    if not app.strip() or not query.strip():
        return ToolResult(ok=False, message="Tell me the app and what to search for.")
    opened = open_app(app)
    if not opened.ok:
        return opened
    time.sleep(0.8)
    focused = _focus(app)
    if not focused.ok:
        return ToolResult(ok=False, message=f"{app} did not come to the front, so I did not search.")
    shortcut = SEARCH_KEYS.get(_clean(app), "^f")
    _keys(shortcut)
    time.sleep(0.2)
    _paste(query.strip())
    _keys("{ENTER}")
    return ToolResult(ok=True, message=f"Searched {app} for {query}.")


def whatsapp_message(text: str) -> ToolResult:
    if not text.strip():
        return ToolResult(ok=False, message="There is no message to send.")
    encoded = urllib.parse.quote(text.strip())
    subprocess.Popen(["explorer.exe", f"whatsapp://send?text={encoded}"], shell=False)
    return ToolResult(ok=True, message="Opened WhatsApp with that message. You still need to choose who and press send.")


def _find_app(wanted: str) -> dict[str, str] | None:
    apps = discover_apps()
    for app in apps:
        if _clean(app["name"]) == wanted:
            return app
    words = [word for word in wanted.split() if word not in {"the", "app", "games", "game"}]
    if not words:
        words = wanted.split()
    for app in apps:
        cleaned = _clean(app["name"])
        if all(word in cleaned for word in words):
            return app
    return None


def _clean(value: str) -> str:
    return " ".join(value.lower().split())


def _keys(sequence: str) -> None:
    from pywinauto.keyboard import send_keys

    send_keys(sequence, pause=0.02, with_spaces=True)


def _paste(text: str) -> None:
    _clipboard_write(text)
    time.sleep(0.05)
    _keys("^v")
