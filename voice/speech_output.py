"""Text-to-speech. Neural voices via edge-tts, with pyttsx3 as the offline fallback."""

from __future__ import annotations

import asyncio
import ctypes
import logging
import re
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from voice.speech_text import pause_after, speakable

logger = logging.getLogger("orion.voice.speech_output")

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

try:
    import pythoncom
    HAS_PYTHONCOM = True
except ImportError:
    HAS_PYTHONCOM = False

try:
    import edge_tts
    HAS_EDGE = True
except ImportError:
    HAS_EDGE = False

DEFAULT_NEURAL_VOICE = "en-GB-ThomasNeural"

NEURAL_VOICES: list[dict[str, str]] = [
    {"id": "en-GB-ThomasNeural", "name": "Thomas — British, warm"},
    {"id": "en-GB-RyanNeural", "name": "Ryan — British, younger"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia — British"},
    {"id": "en-US-AndrewNeural", "name": "Andrew — American"},
    {"id": "en-US-BrianNeural", "name": "Brian — American"},
    {"id": "en-US-AvaNeural", "name": "Ava — American"},
    {"id": "en-US-EmmaNeural", "name": "Emma — American"},
]

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_URL = re.compile(r"https?://\S+")
_MARKDOWN = re.compile(r"[*_`#>]+")
_BULLET = re.compile(r"(?m)^\s*[-*]\s+")


def prepare_for_speech(text: str, limit: int = 900) -> str:
    """Turn a chat reply into something that should be spoken, not read as markup."""
    cleaned = _CODE_FENCE.sub(" ", text)
    cleaned = _URL.sub(" a link ", cleaned)
    cleaned = _BULLET.sub("", cleaned)
    cleaned = _MARKDOWN.sub("", cleaned)
    cleaned = speakable(re.sub(r"\s+", " ", cleaned).strip())
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    end = max(cut.rfind("."), cut.rfind("?"), cut.rfind("!"))
    if end > 200:
        return cut[: end + 1]
    return cut.rsplit(" ", 1)[0]


def spoken_chunks(text: str) -> list[str]:
    """Break a reply into short spoken pieces so the first sentence can start immediately."""
    pieces = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", text)
    chunks: list[str] = []
    for piece in pieces:
        words = piece.split()
        if not words:
            continue
        if len(words) <= 18:
            chunks.append(" ".join(words))
            continue
        clause = ""
        for word in words:
            clause = f"{clause} {word}".strip()
            if word.endswith(",") and len(clause.split()) >= 8:
                chunks.append(clause)
                clause = ""
        if clause:
            chunks.append(clause)
    return [chunk for chunk in chunks if chunk][:6]


def kokoro_speed(words_per_minute: int) -> float:
    """The words-per-minute setting as a Kokoro speed. 180 is a person's pace (1.0)."""
    return max(0.8, min(1.3, round(words_per_minute / 180, 2)))


SAMPLE_LINE = "Evening. Your reminder is set for half past seven, and tomorrow looks clear and mild."


def voice_catalog() -> list[dict[str, object]]:
    """Every voice the picker offers: local Kokoro voices first, then the online Edge voices."""
    from voice.kokoro_engine import VOICES, available

    local_ready = available()
    voices: list[dict[str, object]] = [
        {"id": voice, "name": name, "engine": "kokoro", "online": False, "ready": local_ready}
        for voice, name in VOICES.items()
    ]
    voices += [
        {"id": item["id"], "name": item["name"].replace(" \u2014 ", " \u00b7 "), "engine": "edge", "online": True, "ready": HAS_EDGE}
        for item in NEURAL_VOICES
    ]
    return voices


def render_sample(voice_id: str, words_per_minute: int = 180, text: str = SAMPLE_LINE) -> tuple[bytes, str]:
    """Audio for a voice preview in the browser: WAV from Kokoro, MP3 from Edge."""
    from voice.kokoro_engine import VOICES, synthesize, wav_bytes

    spoken = prepare_for_speech(text)
    if voice_id in VOICES:
        samples, rate = synthesize(spoken, voice=voice_id, speed=kokoro_speed(words_per_minute))
        return wav_bytes(samples, rate), "audio/wav"
    if voice_id in {voice["id"] for voice in NEURAL_VOICES} and HAS_EDGE:
        chunks: list[bytes] = []

        async def _collect() -> None:
            communicate = edge_tts.Communicate(spoken, voice_id, rate=_rate_to_edge(words_per_minute), pitch="+1Hz")
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    chunks.append(chunk["data"])

        asyncio.run(_collect())
        return b"".join(chunks), "audio/mpeg"
    raise ValueError(f"Unknown voice: {voice_id}")


_SENTENCE_END = re.compile(r"([.!?]+[\"')\]]*)(\s+)")


class SpeechStream:
    """Speak a reply sentence by sentence while it is still being written.

    The first sentence starts as soon as it is complete. Whatever arrives while it
    plays is spoken next in one go, so the speaker prepares each following sentence
    during the one before it.
    """

    def __init__(self, speaker: "SpeechOutput", on_start: Callable[[], None] | None = None) -> None:
        self.speaker = speaker
        self.on_start = on_start
        self.spoken = ""
        self._buffer = ""
        self._ready: list[str] = []
        self._fed = ""
        self._closed = False
        self._cancelled = False
        self._wake = threading.Condition()
        self._thread: threading.Thread | None = None

    @property
    def started(self) -> bool:
        return self._thread is not None

    def feed(self, piece: str) -> None:
        if self._cancelled or not piece:
            return
        with self._wake:
            self._fed += piece
            self._buffer += piece
            self._take_sentences()
            if self._ready:
                self._ensure_thread()
                self._wake.notify_all()

    def say_first(self, line: str, grace: float = 0.6) -> None:
        """A short line ("One moment.") while a slow turn is still working. Only before anything else."""
        def later() -> None:
            time.sleep(grace)
            with self._wake:
                # The answer got here first: say that instead of "One moment" right before it.
                if self._cancelled or self.started or self._ready or self._fed.strip():
                    return
                self._ready.insert(0, line)
                self._ensure_thread()
                self._wake.notify_all()

        with self._wake:
            if self._cancelled or self.started:
                return
        if grace <= 0:
            later()
            return
        threading.Thread(target=later, name="OrionHoldOn", daemon=True).start()

    def close(self, final_text: str = "") -> None:
        """The reply is complete. Speak whatever of it has not been spoken yet."""
        with self._wake:
            fed = self._fed
            if final_text and not fed.strip():
                self._buffer = final_text
            elif final_text.startswith(fed) and len(final_text) > len(fed):
                self._buffer += final_text[len(fed):]
            elif final_text and final_text != fed:
                common = 0
                for mine, theirs in zip(fed, final_text):
                    if mine != theirs:
                        break
                    common += 1
                if common >= len(fed.rstrip()) - 2:
                    # Same reply with an ending added ("Hello." -> "Hello, sir."): say the new part.
                    self._buffer = final_text[common:]
                else:
                    # A different, corrected answer replaced what was being said: drop what hasn't
                    # been spoken yet and say the correction whole.
                    self._ready.clear()
                    self._buffer = final_text
            rest = self._buffer.strip()
            self._buffer = ""
            if rest and not self._cancelled:
                self._ready.append(rest)
                self._ensure_thread()
            self._closed = True
            self._wake.notify_all()

    def cancel(self) -> None:
        with self._wake:
            self._cancelled = True
            self._ready.clear()
            self._buffer = ""
            self._wake.notify_all()
        self.speaker.stop()

    def wait(self, timeout: float = 180.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _take_sentences(self) -> None:
        while True:
            match = _SENTENCE_END.search(self._buffer)
            if match is None:
                return
            sentence = self._buffer[: match.end(1)]
            # "Sure." on its own waits for the next sentence, so the two are spoken together.
            if not self.started and not self._ready and len(sentence) < 14:
                nxt = _SENTENCE_END.search(self._buffer, match.end())
                if nxt is None:
                    return
                sentence = self._buffer[: nxt.end(1)]
                match = nxt
            self._buffer = self._buffer[match.end():]
            self._ready.append(sentence)

    def _ensure_thread(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="OrionSpeechStream", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        first = True
        while True:
            with self._wake:
                while not self._ready and not self._closed and not self._cancelled:
                    self._wake.wait(0.25)
                if self._cancelled or (not self._ready and self._closed):
                    return
                batch = " ".join(part.strip() for part in self._ready)
                self._ready.clear()
            if first and self.on_start:
                self.on_start()
            first = False
            self.spoken = f"{self.spoken} {batch}".strip()
            self.speaker.speak(batch, block=True)
            if self._cancelled:
                return


def _varied_rates(words_per_minute: int, count: int) -> list[str]:
    """A flat rate is what makes a neural voice sound like a recording."""
    base = int(_rate_to_edge(words_per_minute).removesuffix("%"))
    offsets = (-3, 2, -6, 1)
    return [f"{max(-18, min(12, base + offsets[index % 4])):+d}%" for index in range(count)]


def _rate_to_edge(words_per_minute: int) -> str:
    """Map the old words-per-minute setting onto an edge-tts rate. 180 is slightly slow."""
    percent = int(round((words_per_minute - 180) / 180 * 100)) - 4
    percent = max(-30, min(40, percent))
    return f"{percent:+d}%"


class SpeechOutput:
    """Speak replies. Provider 'edge' uses a neural voice; 'pyttsx3' is the system voice."""

    def __init__(
        self,
        voice_id: str | None = None,
        rate: int = 180,
        volume: float = 1.0,
        enabled: bool = True,
        provider: str = "pyttsx3",
    ) -> None:
        self.enabled = enabled
        self.voice_id = voice_id
        self.rate = rate
        self.volume = max(0.0, min(1.0, volume))
        self.provider = provider
        self._current_engine: Any = None
        self._lock = threading.Lock()
        self._is_speaking = False
        self._stop_event = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._last_spoken_text: str | None = None
        self._mci_alias: str | None = None
        self._clip: tuple[Any, int, float] | None = None

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if self.provider == "edge" and HAS_EDGE:
            return True
        if not HAS_PYTTSX3:
            return False
        try:
            return len(self.get_voices()) > 0
        except Exception:
            return False

    def status_message(self) -> str:
        if not self.enabled:
            return "Speech output is disabled."
        if self.provider == "edge" and HAS_EDGE:
            return f"Neural voice ready ({self._neural_voice()})"
        if not HAS_PYTTSX3:
            return "pyttsx3 is not installed."
        try:
            voices = self.get_voices()
            if voices:
                return f"pyttsx3 (SAPI5) ready ({len(voices)} voices)"
            return "No TTS voices found."
        except Exception as exc:
            return f"TTS unavailable: {exc}"

    def get_voices(self) -> list[dict[str, str]]:
        if self.provider == "edge" and HAS_EDGE:
            return list(NEURAL_VOICES)
        return self._system_voices()

    def _neural_voice(self) -> str:
        chosen = self.voice_id or DEFAULT_NEURAL_VOICE
        known = {voice["id"] for voice in NEURAL_VOICES}
        if chosen in known:
            return chosen
        return DEFAULT_NEURAL_VOICE

    def _system_voices(self) -> list[dict[str, str]]:
        if not HAS_PYTTSX3:
            return []
        try:
            if HAS_PYTHONCOM:
                pythoncom.CoInitialize()
            engine = pyttsx3.init()
            voices = engine.getProperty("voices") or []
            result = []
            for voice in voices:
                result.append({
                    "id": str(getattr(voice, "id", "")),
                    "name": str(getattr(voice, "name", "Default Voice")),
                    "languages": str(getattr(voice, "languages", "")),
                })
            return result
        except Exception as exc:
            logger.warning("Could not enumerate voices: %s", exc)
            return []

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def output_level(self) -> float | None:
        """Loudness of ORION's voice right now (RMS, 0..1). None while speaking with an online voice we can't measure."""
        clip = self._clip
        if clip is None:
            return None if self._is_speaking else 0.0
        samples, rate, started = clip
        position = int((time.monotonic() - started) * rate)
        window = samples[position: position + int(rate * 0.05)]
        if len(window) == 0:
            return 0.0
        import numpy as np

        return float(np.sqrt(np.mean(np.square(window))))

    def stop(self) -> None:
        """Interrupt any ongoing speech playback."""
        self._stop_event.set()
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass
        alias = self._mci_alias
        if alias:
            try:
                ctypes.windll.winmm.mciSendStringW(f"stop {alias}", None, 0, None)
            except Exception as exc:
                logger.debug("Error while stopping playback: %s", exc)
        with self._lock:
            if self._current_engine is not None:
                try:
                    self._current_engine.stop()
                except Exception as exc:
                    logger.debug("Error while stopping TTS engine: %s", exc)
            self._is_speaking = False

    def speak(
        self,
        text: str,
        voice_id: str | None = None,
        rate: int | None = None,
        volume: float | None = None,
        on_start: Callable[[], None] | None = None,
        on_done: Callable[[], None] | None = None,
        block: bool = False,
    ) -> bool:
        """Speak text. Non-blocking by default."""
        cleaned = prepare_for_speech(text)
        if not cleaned or not self.enabled:
            return False
        if not self._can_speak():
            return False

        self.stop()
        # Let the previous utterance see the stop before the flag is reset, or it keeps playing.
        self._idle.wait(1.5)
        self._stop_event.clear()
        chosen_voice = voice_id or self.voice_id
        effective_rate = rate or self.rate
        effective_volume = volume if volume is not None else self.volume

        def _worker() -> None:
            self._idle.clear()
            try:
                with self._lock:
                    self._is_speaking = True
                if on_start and not self._stop_event.is_set():
                    on_start()
                if self._stop_event.is_set():
                    return
                for engine in self._engine_order():
                    if self._stop_event.is_set():
                        return
                    if engine == "elevenlabs" and self._speak_eleven(cleaned):
                        break
                    if engine == "kokoro" and self._speak_kokoro(cleaned, chosen_voice, effective_rate):
                        break
                    if engine == "edge" and HAS_EDGE:
                        try:
                            self._speak_edge(cleaned, chosen_voice, effective_rate)
                            break
                        except Exception as exc:
                            logger.warning("Neural voice failed, trying the next one: %s", exc)
                    if engine == "sapi" and HAS_PYTTSX3:
                        self._speak_sapi(cleaned, chosen_voice, effective_rate, effective_volume)
                        break
                self._last_spoken_text = cleaned
            except Exception as exc:
                logger.error("TTS speaking failed: %s", exc)
            finally:
                with self._lock:
                    self._current_engine = None
                    self._is_speaking = False
                self._mci_alias = None
                self._idle.set()
                if on_done:
                    on_done()

        if block:
            _worker()
            return True

        thread = threading.Thread(target=_worker, name="TTSThread", daemon=True)
        thread.start()
        return True

    def _engine_order(self) -> list[str]:
        """TTS_PROVIDER picks the first voice; the others are fallbacks, the system voice last.

        ElevenLabs is used only when ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are set.
        """
        from voice.kokoro_engine import VOICES

        # The chosen voice decides the engine, so picking a voice in Settings is enough.
        if self.voice_id in VOICES:
            first = ["kokoro", "edge"]
        elif self.voice_id in {voice["id"] for voice in NEURAL_VOICES}:
            first = ["edge", "kokoro"]
        else:
            first = {"kokoro": ["kokoro", "edge"], "edge": ["edge", "kokoro"], "pyttsx3": []}.get(self.provider, ["kokoro", "edge"])
        return ["elevenlabs", *first, "sapi"]

    def _speak_eleven(self, text: str) -> bool:
        import os

        key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        voice = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
        if not key or not voice:
            return False
        try:
            import httpx

            response = httpx.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                headers={"xi-api-key": key, "accept": "audio/mpeg"},
                json={"text": text, "model_id": "eleven_multilingual_v2"},
                timeout=30,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("ElevenLabs voice failed: %s", exc)
            return False
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
            handle.write(response.content)
            path = Path(handle.name)
        try:
            self._play_mp3(path)
        finally:
            path.unlink(missing_ok=True)
        return not self._stop_event.is_set()

    def _can_speak(self) -> bool:
        from voice.kokoro_engine import available

        if self.provider == "none":
            return False
        return available() or HAS_EDGE or HAS_PYTTSX3

    def _speak_kokoro(self, text: str, voice_id: str | None, words_per_minute: int = 180) -> bool:
        from voice.kokoro_engine import DEFAULT_VOICE, VOICES, available, synthesize

        if not available():
            return False
        voice = voice_id if voice_id in VOICES else DEFAULT_VOICE
        speed = kokoro_speed(words_per_minute)
        chunks = spoken_chunks(text) or [text]
        try:
            import sounddevice as sd
        except ImportError:
            return False
        current = None
        try:
            samples, rate = synthesize(chunks[0], voice=voice, speed=speed)
            current = (samples, rate)
            for index in range(len(chunks)):
                if self._stop_event.is_set():
                    return True
                holder: dict[str, object] = {}
                follower: threading.Thread | None = None
                if index + 1 < len(chunks):
                    nxt = chunks[index + 1]

                    def _follow(sentence: str = nxt) -> None:
                        try:
                            holder["audio"] = synthesize(sentence, voice=voice, speed=speed)
                        except Exception as exc:
                            logger.warning("Could not prepare the next sentence: %s", exc)

                    follower = threading.Thread(target=_follow, name="OrionNextLine", daemon=True)
                    follower.start()
                samples, rate = current
                sd.play(samples, rate)
                self._clip = (samples, rate, time.monotonic())
                while not self._stop_event.is_set():
                    stream = sd.get_stream()
                    if stream is None or not stream.active:
                        break
                    time.sleep(0.04)
                self._clip = None
                if self._stop_event.is_set():
                    sd.stop()
                    return True
                if follower:
                    follower.join()
                nxt_audio = holder.get("audio")
                if not isinstance(nxt_audio, tuple):
                    return True
                time.sleep(pause_after(chunks[index]))
                current = nxt_audio
            return True
        except Exception as exc:
            logger.warning("Kokoro voice failed, using the neural fallback: %s", exc)
            try:
                import sounddevice as sd

                sd.stop()
            except Exception:
                pass
            return False

    def _speak_edge(self, text: str, voice_id: str | None, words_per_minute: int) -> None:
        voice = voice_id if voice_id in {item["id"] for item in NEURAL_VOICES} else self._neural_voice()
        chunks = spoken_chunks(text) or [text]
        rates = _varied_rates(words_per_minute, len(chunks))
        paths: list[Path] = []
        try:
            current = self._render_edge(chunks[0], voice, rates[0])
            paths.append(current)
            for index, _chunk in enumerate(chunks):
                if self._stop_event.is_set():
                    return
                holder: dict[str, Path] = {}
                follower: threading.Thread | None = None
                if index + 1 < len(chunks):
                    nxt = index + 1

                    def _follow(sentence: str = chunks[nxt], rate: str = rates[nxt]) -> None:
                        try:
                            holder["path"] = self._render_edge(sentence, voice, rate)
                        except Exception as exc:
                            logger.warning("Could not prepare the next sentence: %s", exc)

                    follower = threading.Thread(target=_follow, name="OrionNextLine", daemon=True)
                    follower.start()
                self._play_mp3(current)
                if follower:
                    follower.join()
                if self._stop_event.is_set():
                    return
                nxt_path = holder.get("path")
                if nxt_path is None:
                    return
                paths.append(nxt_path)
                time.sleep(pause_after(chunks[index]))
                current = nxt_path
        finally:
            for path in paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _render_edge(self, text: str, voice: str, rate: str) -> Path:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
            path = Path(handle.name)

        async def _save() -> None:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch="+1Hz", volume="+0%")
            await communicate.save(str(path))

        asyncio.run(_save())
        return path

    def _play_mp3(self, path: Path) -> None:
        alias = f"j{threading.get_ident() % 100000}"
        winmm = ctypes.windll.winmm
        opened = winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
        if opened != 0:
            raise RuntimeError(f"Could not open speech audio ({opened})")
        self._mci_alias = alias
        try:
            winmm.mciSendStringW(f"play {alias}", None, 0, None)
            buffer = ctypes.create_unicode_buffer(32)
            while not self._stop_event.is_set():
                winmm.mciSendStringW(f"status {alias} mode", buffer, 32, None)
                if buffer.value.lower() != "playing":
                    break
                time.sleep(0.05)
        finally:
            winmm.mciSendStringW(f"stop {alias}", None, 0, None)
            winmm.mciSendStringW(f"close {alias}", None, 0, None)
            self._mci_alias = None

    def _speak_sapi(
        self,
        text: str,
        voice_id: str | None,
        words_per_minute: int,
        volume: float,
    ) -> None:
        if HAS_PYTHONCOM:
            try:
                pythoncom.CoInitialize()
            except Exception:
                pass
        try:
            engine = pyttsx3.init()
            with self._lock:
                self._current_engine = engine
            if voice_id and not str(voice_id).endswith("Neural"):
                try:
                    engine.setProperty("voice", voice_id)
                except Exception as exc:
                    logger.warning("Failed to set voice '%s': %s", voice_id, exc)
            try:
                engine.setProperty("rate", words_per_minute)
            except Exception:
                pass
            try:
                engine.setProperty("volume", volume)
            except Exception:
                pass
            if not self._stop_event.is_set():
                engine.say(text)
                engine.runAndWait()
        finally:
            if HAS_PYTHONCOM:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
