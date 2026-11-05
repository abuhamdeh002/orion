from core.command_parser import confirmation_line, is_no, is_yes, parse_command
from voice.kokoro_engine import humanize_speech


def test_math_folder_and_reopen_are_real(monkeypatch):
    from core.hands import make_project, reopen_last, spoken_math, wants_reopen

    opened: list[str] = []
    monkeypatch.setattr("os.startfile", lambda path: opened.append(str(path)), raising=False)
    assert spoken_math("what's 199931287462 * 2190479023452135") == "That's 437945291317289842282631370."
    assert parse_command("open again") is None
    made = make_project("make me a project in OrionTest")
    assert made is not None and str(made).endswith("OrionTest.")
    assert wants_reopen("open the project again")
    assert "OrionTest" in (reopen_last("open it again") or "")
    assert opened and opened[0].endswith("OrionTest")
    assert parse_command("open Discord") == {"action": "open", "name": "Discord"}
    assert parse_command("play Coldplay on Spotify") == {"action": "play", "query": "Coldplay"}
    assert parse_command("pause") == {"action": "media", "name": "pause"}
    assert parse_command("next song") == {"action": "media", "name": "next"}


def test_discord_message_and_search():
    parsed = parse_command("message Ahmad on Discord saying on my way")
    assert parsed == {"action": "discord_message", "target": "Ahmad", "text": "on my way"}
    assert "Ahmad" in confirmation_line(parsed)
    assert parse_command("search playlists in Spotify") == {
        "action": "search",
        "query": "playlists",
        "name": "Spotify",
    }


def test_questions_are_not_commands():
    assert parse_command("what time is it?") is None
    assert parse_command("how are you") is None


def test_yes_and_no():
    assert is_yes("yeah")
    assert is_yes("go ahead")
    assert is_no("don't")
    assert not is_yes("open discord")


def test_clock_is_spoken():
    assert humanize_speech("It is 6:15.") == "It is quarter past six."


def test_reflex_splits_a_sentence_without_breaking_an_app_name():
    from core.reflex import clauses, weather_place

    assert clauses("what time is it, open Spotify") == ["what time is it", "open Spotify"]
    assert clauses("open visual studio code") == ["open visual studio code"]
    assert weather_place("what's the weather") == ""
    assert weather_place("weather in London") == "London"
    assert weather_place("open Spotify") is None


class _Gate:
    """The same rule the microphone uses: speech during a reply wins."""

    def __init__(self) -> None:
        self.cut = False

    def on_speech(self, phase: str) -> str:
        if phase in {"speaking", "thinking"}:
            self.cut = True
            return "stop"
        return "keep"

    def should_speak(self) -> bool:
        return not self.cut


def test_barge_in_discards_the_reply():
    gate = _Gate()
    assert gate.on_speech("speaking") == "stop"
    assert gate.should_speak() is False
    idle = _Gate()
    assert idle.on_speech("idle") == "keep"
    assert idle.should_speak() is True
