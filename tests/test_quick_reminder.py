"""Everyday requests that must be right every time, without depending on a small model.

Each case here comes from real use where the model got it wrong: it said "Got it" without
creating a reminder, couldn't do seconds, misread "401 am", called the user "Sir" after
"my name is Nick", and invented "say standby" for how to turn ORION off.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.hands import claims_unchecked_action
from core.personal import personal_statement, plain, with_suffix
from core.reflex import about_me, web_search_query
from core.when import parse_reminder, wants_reminder_list

# Thursday 5 November 2026, 04:30 local.
NOW = datetime(2026, 11, 5, 4, 30).astimezone()


def _at(days: int, hour: int, minute: int = 0) -> datetime:
    return (NOW + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)


@pytest.mark.parametrize(
    ("said", "title", "due"),
    [
        ("Remind me in 10 minutes to drink water", "drink water", NOW + timedelta(minutes=10)),
        ("set a reminder, beep sound after 10 seconds", "Timer", NOW + timedelta(seconds=10)),
        ("remind me at 4:01 am to stretch", "stretch", _at(1, 4, 1)),
        ("remind me at 401 am to stretch", "stretch", _at(1, 4, 1)),
        ("remind me tomorrow at 9 to call the bank", "call the bank", _at(1, 9)),
        ("remind me to call mom at 5pm", "call mom", _at(0, 17)),
        ("remind me to call mom at 5", "call mom", _at(0, 5) if _at(0, 5) > NOW else _at(0, 17)),
        ("set a timer for 15 minutes", "Timer", NOW + timedelta(minutes=15)),
        ("wake me up at 7am", "Wake up", _at(0, 7)),
        ("remind me in half an hour to check the oven", "check the oven", NOW + timedelta(minutes=30)),
        ("remind me in an hour and a half to leave", "leave", NOW + timedelta(minutes=90)),
        ("please remind me in two hours about the meeting", "the meeting", NOW + timedelta(hours=2)),
        ("I want you to remind me tonight at 8 to take the bins out", "take the bins out", _at(0, 20)),
        ("remind me on friday at 3pm to pay rent", "pay rent", _at(1, 15)),
        ("remind me tomorrow morning to buy milk", "buy milk", _at(1, 9)),
        ("remind me 20 minutes from now to stretch", "stretch", NOW + timedelta(minutes=20)),
    ],
)
def test_reminders_are_understood(said, title, due):
    found = parse_reminder(said, now=NOW)
    assert found is not None, said
    assert found.title == title
    assert abs((found.due - due).total_seconds()) < 2, (found.due, due)


def test_every_day_is_a_daily_reminder():
    found = parse_reminder("remind me every day at 8 to take my pills", now=NOW)
    assert found.recurrence == "daily" and found.title == "take my pills" and found.due == _at(0, 8)


@pytest.mark.parametrize(
    "said",
    ["remind me about the meeting", "what reminders do I have", "tell me a joke", "set a timer", "what time is it in Tokyo", "how was your day"],
)
def test_no_time_no_reminder(said):
    assert parse_reminder(said, now=NOW) is None


def test_replies_say_when_in_plain_words():
    assert parse_reminder("beep after 10 seconds", now=NOW).reply(NOW) == "Timer set. I'll beep in 10 seconds."
    assert parse_reminder("remind me tomorrow at 9 to call the bank", now=NOW).reply(NOW) == "Okay, I'll remind you to call the bank tomorrow at 9:00 AM."


@pytest.mark.parametrize("said", ["what reminders do I have?", "list my reminders", "do I have any reminders", "show me my reminders"])
def test_reminder_lists(said):
    assert wants_reminder_list(said)


@pytest.mark.parametrize(
    ("said", "kind", "value"),
    [
        ("My name is Nick", "name", "Nick"),
        ("call me Nick.", "name", "Nick"),
        ("I live in London", "city", "London"),
        ("From now on, say sir at the end of everything you say.", "suffix", "sir"),
        ("Say sir, after everything you say.", "suffix", "sir"),
        ("stop saying sir", "stop_suffix", "sir"),
        ("from now on keep your answers really short", "instruction", "from now on keep your answers really short."),
    ],
)
def test_personal_statements_take_effect(said, kind, value):
    found = personal_statement(said)
    assert found is not None and found.kind == kind and found.value == value


@pytest.mark.parametrize("said", ["my name is not important", "I'm in a meeting", "call me back later please now"])
def test_not_every_sentence_is_a_setting(said):
    found = personal_statement(said)
    assert found is None or found.kind != "name"


def test_suffix_is_added_once():
    assert with_suffix("It's four fourteen.", "sir") == "It's four fourteen, sir."
    assert with_suffix("Good evening, sir.", "sir") == "Good evening, sir."


def test_politeness_is_not_in_the_way():
    assert plain("I want you to open my calculator.") == "open calculator."
    assert plain("can you open notepad please") == "open notepad"


def test_true_answers_about_orion():
    assert "Ctrl+Alt+Esc" in about_me("How can I turn you off?") and "standby" not in about_me("How can I turn you off?")
    assert "remind" in about_me("what can you do")


@pytest.mark.parametrize(
    ("said", "query"),
    [("search the web for the best pizza near me", "the best pizza near me"), ("google cheap flights to Rome", "cheap flights to Rome"), ("look up the current time", None), ("search lofi on youtube", None)],
)
def test_web_searches(said, query):
    assert web_search_query(said) == query


@pytest.mark.parametrize(
    "said",
    ["I've set a reminder to beep after ten seconds.", "Got it. I'll remind you at 4:01 AM.", "Reminder set for 4:01 AM.", "Your calculator is open now.", "I've opened Notepad for you."],
)
def test_untrue_claims_are_caught(said):
    assert claims_unchecked_action(said, None)


def test_a_real_tool_result_is_not_a_lie():
    assert not claims_unchecked_action("Reminder set.", [{"tool": "reminders", "ok": True}])


def _assistant(app_config, tmp_path, provider):
    from core.assistant import Assistant
    from storage.database import Database
    from storage.memory_repository import MemoryRepository
    from storage.reminder_repository import ReminderRepository
    from tools.registry import ToolRegistry
    from tools.reminder_tool import ReminderTool

    database = Database(tmp_path / "t.db")
    repository = ReminderRepository(database)
    tools = ToolRegistry()
    tools.register(ReminderTool(repository))
    assistant = Assistant(app_config, provider, tools=tools)
    assistant.memory = MemoryRepository(database, "http://127.0.0.1:9")
    return assistant, repository


def test_reminders_are_created_without_the_model(app_config, tmp_path, monkeypatch):
    from tests.conftest import FakeProvider

    monkeypatch.setattr("app.config.settings_path", lambda: tmp_path / "settings.json")
    assistant, repository = _assistant(app_config, tmp_path, FakeProvider(fail=AssertionError("the model must not be asked")))
    reply = assistant.handle_user_message("set a reminder, beep sound after 10 seconds")
    assert reply.text == "Timer set. I'll beep in 10 seconds."
    reply = assistant.handle_user_message("remind me tomorrow at 9 to call the bank")
    assert reply.text.startswith("Okay, I'll remind you to call the bank tomorrow at 9:00")
    assert sorted(item.title for item in repository.list_open()) == ["Timer", "call the bank"]
    listing = assistant.handle_user_message("what reminders do I have?").text
    assert "You have 2 reminders" in listing and "call the bank tomorrow at 9:00 AM" in listing


def test_name_and_reply_ending_stick(app_config, tmp_path, monkeypatch):
    from tests.conftest import FakeProvider

    monkeypatch.setattr("app.config.settings_path", lambda: tmp_path / "settings.json")
    assistant, _ = _assistant(app_config, tmp_path, FakeProvider(text="I'm well, thank you."))
    assert assistant.handle_user_message("My name is Nick").text == "Nice to meet you, Nick. I'll call you Nick."
    assert assistant.config.display_name == "Nick"
    assistant.handle_user_message("From now on, say sir at the end of everything you say.")
    assert assistant.handle_user_message("what time is it").text.endswith(", sir.")
    assert assistant.handle_user_message("tell me how you are doing today").text == "I'm well, thank you, sir."


def test_standing_instructions_reach_the_model(app_config, tmp_path, monkeypatch):
    from tests.conftest import FakeProvider

    monkeypatch.setattr("app.config.settings_path", lambda: tmp_path / "settings.json")
    provider = FakeProvider(text="Sure.")
    assistant, _ = _assistant(app_config, tmp_path, provider)
    assistant.handle_user_message("from now on keep your answers really short")
    assistant.handle_user_message("explain what a black hole is")
    note = [message["content"] for message in provider.calls[-1] if message["role"] == "system"][-1]
    assert "keep your answers really short" in note and "Now:" in note


def test_a_claimed_action_gets_the_tools_and_one_more_try(app_config, tmp_path, monkeypatch):
    """'Got it, I'll remind you' with no tool call: ask again with the reminders tool."""
    from ai.base_provider import ChatResponse, ToolCallRequest
    from tests.conftest import FakeProvider

    monkeypatch.setattr("app.config.settings_path", lambda: tmp_path / "settings.json")
    provider = FakeProvider(responses=[
        ChatResponse(text="Got it. I'll remind you about the dentist.", model="fake"),
        ChatResponse(text="", model="fake", tool_calls=[ToolCallRequest(id="1", name="reminders", arguments={"action": "create", "title": "dentist", "due_in_minutes": 60})]),
        ChatResponse(text="Done: the dentist reminder is set for an hour from now.", model="fake"),
    ])
    assistant, repository = _assistant(app_config, tmp_path, provider)
    reply = assistant.handle_user_message("don't let me forget about the dentist")
    assert [item.title for item in repository.list_open()] == ["dentist"]
    assert reply.text.startswith("Done")
    assert len(provider.calls) == 3



@pytest.mark.parametrize("said", ["how much battery do I have", "what's my battery level", "am I charging", "battery"])
def test_battery_questions(said):
    from core.reflex import battery_question

    assert battery_question(said)


def test_battery_lines_are_true():
    from core.reflex import battery_line

    assert battery_line({"status": "no battery"}) == "This PC has no battery. It runs straight off the mains."
    assert battery_line({"percent": "82%", "is_charging": True}) == "You're at 82 percent, and charging."
    assert battery_line({"percent": "40%", "is_charging": False, "time_remaining_mins": 95}) == "You're at 40 percent, about 1 hour and 35 minutes left."


def test_weekday_alarms_repeat_on_workdays_only():
    found = parse_reminder("set an alarm for 7 am every weekday", now=NOW)
    assert found.recurrence == "weekdays" and found.title == "Alarm" and found.reply(NOW) == "Alarm set every weekday at 7:00 AM."
    from core.when import workdays_from

    sunday_to_thursday = workdays_from("sun,mon,tue,wed,thu")
    friday_now = datetime(2026, 11, 6, 8, 0).astimezone()  # a Friday, after 7
    assert parse_reminder("wake me up at 7am on weekdays", now=friday_now, workdays=sunday_to_thursday).due.strftime("%A") == "Sunday"


@pytest.mark.parametrize(
    ("said", "kind", "what"),
    [
        ("cancel my reminder to stretch", "cancel", "stretch"),
        ("delete the stretch reminder", "cancel", "stretch"),
        ("move my bank reminder to 10", "move", "bank"),
        ("move the reminder to call the bank to tomorrow at 11", "move", "call the bank"),
        ("how long until my next reminder?", "next", ""),
        ("snooze for 5 minutes", "snooze", ""),
    ],
)
def test_managing_reminders_is_understood(said, kind, what):
    from core.when import reminder_command

    found = reminder_command(said)
    assert found is not None and found.kind == kind and found.what == what


def test_managing_real_reminders_without_the_model(app_config, tmp_path, monkeypatch):
    from tests.conftest import FakeProvider

    monkeypatch.setattr("app.config.settings_path", lambda: tmp_path / "settings.json")
    assistant, repository = _assistant(app_config, tmp_path, FakeProvider(fail=AssertionError("the model must not be asked")))
    assistant.handle_user_message("remind me in 2 hours to stretch")
    assistant.handle_user_message("remind me tomorrow at 9 to call the bank")
    assert assistant.handle_user_message("how long until my next reminder?").text.startswith("Your next reminder is stretch")
    moved = assistant.handle_user_message("move my bank reminder to 10").text
    assert moved.startswith("Moved: call the bank, now tomorrow at 10:00 AM")
    assert assistant.handle_user_message("cancel my reminder to stretch").text.startswith("Cancelled: stretch")
    assert [item.title for item in repository.list_open()] == ["call the bank"]
    missing = assistant.handle_user_message("cancel my reminder about the dentist").text
    assert missing.startswith("I don't see a reminder about the dentist. You have: call the bank")
    assert assistant.handle_user_message("snooze").text == "There's nothing to snooze right now."
    assert assistant.handle_user_message("clear all my reminders").text == "Done. I've cleared all 1 reminder."


def test_one_message_can_hold_several_settings():
    from core.personal import personal_statements

    found = personal_statements("My nickname is Sam, and call me Sir at the end of every sentence you make")
    assert [(item.kind, item.value) for item in found] == [("name", "Sam"), ("suffix", "Sir")]
    assert [(item.kind, item.value) for item in personal_statements("I live in Lisbon, Portugal")] == [("city", "Lisbon")]


def test_what_was_remembered_takes_effect_once(app_config, tmp_path, monkeypatch):
    """'I live in Lisbon, Portugal' sat in memory while the weather asked for a city, and he kept saying 'Sir'."""
    from tests.conftest import FakeProvider

    monkeypatch.setattr("app.config.settings_path", lambda: tmp_path / "settings.json")
    assistant, _ = _assistant(app_config, tmp_path, FakeProvider())
    assistant.config.display_name = "Sir"
    assistant.memory.remember("I live in Lisbon, Portugal", kind="auto")
    assistant.memory.remember("My nickname is Sam, and call me Sir at the end of every sentence you make", kind="fact")
    adopted = assistant.adopt_memories()
    assert sorted(adopted) == ["city=Lisbon", "name=Sam", "suffix=Sir"]
    assert (assistant.config.display_name, assistant.config.default_city, assistant.config.reply_suffix) == ("Sam", "Lisbon", "Sir")
    assert assistant.adopt_memories() == []  # already in effect: nothing changes a second time
    assistant.config.display_name = "Nick"  # a name chosen in Settings is never overridden
    assert assistant.adopt_memories() == []


@pytest.mark.parametrize("said", ["set an alarm for 7 am every weekday", "set a timer for 10 minutes", "set a reminder for 5pm to call mom"])
def test_setting_something_new_is_never_a_move(said):
    from core.when import reminder_command

    assert reminder_command(said) is None
    assert parse_reminder(said, now=NOW) is not None


def test_cancelling_one_never_cancels_all(app_config, tmp_path, monkeypatch):
    """'cancel the alarm' once cleared every reminder."""
    from core.when import reminder_command
    from tests.conftest import FakeProvider

    assert reminder_command("cancel the alarm").every is False
    assert reminder_command("cancel all reminders").every and reminder_command("clear my reminders").every
    monkeypatch.setattr("app.config.settings_path", lambda: tmp_path / "settings.json")
    assistant, repository = _assistant(app_config, tmp_path, FakeProvider(fail=AssertionError("no model")))
    assistant.handle_user_message("remind me in 2 hours to stretch")
    assistant.handle_user_message("set an alarm for 7 am every weekday")
    assert assistant.handle_user_message("cancel the alarm").text.startswith("Cancelled: Alarm")
    assert [item.title for item in repository.list_open()] == ["stretch"]
