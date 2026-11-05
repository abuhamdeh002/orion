"""Tests for Phase 4 voice pipeline: speech input, output, worker, and wake word."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch
import pytest

from core.state import AppState
from voice.speech_input import SpeechInput
from voice.speech_output import SpeechOutput, prepare_for_speech
from voice.wake_word import WakeWordDetector


def test_speech_output_availability_and_voices() -> None:
    tts = SpeechOutput()
    with patch.object(tts, "get_voices", return_value=[{"id": "v1", "name": "David"}]):
        with patch("voice.speech_output.HAS_PYTTSX3", True):
            assert tts.is_available() is True
            assert "ready" in tts.status_message().lower() or tts.get_voices()


def test_speech_output_speak_and_stop() -> None:
    tts = SpeechOutput()
    started = []
    done = []

    with patch.object(tts, "_speak_kokoro", return_value=False), patch("pyttsx3.init") as mock_init:
        mock_engine = MagicMock()
        mock_init.return_value = mock_engine

        result = tts.speak(
            "Hello world",
            on_start=lambda: started.append(True),
            on_done=lambda: done.append(True),
            block=True,
        )

        assert result is True
        assert len(started) == 1
        assert len(done) == 1
        mock_engine.say.assert_called_once_with("Hello world")
        mock_engine.runAndWait.assert_called_once()

    # Interruption test
    tts.stop()
    assert tts.is_speaking is False


def test_prepare_for_speech_strips_markup() -> None:
    spoken = prepare_for_speech("**Hello.** See https://example.com/a for more.\n- one item")
    assert "http" not in spoken
    assert "*" not in spoken
    assert "Hello." in spoken
    assert "a link" in spoken


def test_neural_voice_does_not_call_the_network_when_mocked() -> None:
    tts = SpeechOutput(provider="edge")
    with patch.object(tts, "_speak_kokoro", return_value=False), \
         patch("voice.speech_output.HAS_EDGE", True), \
         patch.object(tts, "_speak_edge") as speak_edge:
        assert tts.speak("Hello there.", block=True) is True
    speak_edge.assert_called_once()
    assert tts.is_speaking is False


def test_speech_output_rejects_empty_string() -> None:
    tts = SpeechOutput()
    assert tts.speak("   ") is False


def test_speech_input_availability_and_devices() -> None:
    si = SpeechInput()
    with patch("voice.speech_input.HAS_SR", True), patch("voice.speech_input.HAS_PYAUDIO", True):
        with patch.object(si, "list_microphones", return_value=[{"index": 0, "name": "Mic"}]):
            assert si.is_available() is True
            assert "ready" in si.status_message().lower()


def test_speech_input_missing_dependency() -> None:
    si = SpeechInput()
    with patch("voice.speech_input.HAS_SR", False):
        assert si.is_available() is False
        assert "not installed" in si.status_message().lower()
        ok, message = si.listen_once()
        assert ok is False
        assert "not available" in message.lower() or "not installed" in message.lower()


def test_speech_output_missing_dependency() -> None:
    tts = SpeechOutput()
    with patch("voice.speech_output.HAS_PYTTSX3", False), \
         patch("voice.kokoro_engine.available", return_value=False), \
         patch("voice.speech_output.HAS_EDGE", False):
        assert tts.speak("hello") is False


def test_voice_can_be_disabled_by_config() -> None:
    assert SpeechInput(enabled=False).is_available() is False
    assert "disabled" in SpeechInput(enabled=False).status_message().lower()
    assert SpeechOutput(enabled=False).is_available() is False
    assert SpeechOutput(enabled=False).speak("hello") is False


def test_speech_input_listen_success() -> None:
    si = SpeechInput()
    with patch("speech_recognition.Microphone") as mock_mic_cls, \
         patch.object(si._recognizer, "adjust_for_ambient_noise"), \
         patch.object(si._recognizer, "listen") as mock_listen, \
         patch.object(si._recognizer, "recognize_google", return_value="hello orion"):
        mock_mic_cls.return_value.__enter__.return_value = MagicMock()
        mock_listen.return_value = MagicMock()

        ok, text = si.listen_once(timeout=2.0)
        assert ok is True
        assert text == "hello orion"


def test_speech_input_listen_timeout() -> None:
    import speech_recognition as sr

    si = SpeechInput()
    with patch("speech_recognition.Microphone") as mock_mic_cls, \
         patch.object(si._recognizer, "adjust_for_ambient_noise"), \
         patch.object(si._recognizer, "listen", side_effect=sr.WaitTimeoutError):
        mock_mic_cls.return_value.__enter__.return_value = MagicMock()
        ok, msg = si.listen_once(timeout=1.0)
        assert ok is False
        assert "timed out" in msg.lower()


def test_speech_input_listen_unknown_value() -> None:
    import speech_recognition as sr

    si = SpeechInput()
    with patch("speech_recognition.Microphone") as mock_mic_cls, \
         patch.object(si._recognizer, "adjust_for_ambient_noise"), \
         patch.object(si._recognizer, "listen", return_value=MagicMock()), \
         patch.object(si._recognizer, "recognize_google", side_effect=sr.UnknownValueError):
        mock_mic_cls.return_value.__enter__.return_value = MagicMock()
        ok, msg = si.listen_once(timeout=1.0)
        assert ok is False
        assert "could not understand" in msg.lower()


def test_speech_input_listen_service_error() -> None:
    import speech_recognition as sr

    si = SpeechInput()
    with patch("speech_recognition.Microphone") as mock_mic_cls, \
         patch.object(si._recognizer, "adjust_for_ambient_noise"), \
         patch.object(si._recognizer, "listen", return_value=MagicMock()), \
         patch.object(si._recognizer, "recognize_google", side_effect=sr.RequestError("API rate limit")):
        mock_mic_cls.return_value.__enter__.return_value = MagicMock()
        ok, msg = si.listen_once(timeout=1.0)
        assert ok is False
        assert "service error" in msg.lower()


def test_speech_input_missing_mic_hardware_error() -> None:
    si = SpeechInput()
    with patch("speech_recognition.Microphone", side_effect=OSError("No default input device")):
        ok, msg = si.listen_once(timeout=1.0)
        assert ok is False
        assert "microphone device error" in msg.lower()


def test_speech_input_cancellation() -> None:
    si = SpeechInput()
    cancel_event = threading.Event()
    cancel_event.set()

    ok, msg = si.listen_once(cancel_event=cancel_event)
    assert ok is False
    assert "cancelled" in msg.lower()


def test_wake_word_optional_not_claimed() -> None:
    detector = WakeWordDetector()
    assert detector.is_available() is False
    assert "optional" in detector.status_message().lower()
