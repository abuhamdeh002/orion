"""System tray icon. Skipped when pystray is not installed."""

from __future__ import annotations

import threading

from app.brand import NAME
from service.runtime import OrionRuntime


def start(runtime: OrionRuntime) -> threading.Thread | None:
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    def _open(_icon, _item) -> None:
        from web.desktop import open_shell

        open_shell(f"http://{runtime.config.orion_host}:{runtime.config.orion_port}/")

    def _quit(icon, _item) -> None:
        icon.stop()

    image = Image.new("RGB", (64, 64), "black")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), outline=(46, 214, 196), width=3)
    icon = pystray.Icon(NAME, image, NAME, pystray.Menu(
        pystray.MenuItem("Open", _open),
        pystray.MenuItem("Quit tray", _quit),
    ))
    thread = threading.Thread(target=icon.run, name="OrionTray", daemon=True)
    thread.start()
    return thread
