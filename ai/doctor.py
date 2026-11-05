"""Keeps the local model alive: waits while it wakes, and heals it when it freezes.

What happened on 2026-11-05: the graphics driver lost the model's memory (a game took the
GPU), Ollama still reported it as loaded, and every request hung for two minutes before
failing with "No AI model is available". Unloading and reloading it fixed it in 45 s.
This does that automatically, and says so instead of hanging.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable

import httpx

logger = logging.getLogger("orion.ai.doctor")

WAIT_FOR_BRAIN = 75.0  # how long a request waits while the model wakes or heals
WAKING = "I'm still waking up. Give me a few more seconds and ask again."
FROZE = (
    "My brain froze, so I'm restarting it. That takes about a minute. "
    "Quick things like reminders, timers and the time still work."
)


def looks_stuck(exc: Exception) -> bool:
    """A hang, a server error, or Ollama gone: all are fixed by reloading the model."""
    text = str(exc).lower()
    # "Could not reach Ollama" is different: nothing is running, and the "no model" message says how to fix it.
    return any(sign in text for sign in ("timed out", "error (500", "error (502", "error (503", "unexpected response"))


class LocalDoctor:
    def __init__(self, base_url: str, model: str, mark: Callable[[bool, str], None] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.mark = mark
        self._ready = threading.Event()
        self._ready.set()
        self._lock = threading.Lock()
        self.healing = False
        self.heals = 0

    # -- waking (startup) and healing share one "not ready yet" state --------------------------

    @property
    def waking(self) -> bool:
        return not self._ready.is_set()

    def begin(self) -> None:
        self._ready.clear()

    def done(self) -> None:
        self._ready.set()

    def wait_ready(self, timeout: float = WAIT_FOR_BRAIN) -> bool:
        """Block a request until the model is ready, up to `timeout`. True when it is."""
        if self._ready.is_set():
            return True
        logger.info("Waiting for the model to be ready")
        return self._ready.wait(timeout)

    # -- healing -------------------------------------------------------------------------------

    def heal(self, wait: bool = False) -> None:
        """Unload the stuck model, start Ollama if it died, load the model again. Once at a time."""
        if os.environ.get("ORION_NO_HEAL"):
            return  # the test suite: never touch the real Ollama on this PC
        with self._lock:
            if self.healing:
                return
            self.healing = True
            self.heals += 1
        self._ready.clear()
        worker = threading.Thread(target=self._heal, name="OrionHeal", daemon=True)
        worker.start()
        if wait:
            worker.join()

    def _heal(self) -> None:
        from ai.ollama_provider import NUM_CTX

        logger.warning("The local model looks stuck; reloading it")
        try:
            try:
                httpx.post(f"{self.base_url}/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=30)
            except httpx.HTTPError:
                pass  # a hung or dead runner may not answer; loading below starts a fresh one
            try:
                from service.ollama_boot import ensure_ollama

                ensure_ollama(self.base_url)
            except Exception:
                logger.debug("Could not check the Ollama server", exc_info=True)
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": "ok", "stream": False, "keep_alive": "2h", "options": {"num_predict": 1, "num_ctx": NUM_CTX}},
                timeout=240,
            )
            ok = response.status_code < 400
            logger.info("Model reload %s (%s)", "worked" if ok else f"failed with {response.status_code}", self.model)
            if self.mark is not None:
                self.mark(ok, f"Ollama ({self.model})" if ok else "Ollama could not load the model")
        except Exception as exc:
            logger.warning("Model reload failed: %s", exc)
            if self.mark is not None:
                self.mark(False, "Ollama could not load the model")
        finally:
            with self._lock:
                self.healing = False
            self._ready.set()
