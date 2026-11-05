"""Phone and relay commands. Each action calls a real tool or a Windows API."""

from __future__ import annotations

import ctypes
from typing import Any

from service.runtime import OrionRuntime

_VOLUME = {"up": 0xAF, "down": 0xAE, "mute": 0xAD}
_POWER = {"lock", "sleep", "shutdown"}


def perform(runtime: OrionRuntime, action: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    name = action.strip().lower()
    if name == "open":
        from tools.app_control import open_app

        result = open_app(str(arguments.get("name") or ""))
        return {"ok": result.ok, "message": result.message}
    if name == "media":
        from tools.app_control import media_key

        result = media_key(str(arguments.get("name") or "pause"))
        return {"ok": result.ok, "message": result.message}
    if name == "volume":
        key = _VOLUME.get(str(arguments.get("name") or "").lower())
        if key is None:
            return {"ok": False, "message": "Volume is up, down, or mute."}
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)
        return {"ok": True, "message": f"Volume {arguments.get('name')}."}
    if name == "lock":
        ctypes.windll.user32.LockWorkStation()
        return {"ok": True, "message": "Locked."}
    if name == "sleep":
        ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        return {"ok": True, "message": "Going to sleep."}
    if name == "shutdown":
        pin = str(arguments.get("pin") or "")
        if pin and hasattr(runtime, "set_pin"):
            # A PIN typed on a paired phone approves this one shutdown.
            runtime.set_pin(pin)
            runtime.pending_pin = True
        if not runtime._pin_ok():
            return {"ok": False, "message": "Shutdown needs the PIN from the phone.", "confirm": True}
        ctypes.windll.user32.ExitWindowsEx(0x00000001, 0x80000000)
        return {"ok": True, "message": "Shutting down."}
    if name == "screenshot":
        return _screenshot()
    if name == "screen_text":
        shot = _screenshot()
        if not shot["ok"]:
            return shot
        return {"ok": True, "message": _ocr(shot["png_base64"]), "png_base64": shot["png_base64"]}
    if name == "clipboard_read":
        from tools.computer_tool import _clipboard_read

        return {"ok": True, "message": _clipboard_read()}
    if name == "clipboard_write":
        from tools.computer_tool import _clipboard_write

        _clipboard_write(str(arguments.get("text") or ""))
        return {"ok": True, "message": "Clipboard updated."}
    if name == "apps":
        from tools.app_control import discover_apps

        found = discover_apps()
        return {"ok": True, "message": f"{len(found)} apps.", "apps": found[:80]}
    return {"ok": False, "message": "Unknown command."}


def _screenshot() -> dict[str, Any]:
    import base64
    import io

    from PIL import ImageGrab

    image = ImageGrab.grab()
    image.thumbnail((1280, 720))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return {"ok": True, "message": "Screenshot taken.", "png_base64": base64.b64encode(buffer.getvalue()).decode("ascii")}


def _ocr(png_base64: str) -> str:
    import base64
    import io

    from PIL import Image

    image = Image.open(io.BytesIO(base64.b64decode(png_base64)))
    try:
        import pytesseract

        return pytesseract.image_to_string(image).strip() or "No text on screen."
    except Exception:
        return "Screenshot taken. OCR is not installed, so I cannot read the text."
