"""Phone audio in, Kokoro audio out."""

from __future__ import annotations

import io
import uuid
import wave
from typing import Any

_clips: dict[str, bytes] = {}


def transcribe_upload(payload: bytes, content_type: str) -> tuple[bool, str]:
    samples = _to_pcm(payload, content_type)
    if samples is None:
        return False, "I could not read that audio."
    from voice.speech_input import _local_ready, _transcribe_local

    if not _local_ready():
        return False, "Local speech is not loaded yet."

    class _Clip:
        def get_raw_data(self, convert_rate: int = 16000, convert_width: int = 2) -> bytes:
            return samples

    text = _transcribe_local(_Clip())
    if not text:
        return False, "Could not understand audio."
    return True, text


def store_speech(samples: Any, sample_rate: int) -> str:
    import numpy as np

    pcm = (np.asarray(samples) * 32767).astype("<i2").tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    clip_id = uuid.uuid4().hex
    _clips[clip_id] = buffer.getvalue()
    if len(_clips) > 8:
        _clips.pop(next(iter(_clips)))
    return clip_id


def take_clip(clip_id: str) -> bytes | None:
    return _clips.get(clip_id)


def _to_pcm(payload: bytes, content_type: str) -> bytes | None:
    if payload[:4] == b"RIFF":
        with wave.open(io.BytesIO(payload), "rb") as handle:
            return handle.readframes(handle.getnframes())
    if "webm" in content_type or "ogg" in content_type or payload[:4] == b"\x1a\x45\xdf\xa3":
        return _decode_container(payload)
    if len(payload) >= 2 and len(payload) % 2 == 0:
        return payload
    return None


def _decode_container(payload: bytes) -> bytes | None:
    try:
        import av
        import numpy as np
    except ImportError:
        return None
    container = av.open(io.BytesIO(payload))
    chunks: list[Any] = []
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
    for frame in container.decode(audio=0):
        for item in resampler.resample(frame):
            chunks.append(item.to_ndarray())
    if not chunks:
        return None
    return np.concatenate(chunks).astype("<i2").tobytes()
