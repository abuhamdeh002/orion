"""Reflexes run before the model and some have side effects. These used to misfire."""

from __future__ import annotations

from core.command_parser import parse_command
from core.hands import calendar_kind, claims_unchecked_action, spoken_math, wants_project, wants_reopen


def test_reminders_about_meetings_are_not_calendar_reads():
    assert calendar_kind("remind me about the meeting at 3") is None
    assert calendar_kind("create a reminder for the project meeting") is None
    assert calendar_kind("the meeting went well") is None
    assert calendar_kind("what's on my calendar today") == "read"
    assert calendar_kind("do I have any meetings tomorrow?") == "read"
    assert calendar_kind("connect my google calendar") == "connect"


def test_only_real_folder_requests_make_folders():
    assert not wants_project("create a reminder for the project meeting")
    assert not wants_project("make sure the project folder is backed up")
    assert wants_project("create a new project called Atlas")
    assert wants_project("make a folder named receipts")


def test_reopen_needs_the_whole_request():
    assert not wants_reopen("show me how it works")
    assert not wants_reopen("open it up for discussion")
    assert wants_reopen("open it again")
    assert wants_reopen("show the folder")


def test_phone_numbers_and_resolutions_are_not_sums():
    assert spoken_math("call 555-1234") is None
    assert spoken_math("my screen is 1920x1080") is None
    assert spoken_math("12 x 12") == "That's 144."
    assert spoken_math("what's 7*6") == "That's 42."


def test_open_it_again_is_not_an_app_called_again():
    assert parse_command("open it again") is None
    assert parse_command("open spotify again") == {"action": "open", "name": "spotify"}


def test_lie_filter_only_catches_first_person_claims():
    assert claims_unchecked_action("I've opened Notepad for you.", None)
    assert not claims_unchecked_action("Creating a budget starts with tracking spending.", None)
    assert not claims_unchecked_action("Press the Start Menu and type Notepad.", None)
