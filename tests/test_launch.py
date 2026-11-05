"""Launching ORION like an app: one instance, a window when you open it, quiet at sign-in."""

from __future__ import annotations

import sys


def test_autostart_starts_quietly(monkeypatch):
    from service.autostart import command_line

    assert command_line().endswith("-m service --background")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Programs\ORION\ORION.exe")
    assert command_line() == r'"C:\Programs\ORION\ORION.exe" --background'


def test_a_second_launch_only_opens_the_window(monkeypatch):
    import service.__main__ as entry

    opened = []
    monkeypatch.setattr(entry, "_already_running", lambda host, port: True)
    monkeypatch.setattr("web.desktop.open_shell", lambda url: opened.append(url))
    monkeypatch.setattr(sys, "argv", ["ORION.exe", "--open"])
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not start a second server")))
    entry.main()
    assert opened == ["http://127.0.0.1:8765/"]


def test_the_frozen_window_is_the_exe_itself(monkeypatch):
    import web.desktop as desktop

    started = []
    monkeypatch.setattr(desktop, "_has_webview", lambda: True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Programs\ORION\ORION.exe")
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda command, **kwargs: started.append(command))
    desktop.open_shell("http://127.0.0.1:8765/")
    assert started == [[r"C:\Programs\ORION\ORION.exe", "--window", "http://127.0.0.1:8765/"]]
