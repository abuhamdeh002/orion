"""Optional Windows login autostart. Never enabled unless asked."""

from __future__ import annotations

import sys
from pathlib import Path

from app.brand import NAME


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = NAME


def command_line() -> str:
    """Started at sign-in quietly: the window opens only when someone launches ORION themselves."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --background'
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.exists() else python
    return f'"{executable}" -m service --background'


def install() -> str:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command_line())
    return command_line()


def remove() -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            return
