"""Start the local Ollama server when it is installed but not running."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx

logger = logging.getLogger("orion.ollama")


def ollama_executable() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    candidates = [Path(local) / "Programs" / "Ollama" / "ollama.exe"] if local else []
    candidates.append(Path(r"C:\Program Files\Ollama\ollama.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def is_up(base_url: str, timeout: float = 2.0) -> bool:
    try:
        return httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout).status_code < 400
    except httpx.HTTPError:
        return False


def _log_file():
    """Ollama's own output goes to data/logs/ollama.log, so a hang or crash can be diagnosed."""
    try:
        from app.paths import logs_dir

        return open(logs_dir() / "ollama.log", "ab")  # noqa: SIM115 - the child process keeps it open
    except OSError:
        return None


def ensure_ollama(base_url: str, wait_seconds: float = 90.0) -> bool:
    """True when Ollama answers, starting `ollama serve` in the background if needed."""
    if is_up(base_url):
        return True
    host = base_url.split("//", 1)[-1]
    if not host.startswith(("127.0.0.1", "localhost")):
        return False  # a remote Ollama is somebody else's to start
    executable = ollama_executable()
    if executable is None:
        logger.info("Ollama is not installed")
        return False
    # Ollama should outlive ORION: a restart must not unload a model that takes half a minute to load.
    environment = dict(os.environ)
    # More of a small graphics card for the model itself. Only defaults: the user's own settings win.
    environment.setdefault("OLLAMA_FLASH_ATTENTION", "1")
    environment.setdefault("OLLAMA_KV_CACHE_TYPE", "q8_0")
    log = _log_file()
    attempts = [0]
    if os.name == "nt":
        base = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        attempts = [base | subprocess.CREATE_BREAKAWAY_FROM_JOB, base]  # type: ignore[attr-defined]
    for flags in attempts:
        try:
            subprocess.Popen(
                [executable, "serve"],
                stdin=subprocess.DEVNULL,
                stdout=log or subprocess.DEVNULL,
                stderr=subprocess.STDOUT if log else subprocess.DEVNULL,
                env=environment,
                creationflags=flags,
                close_fds=True,
            )
            break
        except OSError as exc:
            # A job that forbids breakaway refuses the first attempt; the second one still works.
            if flags == attempts[-1]:
                logger.warning("Could not start Ollama: %s", exc)
                return False
    logger.info("Started Ollama in the background")
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if is_up(base_url):
            return True
        time.sleep(0.5)
    return False
