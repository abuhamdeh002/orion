"""Optional acoustic wake model.

The live wake phrase ("Hey Orion") is heard by the speech-recognition loop in
voice/conversation.py. A custom openWakeWord model can make that cheaper: train
one for the phrase (openWakeWord's synthetic-data notebook) and drop it at
data/models/hey_orion.onnx. Without that file this detector reports unavailable.
"""

from __future__ import annotations

from pathlib import Path

from app.brand import SLUG, WAKE_PHRASE


def model_path() -> Path:
    from app.paths import app_data_dir

    return app_data_dir() / "models" / f"hey_{SLUG}.onnx"


class WakeWordDetector:
    def __init__(self, path: Path | None = None) -> None:
        self._model = None
        self.path = path or model_path()
        if not self.path.is_file():
            return
        try:
            from openwakeword.model import Model

            self._model = Model(wakeword_models=[str(self.path)])
        except Exception:
            self._model = None

    def is_available(self) -> bool:
        return self._model is not None

    def status_message(self) -> str:
        if self._model is not None:
            return f"Wake word ready ({WAKE_PHRASE})."
        return (
            f"The acoustic wake model is optional. Without {self.path.name}, '{WAKE_PHRASE}' is heard by speech recognition instead. "
            "The hotkey and the mic button also work."
        )

    def heard(self, pcm: bytes) -> bool:
        if self._model is None or not pcm:
            return False
        scores = self._model.predict(pcm)
        return any(float(value) > 0.5 for value in scores.values())
