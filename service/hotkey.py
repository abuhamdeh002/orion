"""Global Win+Alt+Space hotkey. The callback should open the command bar."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from collections.abc import Callable

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_WIN = 0x0008
VK_SPACE = 0x20
VK_ESCAPE = 0x1B
WM_HOTKEY = 0x0312


def listen(callback: Callable[[], None], on_kill: Callable[[], None] | None = None) -> threading.Thread | None:
    if not hasattr(ctypes, "windll"):
        return None

    def _run() -> None:
        user32 = ctypes.windll.user32
        user32.RegisterHotKey(None, 1, MOD_ALT | MOD_WIN, VK_SPACE)
        if on_kill is not None:
            user32.RegisterHotKey(None, 2, MOD_CONTROL | MOD_ALT, VK_ESCAPE)
        message = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) != 0:
            if message.message == WM_HOTKEY and message.wParam == 2 and on_kill is not None:
                on_kill()
            elif message.message == WM_HOTKEY:
                callback()
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    thread = threading.Thread(target=_run, name="OrionHotkey", daemon=True)
    thread.start()
    return thread
