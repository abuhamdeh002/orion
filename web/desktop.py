"""Desktop window for the web UI. A native WebView2 window when pywebview is installed, else the browser.

The window runs in its own process, so closing it never stops the always-on service.
Run directly with:  python -m web.desktop [url]
"""

from __future__ import annotations

import subprocess
import sys
import webbrowser

from app.brand import NAME


def _has_webview() -> bool:
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    return True


def open_shell(url: str = "http://127.0.0.1:8765/") -> None:
    """Show the UI without blocking the caller."""
    if not _has_webview():
        webbrowser.open(url)
        return
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # type: ignore[attr-defined]
    # The installed ORION.exe opens its own native window; from source it's `python -m web.desktop`.
    command = [sys.executable, "--window", url] if getattr(sys, "frozen", False) else [sys.executable, "-m", "web.desktop", url]
    try:
        subprocess.Popen(command, creationflags=flags, close_fds=True)
    except OSError:
        webbrowser.open(url)


def run_window(url: str) -> None:
    import webview

    webview.create_window(NAME, url, width=1240, height=820, min_size=(380, 560))
    webview.start()


if __name__ == "__main__":
    run_window(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/")
