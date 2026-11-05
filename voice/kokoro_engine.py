"""Local neural voice. Kokoro runs on this PC, so a reply does not wait on a speech service."""

from __future__ import annotations

import logging
import threading
import urllib.request
from pathlib import Path

logger = logging.getLogger("orion.voice.kokoro")

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
DEFAULT_VOICE = "bm_fable"
# The voices worth offering. The prefix sets the accent: b = British, a = American.
VOICES: dict[str, str] = {
    "bm_fable": "Fable · British, smooth",
    "bm_george": "George · British, deep",
    "bm_lewis": "Lewis · British, low",
    "am_michael": "Michael · American, warm",
    "am_fenrir": "Fenrir · American, rich",
    "af_heart": "Heart · American, most natural",
    "af_bella": "Bella · American, bright",
    "bf_emma": "Emma · British, clear",
}
BRITISH_VOICES = tuple(voice for voice in VOICES if voice.startswith("b"))
# A person's pace. The old 1.22 rushed every sentence and is what made him sound synthetic.
NATURAL_SPEED = 1.0

_engine = None
_lock = threading.Lock()


def model_dir() -> Path:
    """Repo data/models from source. A packaged install can't write next to the exe, so it uses app data."""
    import sys

    if getattr(sys, "frozen", False):
        from app.paths import app_data_dir

        root = app_data_dir() / "models"
    else:
        root = Path(__file__).resolve().parents[1] / "data" / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _fetch(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 1000:
        return
    logger.info("Downloading %s", path.name)
    urllib.request.urlretrieve(url, path)


def model_files() -> tuple[Path, Path]:
    folder = model_dir()
    return folder / "kokoro-v1.0.onnx", folder / "voices-v1.0.bin"


def ensure_models() -> tuple[Path, Path]:
    """Download the voice if it is missing. Only called from warmup, never while speaking."""
    model, voices = model_files()
    _fetch(MODEL_URL, model)
    _fetch(VOICES_URL, voices)
    return model, voices


def humanize_speech(text: str) -> str:
    """Say times, dates and units the way a person would (shared by every voice)."""
    from voice.speech_text import speakable

    return speakable(text)


def available() -> bool:
    """True when the voice files are already on disk. Never downloads (that would stall a reply)."""
    model, voices = model_files()
    return all(path.exists() and path.stat().st_size > 1000 for path in (model, voices))


_cache: dict[tuple[str, str, float], tuple[object, int]] = {}


def synthesize(text: str, voice: str = DEFAULT_VOICE, speed: float = NATURAL_SPEED) -> tuple[object, int]:
    """Return float samples and the sample rate. Loads the model once."""
    global _engine
    spoken = humanize_speech(text)
    chosen = voice if voice in VOICES else DEFAULT_VOICE
    speed = round(max(0.8, min(1.3, speed)), 2)
    key = (spoken, chosen, speed)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    with _lock:
        if _engine is None:
            from kokoro_onnx import Kokoro

            model, voices = model_files()
            _engine = Kokoro(str(model), str(voices))
        engine = _engine
    samples, sample_rate = engine.create(
        spoken,
        voice=chosen,
        speed=speed,
        lang="en-gb" if chosen.startswith("b") else "en-us",
        sentence_pause=0.26,
        clause_pause=0.1,
    )
    if len(spoken) <= 48:
        _cache[key] = (samples, sample_rate)
    return samples, sample_rate


def wav_bytes(samples: object, sample_rate: int) -> bytes:
    """16-bit mono WAV, for playing a voice preview in the browser."""
    import io
    import wave

    import numpy as np

    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(int(sample_rate))
        out.writeframes(pcm.tobytes())
    return buffer.getvalue()


def warmup() -> None:
    """Load the voice and keep the short lines he says most often ready."""
    from voice.speech_text import ACKNOWLEDGE, HOLD_ON

    try:
        if not available():
            ensure_models()
        for line in (*ACKNOWLEDGE, *HOLD_ON, "Alright."):
            synthesize(line)
    except Exception as exc:
        logger.warning("Voice warmup failed: %s", exc)
