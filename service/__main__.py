"""Run the ORION service.

    ORION.exe                 start, and open the window (a second launch just opens the window)
    ORION.exe --background    start quietly (what sign-in autostart uses)
    ORION.exe --window URL    the native app window on its own (started by the service)
    --install-autostart / --remove-autostart
"""

from __future__ import annotations

import os
import sys
import threading

# A windowed build has no console: anything printed would crash it.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

import uvicorn  # noqa: E402

from app.brand import NAME  # noqa: E402
from app.config import load_config  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.paths import is_frozen  # noqa: E402


def _already_running(host: str, port: int) -> bool:
    """True when ORION already answers on this port, so a second launch only opens the window."""
    import httpx

    try:
        response = httpx.get(f"http://{host}:{port}/health", timeout=1.5)
        return response.status_code == 200 and response.json().get("name") == NAME
    except (httpx.HTTPError, ValueError):
        return False


def main() -> None:
    args = sys.argv[1:]
    if "--window" in args:
        from web.desktop import run_window

        index = args.index("--window")
        run_window(args[index + 1] if index + 1 < len(args) else "http://127.0.0.1:8765/")
        return
    if "--install-autostart" in args:
        from service.autostart import install

        print(install())
        return
    if "--remove-autostart" in args:
        from service.autostart import remove

        remove()
        print("removed")
        return

    config = load_config()
    url = f"http://{config.orion_host}:{config.orion_port}/"
    show = ("--background" not in args) and (is_frozen() or "--open" in args)
    if _already_running(config.orion_host, config.orion_port):
        if show or "--open" in args or is_frozen():
            from web.desktop import open_shell

            open_shell(url)
        print(f"{NAME} is already running at {url}")
        return

    from service.api import app, mount_ui
    from service.runtime import get_runtime

    mount_ui(app)
    setup_logging(config)
    get_runtime().start_ambient()
    if show:
        from web.desktop import open_shell

        # Give the server a moment to start listening first.
        threading.Timer(1.5, open_shell, args=(url,)).start()
    print(f"{NAME} listening on {url}")
    uvicorn.run(app, host=config.orion_host, port=config.orion_port, log_level="info", log_config=None if is_frozen() else uvicorn.config.LOGGING_CONFIG)


if __name__ == "__main__":
    main()
