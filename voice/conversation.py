"""Spoken conversation. The PC microphone stays open, 'Hey Orion' wakes him, and the reply is spoken."""

from __future__ import annotations

import logging
import queue
import random
import re
import threading
import time
from typing import Any

from app.brand import WAKE_PHRASE
from voice.speech_text import ACKNOWLEDGE, HOLD_ON

logger = logging.getLogger("orion.voice.conversation")
_IDLE_LINE = f"Say {WAKE_PHRASE.title()}."

_WAKE = re.compile(
    r"^(?:hey|ok|okay|hi)?[\s,]*orion\b[\s,.:!?-]*(.*)$",
    re.IGNORECASE,
)
_END = re.compile(
    r"^(?:goodbye|good\s*bye|good\s+night|that(?:'s| is) all|stop talking|go to sleep|never mind|thanks,? that(?:'s| is) all)\b",
    re.IGNORECASE,
)
_HALT_WORDS = (
    ("stop",),
    ("stop", "talking"),
    ("shut", "up"),
    ("be", "quiet"),
    ("quiet",),
    ("silence",),
    ("enough",),
)
_QUIET = ("timed out", "no speech", "could not understand", "unintelligible")
_NAME_WORDS = {"orion", "orien", "orin", "orian", "orions", "oryn", "oriann", "orionn"}
# Only count as the name right after a greeting: "hey iron" is a wake, "pump iron" is not.
_MISHEARD = {"ryan", "rion", "iron"}
_NOT_NAMES = {"origin", "origins", "orient", "oriental", "oriented", "oriel", "orients"}

# A turn still working after this long gets a short "One moment." so the silence doesn't feel broken.
# Only for turns that are really slow (tools, a cold model): a quick answer arrives in 3-5 s,
# and "Give me a second" right before it sounds wrong.
HOLD_ON_SECONDS = 7.0

# How long ORION keeps listening without the name. Counted from when speech *starts*.
AWAKE_SECONDS = 20.0  # after a bare wake ("Hey Orion") or the UI's listen button
FOLLOW_UP_SECONDS = 8.0  # after a reply, for "and tomorrow?"
UTTERANCE_SECONDS = 15.0


def _is_name(word: str) -> bool:
    token = re.sub(r"[^a-z]", "", word.lower())
    if token in _NAME_WORDS:
        return True
    if token in _NOT_NAMES:
        return False
    return token.startswith(("orio", "oria", "orie")) and 5 <= len(token) <= 7


def has_name(text: str) -> bool:
    words = text.split()
    for index, word in enumerate(words):
        previous = re.sub(r"[^a-z]", "", words[index - 1].lower()) if index else ""
        token = re.sub(r"[^a-z]", "", word.lower())
        if _is_name(word) or (previous in {"hey", "hi", "ok", "okay", "hello"} and token in _MISHEARD):
            return True
    return False


def _configured_mic(runtime: Any) -> int | None:
    """The microphone chosen in settings, or the Windows default."""
    config = getattr(runtime, "config", None)
    return getattr(config, "microphone_device_index", None)


def _halt_words(text: str) -> list[str]:
    words = [re.sub(r"[^a-z]", "", word.lower()) for word in text.split()]
    return [word for word in words if word and word not in {"hey", "ok", "okay", "hi"}]


def _is_loop(text: str) -> bool:
    """Whisper repeats one clause when the audio is a video or the room, not a request."""
    parts = [re.sub(r"[^a-z ]", "", part.lower()).strip() for part in re.split(r"[.!?]", text)]
    parts = [part for part in parts if len(part) > 8]
    return len(parts) >= 3 and len(set(parts)) == 1


def _is_halt(words: list[str]) -> bool:
    return tuple(words) in _HALT_WORDS


_GREETINGS = {"hey", "hi", "ok", "okay", "hello", "yo", "so", "um", "uh", "oh"}
# "the Orion constellation", "Orion's belt", "in Orion": the stars, not him.
_STAR_WORDS = {"constellation", "nebula", "belt", "arm", "spacecraft", "capsule", "mission", "orions", "stars"}


def _names_the_stars(words: list[str], index: int) -> bool:
    word = words[index].lower()
    if "'s" in word or "’s" in word:
        return True
    previous = re.sub(r"[^a-z]", "", words[index - 1].lower()) if index else ""
    following = re.sub(r"[^a-z]", "", words[index + 1].lower()) if index + 1 < len(words) else ""
    if previous in {"the", "of", "in", "near", "about", "called", "named"} and not re.search(r"[,.!?]$", words[index - 1]):
        return True
    return following in _STAR_WORDS


def take_command(text: str, awake: bool) -> str | None:
    """Return the words to answer, '' to acknowledge a bare wake, or None to ignore.

    'end' means the person closed the conversation. 'Orion stop' does that even
    when he was not already in a conversation.
    """
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return None
    words = _halt_words(cleaned)
    if any(_is_name(word) for word in words) and _is_halt([word for word in words if not _is_name(word)]):
        return "end"
    if awake and _is_halt(words):
        return "end"
    match = _WAKE.match(cleaned)
    if match:
        command = match.group(1).strip(" .,!?")
        if _END.match(command):
            return "end"
        return command
    words = cleaned.split()
    for index, word in enumerate(words):
        previous = re.sub(r"[^a-z]", "", words[index - 1].lower()) if index else ""
        heard_name = _is_name(word) or (
            previous in {"hey", "hi", "ok", "okay", "hello"} and re.sub(r"[^a-z]", "", word.lower()) in _MISHEARD
        )
        if not heard_name or _names_the_stars(words, index):
            continue
        before = words[:index]
        while before and re.sub(r"[^a-z]", "", before[0].lower()) in _GREETINGS:
            before = before[1:]
        after = words[index + 1 :]
        if before:
            # "I am the one who made you, Orion" or "tell me, Orion, the time": the name is said
            # to him, and the whole sentence is the request. Only what follows the name would be
            # nothing at all, and he'd answer "Yeah?" as if he had only been called.
            # "your name is Orion" uses the name in the sentence; "made you, Orion" says it to him.
            in_sentence = re.sub(r"[^a-z]", "", before[-1].lower()) in {"is", "am", "are", "was", "be", "called", "named", "call", "name"}
            addressed = not in_sentence and (not after or bool(re.search(r"[,;:]$", before[-1])) or bool(re.search(r"[,;:.!?]$", word)))
            command = " ".join(before + after) if addressed else " ".join(before + [word] + after)
        else:
            command = " ".join(after)
        command = command.strip(" .,!?;:")
        if _END.match(command):
            return "end"
        return command
    if not awake:
        # Without the name, nothing wakes him. A TV saying "hello" is not a request.
        return None
    if re.fullmatch(r"(?:hey|hi|hello|yo|ok|okay)[!.?]*", cleaned, re.IGNORECASE):
        return ""
    if _END.match(cleaned):
        return "end"
    return cleaned


class VoiceConversation:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.phase = "off"
        self.line = _IDLE_LINE
        self.turn = 0
        self.user = ""
        self.reply = ""
        self._awake_until = 0.0
        self._hushed = False
        self._stop = threading.Event()
        self._barge = threading.Event()
        self._audio: queue.Queue[bytes] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ear: Any = None
        self._mic: Any = None
        self._heard_wake = False
        self._ack_busy = False
        self._utterance = 0
        self._speech_started = 0.0
        self._confirming = threading.Event()
        self._stream: Any = None
        self.timings: dict[str, float] = {}

    def levels(self) -> dict[str, Any]:
        from service.today import levels_from

        return levels_from(self._mic, self.runtime.speaker, self.phase)

    def status(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "line": self.line,
            "turn": self.turn,
            "user": self.user,
            "reply": self.reply,
            "awake": time.time() < self._awake_until,
        }

    def awake(self) -> None:
        self._hushed = False
        self._awake_until = time.time() + AWAKE_SECONDS
        self.line = "I'm listening."

    def hush(self) -> None:
        """Stop talking and ignore the room until the next wake word."""
        self._hushed = True
        self._awake_until = 0
        self._barge.set()
        self._drop_stream()
        self.runtime.speaker.stop()
        self.runtime.assistant.cancel()
        self._drain()
        self.phase = "idle"
        self.line = f"Stopped. {_IDLE_LINE}"
        self.reply = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="OrionVoice", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def confirm(self, request: Any) -> bool:
        from core.command_parser import confirmation_line, is_yes

        line = confirmation_line(request.arguments) if getattr(request, "tool_name", "") == "apps" else "Shall I go ahead?"
        # While this is set, the thinking loop leaves the microphone queue alone, so the "yes" reaches us.
        self._confirming.set()
        try:
            self.phase = "confirming"
            self.line = line
            self._drain()
            if self._mic is not None:
                self._mic.guard_echo = True
            self.runtime.speaker.speak(line, block=True)
            self._release_echo()
            pcm = self._wait_pcm(12)
            self.phase = "thinking"
            if not pcm or self._ear is None:
                return False
            ok, heard = self._transcribe(pcm)
            return bool(ok and is_yes(heard))
        finally:
            self._confirming.clear()

    def _run(self) -> None:
        from voice.mic_stream import MicStream
        from voice.speech_input import SpeechInput

        from voice.kokoro_engine import warmup
        from voice.speech_input import preload_local_speech

        warmup()
        preload_local_speech()
        self._ear = SpeechInput()
        self._mic = MicStream(_configured_mic(self.runtime), self._on_speech_start, self._audio.put)
        self._mic.start()
        self.runtime.warm_model_async()
        self.phase = "idle"
        self.line = _IDLE_LINE
        while not self._stop.is_set():
            pcm = self._wait_pcm(0.5)
            if pcm is None or self.phase == "confirming":
                continue
            self._handle_pcm(pcm)
        self.phase = "off"
        self._mic.stop()

    def _on_speech_start(self) -> None:
        self._speech_started = time.time()
        self._utterance += 1
        self._heard_wake = False
        self._ack_busy = False
        if self.phase != "speaking":
            return
        if self._stream is not None:
            self._stream.cancel()
        self.runtime.speaker.stop()
        self._barge.set()
        self.phase = "listening"

    def _handle_pcm(self, pcm: bytes) -> None:
        from service.runtime import KILL

        if KILL.is_set():
            return
        ended = time.monotonic()
        ok, heard = self._transcribe(pcm)
        self.timings = {"stt_ms": (time.monotonic() - ended) * 1000}
        logger.info("Heard ok=%s text=%s", ok, heard)
        if not ok:
            return
        if self._is_echo(heard) or _is_loop(heard):
            return
        # Awake is judged by when they *started* talking, so a long follow-up still counts.
        started = self._speech_started or time.time()
        awake = started < self._awake_until
        if self._mic is not None:
            self._mic.quick = not awake
        command = take_command(heard, awake)
        if command is None:
            return
        if command == "end":
            self.hush()
            return
        if command == "":
            self._hushed = False
            self._awake_until = time.time() + AWAKE_SECONDS
            self._say(random.choice(ACKNOWLEDGE))
            if self._hushed:
                return
            self.phase = "listening"
            self.line = "I'm listening."
            return
        self._answer(command)

    def _keep(self, follow: str) -> bool:
        """A one-word tail of the same sentence must not throw away the question in progress."""
        if follow in {"", "end"}:
            return True
        return len(follow.split()) >= 3

    def _answer(self, command: str) -> None:
        self._awake_until = time.time() + AWAKE_SECONDS
        while command:
            if command == "end":
                self.hush()
                return
            if command == "":
                self._hushed = False
                self._say(random.choice(ACKNOWLEDGE))
                break
            text, nxt = self._think(command)
            if self._hushed or nxt == "end":
                self._drop_stream()
                self.hush()
                return
            if nxt is not None:
                if nxt == "":
                    self._hushed = False
                    self._say(random.choice(ACKNOWLEDGE))
                    break
                command = nxt
                continue
            if not text or text == "Cancelled.":
                self._drop_stream()
                break
            logger.info("Saying %s", text)
            self._log_latency()
            self.turn += 1
            self.user = command
            self.reply = text
            self.phase = "speaking"
            self.line = text
            stream, self._stream = self._stream, None
            if stream is not None and stream.started:
                # The first sentences are already playing; finish the rest of the same reply.
                if self._mic is not None:
                    self._mic.guard_echo = True
                self._stream = stream
                stream.close(text)
                stream.wait()
                self._stream = None
            else:
                if stream is not None:
                    stream.cancel()
                self._barge.clear()
                if self._mic is not None:
                    self._mic.guard_echo = True
                self.runtime.speaker.speak(text, block=True)
            self._release_echo()
            if self._hushed or not self._barge.is_set():
                break
            command = self._barge_command()
            if not command:
                if command == "":
                    self._hushed = False
                    self._say(random.choice(ACKNOWLEDGE))
                break
            if command == "end":
                self.hush()
                break
        if self._hushed:
            self.phase = "idle"
            self.line = f"Stopped. {_IDLE_LINE}"
            return
        self._awake_until = time.time() + FOLLOW_UP_SECONDS
        self.phase = "listening"
        self.line = "I'm listening."

    def _think(self, command: str) -> tuple[str, str | None]:
        """Ask for a reply without going deaf. A new sentence replaces the one in progress.

        The second value is the replacement command, 'end' to stop, or None to speak the text.
        """
        from core.voice_mode import VOICE_TURN
        from voice.speech_output import SpeechStream

        self.phase = "thinking"
        self.line = command
        self._barge.clear()
        if self._mic is not None:
            self._mic.guard_echo = False
        box: dict[str, str] = {}
        stream = SpeechStream(self.runtime.speaker, on_start=self._speaking_early)
        self._stream = stream

        def run() -> None:
            token = VOICE_TURN.set(True)
            try:
                result = self.runtime.assistant.handle_user_message(
                    command, source="voice", confirm=self.confirm, on_token=stream.feed
                )
                box["text"] = (result.text or "").strip() or "I didn't catch a reply."
            except Exception as exc:
                logger.exception("Spoken turn failed")
                box["text"] = "Something went wrong on that one."
                self.runtime.push(str(exc), kind="voice_error")
            finally:
                VOICE_TURN.reset(token)

        thinking_from = time.monotonic()
        worker = threading.Thread(target=run, name="OrionThink", daemon=True)
        worker.start()
        replacement: str | None = None
        held = False
        while worker.is_alive():
            if self._hushed:
                self.runtime.assistant.cancel()
                replacement = "end"
                break
            if self._confirming.is_set():
                time.sleep(0.05)
                continue
            if not held and not stream.started and time.monotonic() - thinking_from > HOLD_ON_SECONDS:
                held = True
                stream.say_first(random.choice(HOLD_ON))
            pcm = self._wait_pcm(0.25)
            if pcm is None:
                continue
            ok, heard = self._transcribe(pcm)
            logger.info("Heard ok=%s text=%s", ok, heard)
            if not ok or self._is_echo(heard):
                continue
            follow = take_command(heard, True)
            if follow is None or not self._keep(follow):
                continue
            self.runtime.assistant.cancel()
            if follow == "end":
                replacement = "end"
            elif has_name(heard):
                replacement = follow  # "Orion, actually..." is a new request
            else:
                replacement = f"{command} {follow}"  # they were still talking: keep the start
            break
        worker.join(5)
        self.timings["think_ms"] = (time.monotonic() - thinking_from) * 1000
        if replacement is not None:
            self._drop_stream()
            return "", replacement
        return box.get("text") or "I didn't catch a reply.", None

    def _speaking_early(self) -> None:
        """The first sentence of the reply is ready before the rest: start talking now."""
        self.phase = "speaking"
        self._barge.clear()
        if self._mic is not None:
            self._mic.guard_echo = True

    def _drop_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.cancel()

    def _log_latency(self) -> None:
        stt = self.timings.get("stt_ms")
        think = self.timings.get("think_ms")
        if stt is not None and think is not None:
            logger.info("Latency stt_ms=%.0f think_ms=%.0f total_ms=%.0f", stt, think, stt + think)

    def say_external(self, text: str) -> None:
        """Speak a reply that came from the web or phone without the mic hearing it as a command."""

        def run() -> None:
            self._say(text)
            # Nothing else ends this speech, so settle back to listening or idle (the UI showed "speaking" forever).
            if self.phase == "speaking":
                awake = time.time() < self._awake_until
                self.phase = "listening" if awake else ("idle" if self._ear is not None else "off")
                self.line = "I'm listening." if awake else _IDLE_LINE

        threading.Thread(target=run, name="OrionSayExternal", daemon=True).start()

    def _barge_command(self) -> str | None:
        """None means the interruption was not a new request. '' is a bare wake."""
        if self._hushed:
            return None
        pcm = self._wait_pcm(8)
        if pcm is None:
            return None
        ok, heard = self._transcribe(pcm)
        if not ok or self._is_echo(heard):
            return None
        return take_command(heard, True)

    def _is_echo(self, heard: str) -> bool:
        heard_n = re.sub(r"[^a-z0-9 ]", "", heard.lower()).strip()
        said = f"{self.reply or ''} {self._stream.spoken if self._stream is not None else ''}"
        reply_n = re.sub(r"[^a-z0-9 ]", "", said.lower()).strip()
        if len(heard_n) < 3 or not reply_n:
            return False
        if heard_n == reply_n or heard_n in reply_n or reply_n in heard_n:
            return True
        skip = {"this", "that", "with", "from", "have", "your", "just", "what", "when", "were", "them"}
        heard_stems = {word[:6] for word in heard_n.split() if len(word) > 5 and word not in skip}
        reply_stems = {word[:6] for word in reply_n.split() if len(word) > 5 and word not in skip}
        return bool(heard_stems & reply_stems)

    def _release_echo(self) -> None:
        """Keep his own voice out of the next clip, then listen again."""
        if self._mic is None:
            return
        self._mic.guard_echo = True
        token = time.time()
        self._echo_token = token

        def _later() -> None:
            time.sleep(0.45)
            if getattr(self, "_echo_token", None) != token or self.phase == "speaking":
                return
            if self._mic is not None:
                self._mic.guard_echo = False
                self._mic.quick = time.time() >= self._awake_until

        threading.Thread(target=_later, name="OrionEcho", daemon=True).start()

    def _say(self, text: str) -> None:
        self._barge.clear()
        if self._mic is not None:
            self._mic.guard_echo = True
        self.phase = "speaking"
        self.line = text
        self.reply = text
        try:
            self.runtime.speaker.speak(text, block=True)
        finally:
            self._release_echo()

    def _transcribe(self, pcm: bytes) -> tuple[bool, str]:
        import speech_recognition as sr

        if self._ear is None:
            return False, ""
        return self._ear.transcribe(sr.AudioData(pcm, 16000, 2))

    def _wait_pcm(self, timeout: float) -> bytes | None:
        try:
            return self._audio.get(timeout=timeout)
        except queue.Empty:
            return None

    def _drain(self) -> None:
        while True:
            try:
                self._audio.get_nowait()
            except queue.Empty:
                return
