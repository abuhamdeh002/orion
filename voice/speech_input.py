"""Speech-to-text adapter using SpeechRecognition with device selection and push-to-talk."""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("orion.voice.speech_input")

_local_model: Any = None
_local_failed = False
_local_lock = threading.Lock()
# base.en hears names and short commands far better than tiny.en, and still runs in real time on a CPU.
LOCAL_MODEL = "base.en"

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


def preload_local_speech() -> bool:
    """Load the local transcriber once. Google is only used when this fails."""
    global _local_model, _local_failed
    if _local_model is not None:
        return True
    if _local_failed:
        return False
    with _local_lock:
        if _local_model is not None or _local_failed:
            return _local_model is not None
        try:
            from faster_whisper import WhisperModel

            _local_model = WhisperModel(LOCAL_MODEL, device="cpu", compute_type="int8")
            logger.info("Local speech ready (%s)", LOCAL_MODEL)
            return True
        except Exception as exc:
            _local_failed = True
            logger.warning("Local speech failed to load, using the network recognizer: %s", exc)
            return False


def _local_ready() -> bool:
    return _local_model is not None


class SpeechInput:
    """Microphone audio capture and transcription wrapper."""

    def __init__(self, device_index: int | None = None, enabled: bool = True) -> None:
        self.device_index = device_index
        self.enabled = enabled
        self._recognizer: Any = None
        self._listen_lock = threading.Lock()
        if HAS_SR:
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = 120
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = 1.0
            self._recognizer.non_speaking_duration = 0.45
        self._calibrated = False

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if not (HAS_SR and HAS_PYAUDIO):
            return False
        try:
            mics = self.list_microphones()
            return len(mics) > 0
        except Exception:
            return False

    def status_message(self) -> str:
        if not self.enabled:
            return "Speech input is disabled."
        if not HAS_SR:
            return "SpeechRecognition is not installed."
        if not HAS_PYAUDIO:
            return "PyAudio is not installed (required for microphone input)."
        try:
            mics = self.list_microphones()
            if not mics:
                return "No microphone devices found."
            active_name = "Default device"
            if self.device_index is not None:
                for m in mics:
                    if m["index"] == self.device_index:
                        active_name = m["name"]
                        break
            return f"Microphone ready ({active_name})"
        except Exception as exc:
            return f"Microphone error: {exc}"

    def list_microphones(self) -> list[dict[str, Any]]:
        """Return list of available microphone input devices."""
        if not (HAS_SR and HAS_PYAUDIO):
            return []
        try:
            names = sr.Microphone.list_microphone_names()
            devices: list[dict[str, Any]] = []
            seen_names: set[str] = set()
            for idx, name in enumerate(names):
                # Clean name encoding if needed
                clean_name = name.strip()
                # Deduplicate identical names to provide clean device list
                if clean_name not in seen_names:
                    seen_names.add(clean_name)
                    devices.append({"index": idx, "name": clean_name})
            return devices
        except Exception as exc:
            logger.warning("Could not enumerate microphones: %s", exc)
            return []

    def listen_once(
        self,
        device_index: int | None = None,
        timeout: float = 6.0,
        phrase_time_limit: float = 12.0,
        cancel_event: threading.Event | None = None,
    ) -> tuple[bool, str]:
        """Record a single utterance and transcribe via speech recognition.

        Returns:
            (success: bool, transcribed_text_or_error_message: str)
        """
        if not self.enabled:
            return False, "Speech input is disabled."
        if not (HAS_SR and HAS_PYAUDIO):
            return False, "Speech input dependencies are not available."

        if cancel_event and cancel_event.is_set():
            return False, "Listening cancelled."
        if not self._listen_lock.acquire(blocking=False):
            return False, "The microphone is already in use."

        target_device = device_index if device_index is not None else self.device_index

        try:
            mic = sr.Microphone(device_index=target_device)
            recognizer = self._recognizer or sr.Recognizer()

            logger.info("Opening microphone (device_index=%s)...", target_device)
            with mic as source:
                # Adjust for background noise quickly
                if not self._calibrated:
                    recognizer.adjust_for_ambient_noise(source, duration=0.2)
                    self._calibrated = True

                if cancel_event and cancel_event.is_set():
                    return False, "Listening cancelled."

                logger.info("Listening for speech (timeout=%s, phrase_limit=%s)...", timeout, phrase_time_limit)
                audio = recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )

            if cancel_event and cancel_event.is_set():
                return False, "Listening cancelled."

            # Push-to-talk is an explicit request, so the network recognizer may be used if local speech is missing.
            return self.transcribe(audio, allow_network=True)

        except sr.WaitTimeoutError:
            logger.info("Microphone timed out waiting for speech.")
            return False, "Listening timed out (no speech detected)."
        except sr.UnknownValueError:
            logger.info("Speech recognition could not understand audio.")
            return False, "Could not understand audio."
        except sr.RequestError as exc:
            logger.error("Speech recognition service request error: %s", exc)
            return False, f"Speech recognition service error: {exc}"
        except OSError as exc:
            logger.error("Microphone hardware error: %s", exc)
            return False, f"Microphone device error: {exc}"
        except Exception as exc:
            logger.exception("Unexpected error during speech input")
            return False, f"Speech input failed: {exc}"
        finally:
            self._listen_lock.release()

    def transcribe(self, audio: Any, allow_network: bool = False) -> tuple[bool, str]:
        """Turn captured audio into text.

        The always-on microphone hears the whole room, so its audio never leaves this PC:
        without the local model it reports that, instead of sending every clip to Google.
        """
        recognizer = self._recognizer or sr.Recognizer()
        try:
            if _local_ready():
                text = _transcribe_local(audio)
            elif allow_network:
                text = _best_google(recognizer, audio)
            else:
                return False, "Local speech recognition is not ready."
        except sr.UnknownValueError:
            return False, "Could not understand audio."
        except sr.RequestError as exc:
            return False, f"Speech recognition service error: {exc}"
        cleaned = (text or "").strip()
        if not cleaned:
            return False, "Could not understand audio." if _local_ready() else "No speech detected."
        return True, cleaned


def _transcribe_local(audio: Any) -> str:
    import numpy as np

    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    with _local_lock:
        model = _local_model
        if model is None:
            return ""
        segments, _info = model.transcribe(
            samples,
            language="en",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            without_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(piece.text.strip() for piece in segments).strip()


def _best_google(recognizer: Any, audio: Any) -> str:
    """Prefer the guess that contains his name. The top guess is often 'iron' or 'Orien'."""
    from voice.conversation import take_command

    raw = recognizer.recognize_google(audio, show_all=True)
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, dict):
        raise sr.UnknownValueError()
    alternatives = raw.get("alternative")
    transcripts: list[str] = []
    for item in alternatives or []:
        if isinstance(item, str) and item.strip():
            transcripts.append(item.strip())
        elif isinstance(item, dict) and str(item.get("transcript") or "").strip():
            transcripts.append(str(item["transcript"]).strip())
    if not transcripts:
        raise sr.UnknownValueError()
    for transcript in transcripts:
        if take_command(transcript, False) is not None:
            return transcript
    return transcripts[0]
