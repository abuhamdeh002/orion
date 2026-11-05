"""The local model heals itself instead of hanging for two minutes."""

from __future__ import annotations

import threading
import time

import pytest

from ai.doctor import FROZE, WAKING, LocalDoctor, looks_stuck
from app.errors import ProviderError, ProviderTimeoutError


def test_what_counts_as_stuck():
    assert looks_stuck(ProviderTimeoutError("Ollama timed out."))
    assert looks_stuck(ProviderError("Ollama error (500): llm server error"))
    assert not looks_stuck(ProviderError("Could not reach Ollama. Start Ollama locally."))


def test_requests_wait_while_the_model_wakes():
    doctor = LocalDoctor("http://127.0.0.1:9", "m")
    doctor.begin()
    threading.Timer(0.2, doctor.done).start()
    started = time.monotonic()
    assert doctor.wait_ready(timeout=3)
    assert 0.15 < time.monotonic() - started < 2


def test_waiting_gives_up_politely():
    doctor = LocalDoctor("http://127.0.0.1:9", "m")
    doctor.begin()
    assert not doctor.wait_ready(timeout=0.1)


def _router(monkeypatch, fail):
    from ai.router import ModelRouter
    from app.config import AppConfig, EnvConfig, UserPreferences, merge_config

    config = merge_config(EnvConfig(ai_provider="ollama", ai_model="m", ollama_base_url="http://127.0.0.1:9"), UserPreferences())
    assert isinstance(config, AppConfig)
    router = ModelRouter(config)
    router._cloud = []
    monkeypatch.setattr(router, "local_health", lambda fresh=False: (True, "Ollama (m)"))
    monkeypatch.setattr(router.local, "chat", lambda messages, tools=None: (_ for _ in ()).throw(fail))
    healed = []
    monkeypatch.setattr(router.doctor, "heal", lambda wait=False: healed.append(True))
    return router, healed


def test_a_hang_heals_and_says_so(monkeypatch):
    router, healed = _router(monkeypatch, ProviderTimeoutError("Ollama timed out."))
    with pytest.raises(ProviderError) as caught:
        router.chat([{"role": "user", "content": "hi"}])
    assert str(caught.value) == FROZE and healed == [True]


def test_while_healing_a_request_waits_then_explains(monkeypatch):
    router, _ = _router(monkeypatch, ProviderTimeoutError("Ollama timed out."))
    router.doctor.begin()
    monkeypatch.setattr("ai.doctor.WAIT_FOR_BRAIN", 0.1)
    monkeypatch.setattr(router.doctor, "wait_ready", lambda timeout=0.1: False)
    with pytest.raises(ProviderError) as caught:
        router.chat([{"role": "user", "content": "hi"}])
    assert str(caught.value) == WAKING
