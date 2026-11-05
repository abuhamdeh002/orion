"""The always-on mic must answer people, not the TV. Lines below are from data/logs/orion.log."""

from __future__ import annotations

import time

import pytest

from voice.conversation import AWAKE_SECONDS, VoiceConversation, _is_name, has_name, take_command
from voice.speech_text import ACKNOWLEDGE

ROOM_NOISE = [
    "Thank you.",
    "Yeah.",
    "I will be able to see you in the next video.",
    "hello",
    "hey",
    "pump iron every day",
    "the origin of the species",
    "the orient express",
]


@pytest.mark.parametrize("line", ROOM_NOISE)
def test_room_noise_never_wakes(line: str) -> None:
    assert take_command(line, awake=False) is None


def test_name_matching_is_tight() -> None:
    assert _is_name("Orion") and _is_name("orien") and _is_name("Orian,")
    assert not _is_name("iron") and not _is_name("origin") and not _is_name("orient")
    assert has_name("hey iron what time is it")
    assert not has_name("pump iron")


class _Speaker:
    def __init__(self) -> None:
        self.said: list[str] = []

    def speak(self, text, block=False, **_kwargs):
        self.said.append(text)
        return True

    def stop(self) -> None:
        pass


class _Runtime:
    def __init__(self) -> None:
        self.speaker = _Speaker()
        self.assistant = type("A", (), {"cancel": lambda self: None})()
        self.config = type("C", (), {"microphone_device_index": None})()

    def push(self, *_args, **_kwargs) -> None:
        pass


def _voice(monkeypatch, heard: str) -> tuple[VoiceConversation, list[str]]:
    voice = VoiceConversation(_Runtime())
    voice._ear = object()
    answered: list[str] = []
    monkeypatch.setattr(voice, "_transcribe", lambda pcm: (True, heard))
    monkeypatch.setattr(voice, "_answer", answered.append)
    monkeypatch.setattr(voice, "_release_echo", lambda: None)
    return voice, answered


@pytest.mark.parametrize("line", ROOM_NOISE)
def test_idle_loop_ignores_the_room(monkeypatch, line: str) -> None:
    voice, answered = _voice(monkeypatch, line)
    voice._speech_started = time.time()
    voice._handle_pcm(b"\x00\x00")
    assert answered == []
    assert voice.runtime.speaker.said == []


def test_wake_then_follow_up(monkeypatch) -> None:
    voice, answered = _voice(monkeypatch, "hey orion")
    voice._speech_started = time.time()
    voice._handle_pcm(b"\x00\x00")
    assert len(voice.runtime.speaker.said) == 1 and voice.runtime.speaker.said[0] in ACKNOWLEDGE
    assert voice._awake_until > time.time() + AWAKE_SECONDS - 2
    voice2, answered2 = _voice(monkeypatch, "what time is it")
    voice2._awake_until = time.time() + 5
    voice2._speech_started = time.time()
    voice2._handle_pcm(b"\x00\x00")
    assert answered2 == ["what time is it"]


def test_speech_that_started_after_the_window_is_ignored(monkeypatch) -> None:
    voice, answered = _voice(monkeypatch, "I will be able to see you in the next video.")
    voice._awake_until = time.time() - 1
    voice._speech_started = time.time()
    voice._handle_pcm(b"\x00\x00")
    assert answered == []


def test_kill_switch_silences_the_mic(monkeypatch) -> None:
    from service.runtime import KILL

    voice, answered = _voice(monkeypatch, "hey orion what time is it")
    voice._speech_started = time.time()
    KILL.set()
    try:
        voice._handle_pcm(b"\x00\x00")
    finally:
        KILL.clear()
    assert answered == []


def test_spoken_yes_reaches_the_confirmation(monkeypatch) -> None:
    import threading

    voice, _answered = _voice(monkeypatch, "yes")
    request = type("Req", (), {"tool_name": "computer", "arguments": {}})()

    class Assistant:
        def cancel(self) -> None:
            pass

        def handle_user_message(self, text, **turn):
            approved = turn["confirm"](request)
            return type("Reply", (), {"text": "approved" if approved else "refused"})()

    voice.runtime.assistant = Assistant()
    threading.Timer(0.4, lambda: voice._audio.put(b"\x01\x00")).start()
    text, replacement = voice._think("lock the pc")
    assert replacement is None
    assert text == "approved"


def test_latency_report_reads_the_log(tmp_path) -> None:
    from evals.latency import read, summary

    log = tmp_path / "orion.log"
    log.write_text(
        "x | Latency stt_ms=300 think_ms=900 total_ms=1200\n"
        "x | Latency stt_ms=500 think_ms=1500 total_ms=2000\n",
        encoding="utf-8",
    )
    report = summary(read(log))
    assert report["total_ms"]["turns"] == 2
    assert report["stt_ms"]["p50"] == 400
