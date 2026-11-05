"""Curated Windows actions. No model-written shell."""

from __future__ import annotations

import ctypes
import re
import subprocess
from typing import Literal

from pydantic import BaseModel, Field

from core.permissions import RiskLevel
from tools.base_tool import BaseTool, ToolResult


class ComputerArgs(BaseModel):
    action: Literal[
        "list_windows",
        "focus_window",
        "clipboard_read",
        "clipboard_write",
        "volume",
        "lock",
        "discover_apps",
        "screen_text",
        "click_control",
    ]
    title: str = ""
    text: str = ""
    control: str = ""
    level: int = Field(default=50, ge=0, le=100)


# Actions that change something you can't easily undo or that act on another app.
_CONFIRM_ACTIONS = {"lock", "click_control", "clipboard_write"}


class ComputerTool(BaseTool):
    name = "computer"
    description = (
        "Read open windows, focus one, read or write the clipboard, set volume, lock the PC, "
        "or list Start Menu apps. Locking needs confirmation."
    )
    risk = RiskLevel.MEDIUM

    @property
    def input_schema(self) -> type[BaseModel]:
        return ComputerArgs

    @property
    def requires_confirmation(self) -> bool:
        return False

    def needs_confirmation_for(self, arguments: dict) -> bool:
        return str(arguments.get("action") or "") in _CONFIRM_ACTIONS

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, ComputerArgs):
            arguments = ComputerArgs.model_validate(arguments)
        action = arguments.action
        if action == "list_windows":
            return ToolResult(ok=True, message="\n".join(_window_titles()) or "No visible windows.")
        if action == "focus_window":
            return _focus(arguments.title)
        if action == "clipboard_read":
            return ToolResult(ok=True, message=_clipboard_read() or "Clipboard is empty.")
        if action == "clipboard_write":
            _clipboard_write(arguments.text)
            return ToolResult(ok=True, message="Clipboard updated.")
        if action == "volume":
            _set_volume(arguments.level)
            return ToolResult(ok=True, message=f"Volume set to {arguments.level}.")
        if action == "discover_apps":
            names = _start_menu_names()
            return ToolResult(ok=True, message=", ".join(names[:40]) or "No shortcuts found.", data={"apps": names})
        if action == "lock":
            ctypes.windll.user32.LockWorkStation()
            return ToolResult(ok=True, message="Workstation locked.")
        if action == "screen_text":
            return _screen_text()
        if action == "click_control":
            return _click_control(arguments.title, arguments.control)
        return ToolResult(ok=False, message="Unknown computer action.")


class PowerArgs(BaseModel):
    action: Literal["shutdown", "restart"]


class PowerTool(BaseTool):
    name = "power"
    description = "Shut down or restart this PC. Requires confirmation and the phone PIN."
    risk = RiskLevel.HIGH
    requires_confirmation = True
    requires_pin = True

    @property
    def input_schema(self) -> type[BaseModel]:
        return PowerArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, PowerArgs):
            arguments = PowerArgs.model_validate(arguments)
        flag = "/s" if arguments.action == "shutdown" else "/r"
        subprocess.Popen(["shutdown", flag, "/t", "30"], shell=False)
        return ToolResult(ok=True, message=f"{arguments.action} scheduled in 30 seconds. Run shutdown /a to cancel.")


def _window_titles() -> list[str]:
    titles: list[str] = []

    def _callback(hwnd, _lparam) -> bool:
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
                titles.append(buffer.value)
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_callback)
    ctypes.windll.user32.EnumWindows(enum_proc, 0)
    return titles


def _focus(title: str) -> ToolResult:
    needle = title.lower()
    found = None

    def _callback(hwnd, _lparam) -> bool:
        nonlocal found
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        if needle and needle in buffer.value.lower():
            found = hwnd
            return False
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_callback)
    ctypes.windll.user32.EnumWindows(enum_proc, 0)
    if not found:
        return ToolResult(ok=False, message="No window matched that title.")
    ctypes.windll.user32.ShowWindow(found, 9)
    ctypes.windll.user32.SetForegroundWindow(found)
    return ToolResult(ok=True, message="Window focused.")


def _clipboard_read() -> str:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(13)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _clipboard_write(text: str) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = kernel32.GlobalAlloc(0x0002, size)
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, size)
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        return
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(13, handle)
    finally:
        user32.CloseClipboard()


def _set_volume(level: int) -> None:
    # Virtual-key volume steps are coarse; send the master volume via the key endpoint scalar.
    scalar = max(0.0, min(1.0, level / 100))
    command = (
        "$w = New-Object -ComObject WScript.Shell; "
        f"1..50 | ForEach-Object {{ $w.SendKeys([char]174) }}; "
        f"1..{max(0, int(scalar * 50))} | ForEach-Object {{ $w.SendKeys([char]175) }}"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", command],
        shell=False,
    )


def _start_menu_names() -> list[str]:
    from pathlib import Path

    roots = [
        Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs",
        Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs"),
    ]
    names: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for shortcut in root.rglob("*.lnk"):
            names.append(shortcut.stem)
    return sorted(set(names))


def _screen_text() -> ToolResult:
    try:
        from PIL import ImageGrab
    except ImportError:
        return ToolResult(ok=False, message="Pillow is not installed, so the screen cannot be read.")
    try:
        import pytesseract
    except ImportError:
        return ToolResult(ok=False, message="pytesseract is not installed, so the screen cannot be read.")
    image = ImageGrab.grab()
    text = pytesseract.image_to_string(image).strip()
    return ToolResult(ok=True, message=text or "No text found on the screen.", data={"chars": len(text)})


def _click_control(title: str, control: str) -> ToolResult:
    if not title or not control:
        return ToolResult(ok=False, message="click_control needs a window title and a control name.")
    try:
        from pywinauto import Desktop
    except ImportError:
        return ToolResult(
            ok=False,
            message="UI Automation clicks need pywinauto. It is not installed, so nothing was clicked.",
        )
    windows = Desktop(backend="uia").windows(title_re=f".*{re.escape(title)}.*")
    if not windows:
        return ToolResult(ok=False, message="No window matched that title.")
    matches = windows[0].descendants(title=control)
    if not matches:
        return ToolResult(ok=False, message="No control matched that name.")
    matches[0].click_input()
    return ToolResult(ok=True, message=f"Clicked {control}.")
