"""A soft two-note chime, made on the fly so there's no sound file to ship."""

from __future__ import annotations

import logging

logger = logging.getLogger("orion.voice.chime")


def chime_samples(rate: int = 24000):
    """A bell-like E6 then A5: a quick attack and a long, gentle decay."""
    import numpy as np

    def note(freq: float, seconds: float) -> "np.ndarray":
        t = np.arange(int(rate * seconds)) / rate
        tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2.0 * t) + 0.12 * np.sin(2 * np.pi * freq * 3.01 * t)
        envelope = np.minimum(1.0, t / 0.008) * np.exp(-t * 4.2)
        return tone * envelope

    gap = np.zeros(int(rate * 0.07))
    sound = np.concatenate([note(1318.5, 0.55), gap, note(880.0, 0.9)])
    return (0.28 * sound / np.max(np.abs(sound))).astype("float32"), rate


def chime() -> None:
    """Play it and wait. Never raises: a missing sound device must not stop a reminder."""
    try:
        import sounddevice as sd

        samples, rate = chime_samples()
        sd.play(samples, rate)
        sd.wait()
    except Exception as exc:
        logger.warning("Could not play the chime: %s", exc)
