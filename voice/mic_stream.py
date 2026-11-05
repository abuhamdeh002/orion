"""One open microphone. Speech starting is enough to cut Orion off."""

from __future__ import annotations

import logging
import threading
import urllib.request
from collections import deque
from collections.abc import Callable
from pathlib import Path

import numpy as np

logger = logging.getLogger("orion.voice.mic")

VAD_URL = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
_RATE = 16000
_FRAME = 512
_CONTEXT = 64


def _vad_path() -> Path:
    path = Path(__file__).resolve().parents[1] / "data" / "models" / "silero_vad.onnx"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size < 1000:
        logger.info("Downloading speech detector")
        urllib.request.urlretrieve(VAD_URL, path)
    return path


class SpeechDetector:
    """Silero's small speech model. Returns a probability for each 32 ms frame."""

    def __init__(self) -> None:
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(_vad_path()), providers=["CPUExecutionProvider"])
        self.inputs = {item.name for item in self.session.get_inputs()}
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        # Silero scores a frame only when the previous 64 samples sit in front of it.
        self._context = np.zeros(_CONTEXT, dtype=np.float32)

    def probability(self, frame: np.ndarray) -> float:
        chunk = np.asarray(frame, dtype=np.float32).reshape(-1)[:_FRAME]
        if chunk.size < _FRAME:
            chunk = np.pad(chunk, (0, _FRAME - chunk.size))
        window = np.concatenate([self._context, chunk])
        self._context = window[-_CONTEXT:].copy()
        audio = window.reshape(1, -1)
        feed: dict[str, np.ndarray] = {"input": audio}
        if "state" in self.inputs:
            feed["state"] = self.state
        if "sr" in self.inputs:
            feed["sr"] = np.array(16000, dtype=np.int64)
        if "h" in self.inputs:
            feed["h"] = self.state
            feed["c"] = np.zeros_like(self.state)
        outputs = self.session.run(None, feed)
        if "state" in self.inputs or "h" in self.inputs:
            self.state = outputs[1]
        value = outputs[0]
        return float(np.reshape(value, -1)[0])


class MicStream:
    def __init__(
        self,
        device_index: int | None,
        on_start: Callable[[], None],
        on_audio: Callable[[bytes], None],
        headset: bool = True,
        on_partial: Callable[[bytes], None] | None = None,
    ) -> None:
        self.device_index = device_index
        self.on_start = on_start
        self.on_audio = on_audio
        self.on_partial = on_partial
        self.headset = headset
        self.guard_echo = False
        self.level = 0.0
        self.quick = True
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="OrionMic", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        import pyaudio

        pa = None
        stream = None
        try:
            detector = SpeechDetector()
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=_RATE,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=_FRAME,
            )
            logger.info("Microphone open (device_index=%s)", self.device_index)
            preroll: deque[bytes] = deque(maxlen=10)
            speech: list[bytes] = []
            hot = 0
            quiet = 0
            talking = False
            while not self._stop.is_set():
                raw = stream.read(_FRAME, exception_on_overflow=False)
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                if samples.size < _FRAME:
                    samples = np.pad(samples, (0, _FRAME - samples.size))
                probability = detector.probability(samples[:_FRAME])
                preroll.append(raw)
                # While Orion is speaking, ignore speaker bleed. A real interruption is louder and lasts longer.
                level = float(np.sqrt(np.mean(samples[:_FRAME] ** 2)))
                self.level = level
                needed = 12 if self.guard_echo else 3
                loud_enough = level >= 0.05 if self.guard_echo else True
                if not talking:
                    hot = hot + 1 if probability >= 0.55 and loud_enough else 0
                    if hot >= needed:
                        talking = True
                        speech = list(preroll)
                        quiet = 0
                        try:
                            self.on_start()
                        except Exception:
                            logger.exception("Speech-start handler failed")
                    continue
                speech.append(raw)
                if self.on_partial and len(speech) == 16:
                    try:
                        self.on_partial(b"".join(speech))
                    except Exception:
                        logger.exception("Partial speech handler failed")
                quiet = quiet + 1 if probability < 0.35 else 0
                # About 0.45 s of silence ends a wake phrase, 0.6 s ends a request.
                quiet_need = 14 if self.quick else 19
                # 8 s for "Hey Orion, ..." and 15 s once awake. Silero decides the end, not the cap.
                limit = 250 if self.quick else 470
                if quiet >= quiet_need or len(speech) > limit:
                    talking = False
                    hot = 0
                    payload = b"".join(speech)
                    speech = []
                    try:
                        self.on_audio(payload)
                    except Exception:
                        logger.exception("Utterance handler failed")
        except Exception:
            logger.exception("Microphone stream failed")
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            if pa is not None:
                pa.terminate()
