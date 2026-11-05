"""Speech that sounds like a person: spoken forms, natural pauses, and talking before the reply is finished."""

from __future__ import annotations

import threading
import time
from datetime import date

import pytest

from voice.speech_output import SpeechStream, kokoro_speed, prepare_for_speech, voice_catalog
from voice.speech_text import pause_after, speakable

TODAY = date(2026, 11, 5)


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        ("Reminder set: drink water at 2026-11-05 04:07.", "Reminder set: drink water today at four oh seven."),
        ("Booked for 2026-11-06 18:30.", "Booked for tomorrow at half past six."),
        ("Your flight is on 2027-01-03 09:15.", "Your flight is on January 3rd, 2027 at quarter past nine."),
        ("Meeting at 10:05 PM.", "Meeting at ten oh five p.m."),
        ("It is 21°C, 60% humidity, wind 12 km/h.", "It is 21 degrees Celsius, 60 percent humidity, wind 12 kilometres an hour."),
        ("ORION is ready, e.g. for timers.", "Orion is ready, for example, for timers."),
        ("Done 🙂", "Done"),
    ],
)
def test_written_forms_become_spoken_forms(written, spoken):
    assert speakable(written, today=TODAY) == spoken


def test_markup_is_still_removed_before_speaking():
    assert prepare_for_speech("**Done.** It is 6:15.") == "Done. It is quarter past six."


def test_questions_get_a_longer_breath_than_commas():
    assert pause_after("Shall I?") > pause_after("Right.") > pause_after("First,")


def test_natural_pace_is_one_point_zero():
    assert kokoro_speed(180) == 1.0
    assert kokoro_speed(400) == 1.3 and kokoro_speed(50) == 0.8


def test_catalog_offers_local_and_online_voices():
    engines = {voice["engine"] for voice in voice_catalog()}
    assert engines == {"kokoro", "edge"}
    assert all(not voice["online"] for voice in voice_catalog() if voice["engine"] == "kokoro")


class _Speaker:
    def __init__(self, hold: float = 0.0) -> None:
        self.said: list[str] = []
        self.hold = hold
        self.stops = 0

    def speak(self, text, block=False, **_kwargs):
        self.said.append(text)
        time.sleep(self.hold)
        return True

    def stop(self):
        self.stops += 1


def test_first_sentence_is_spoken_before_the_reply_is_finished():
    speaker = _Speaker(hold=0.2)
    started = threading.Event()
    stream = SpeechStream(speaker, on_start=started.set)
    stream.feed("The sky looks blue because air scatters ")
    assert not stream.started
    stream.feed("short blue light the most. More of it ")
    assert started.wait(1) and speaker.said == ["The sky looks blue because air scatters short blue light the most."]
    stream.feed("reaches your eyes from every direction.")
    stream.close("The sky looks blue because air scatters short blue light the most. More of it reaches your eyes from every direction.")
    stream.wait(3)
    assert speaker.said[1:] == ["More of it reaches your eyes from every direction."]


def test_a_tiny_first_sentence_waits_for_the_next():
    speaker = _Speaker()
    stream = SpeechStream(speaker)
    stream.feed("Sure. ")
    assert not stream.started
    stream.feed("It's nine degrees outside. ")
    stream.close()
    stream.wait(2)
    assert speaker.said == ["Sure. It's nine degrees outside."]


def test_a_reply_that_arrives_whole_is_spoken_once():
    speaker = _Speaker()
    stream = SpeechStream(speaker)
    stream.close("That's 36.")
    stream.wait(2)
    assert speaker.said == ["That's 36."]


def test_cancel_stops_the_rest():
    speaker = _Speaker(hold=0.3)
    stream = SpeechStream(speaker)
    stream.feed("First sentence is long enough. ")
    time.sleep(0.05)
    stream.feed("Second one should never be spoken. ")
    stream.cancel()
    stream.close()
    stream.wait(2)
    assert speaker.said == ["First sentence is long enough."]
    assert speaker.stops == 1


def test_hold_on_line_only_before_the_reply():
    speaker = _Speaker()
    stream = SpeechStream(speaker)
    stream.say_first("One moment.", grace=0)
    stream.close("Your reminder is set.")
    stream.wait(2)
    spoken = " ".join(speaker.said)
    assert spoken.startswith("One moment.") and spoken.endswith("Your reminder is set.")
    assert spoken.count("One moment.") == 1


def test_voice_turn_streams_and_does_not_repeat_itself(monkeypatch):
    """The reply is spoken while it is written, and the finished text is not spoken a second time."""
    from voice.conversation import VoiceConversation

    speaker = _Speaker(hold=0.05)
    reply = "Clouds are made of tiny water droplets. They float because they are so light."

    class Assistant:
        def handle_user_message(self, text, **turn):
            for word in reply.split(" "):
                turn["on_token"](word + " ")
                time.sleep(0.01)

            class Reply:
                text = reply

            return Reply()

        def cancel(self):
            pass

    runtime = type("R", (), {"speaker": speaker, "assistant": Assistant(), "push": lambda *a, **k: None})()
    voice = VoiceConversation(runtime)
    monkeypatch.setattr(voice, "_wait_pcm", lambda timeout: time.sleep(min(timeout, 0.05)))
    monkeypatch.setattr(voice, "_release_echo", lambda: None)
    voice._answer("why do clouds float")
    spoken = " ".join(speaker.said)
    assert spoken == reply
    assert voice.phase == "listening"


def test_voice_picker_endpoints(monkeypatch):
    from fastapi.testclient import TestClient

    from service.api import app
    from service.runtime import get_runtime

    local = TestClient(app, client=("127.0.0.1", 50000))
    listing = local.get("/voice/voices").json()
    assert listing["current"] and any(item["id"] == "bm_george" for item in listing["voices"])
    monkeypatch.setattr("voice.speech_output.render_sample", lambda voice, rate: (b"RIFF0000WAVE", "audio/wav"))
    sample = local.get("/voice/sample", params={"voice": "bm_george"})
    assert sample.status_code == 200 and sample.headers["content-type"] == "audio/wav"
    assert local.get("/voice/sample", params={"voice": "nobody"}).status_code == 404
    chosen = local.post("/voice/choose", json={"voice": "af_heart", "rate": 175}).json()
    assert chosen["current"] == "af_heart" and get_runtime().speaker.rate == 175
    assert get_runtime().speaker._engine_order()[1] == "kokoro"
    local.post("/voice/choose", json={"voice": "en-GB-RyanNeural"})
    assert get_runtime().speaker._engine_order()[1] == "edge"


def test_a_spoken_web_reply_does_not_leave_him_speaking(monkeypatch):
    from voice.conversation import VoiceConversation

    speaker = _Speaker()
    runtime = type("R", (), {"speaker": speaker, "assistant": None, "push": lambda *a, **k: None})()
    voice = VoiceConversation(runtime)
    voice._ear = object()
    monkeypatch.setattr(voice, "_release_echo", lambda: None)
    voice.say_external("It's four fourteen.")
    for _ in range(40):
        if speaker.said and voice.phase != "speaking":
            break
        time.sleep(0.05)
    assert speaker.said == ["It's four fourteen."] and voice.phase == "idle"


def test_an_added_ending_is_spoken_and_a_correction_replaces_the_rest():
    speaker = _Speaker()
    stream = SpeechStream(speaker)
    stream.feed("Good evening. ")
    stream.close("Good evening, sir.")
    stream.wait(2)
    assert " ".join(speaker.said).replace("  ", " ") in {"Good evening, sir.", ", sir."} or speaker.said[-1].endswith("sir.")

    speaker = _Speaker()
    stream = SpeechStream(speaker)
    stream.feed("Got it, I'll remind you. ")
    stream.close("I couldn't set that reminder.")
    stream.wait(2)
    assert speaker.said[-1] == "I couldn't set that reminder."


def test_a_quick_answer_drops_the_hold_on_line():
    speaker = _Speaker()
    stream = SpeechStream(speaker)
    stream.say_first("Give me a second.", grace=0.3)
    stream.feed("It's nine degrees and clear tonight. ")
    stream.close("It's nine degrees and clear tonight.")
    time.sleep(0.5)
    stream.wait(2)
    assert speaker.said == ["It's nine degrees and clear tonight."]


def test_hold_on_waits_for_genuinely_slow_turns():
    from voice.conversation import HOLD_ON_SECONDS

    assert HOLD_ON_SECONDS >= 6
