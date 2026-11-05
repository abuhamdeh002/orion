"""Tool gating must be whole-word: these used to fire on substrings."""

from __future__ import annotations

import pytest

from core.intent_router import offer_tools, tools_for

PLAIN_CHAT = [
    "Is today Monday?",
    "I love this program",
    "the clock on the wall is lovely",
    "my display looks great",
    "should I update my CV?",
    "I took the train",
    "happy birthday to my brain",
    "sometimes I wonder",
    "tell me a joke",
    "hello",
    "thanks, that's all",
]

TASKS = [
    ("what time is it", "time_date"),
    ("will it rain tomorrow", "weather"),
    ("how much battery do I have", "system_info"),
    ("open notepad", "apps"),
    ("remind me in 10 minutes to stretch", "reminders"),
    ("pause the music", "music"),
    ("remember my sister is Lina", "memory"),
    ("lock the pc", "computer"),
    ("what's on my clipboard", "computer"),
    ("search for the open-meteo api", "browser"),
    ("shut down the computer", "power"),
    ("goodnight", "routines"),
    ("watch my downloads folder", "watch"),
]


@pytest.mark.parametrize("text", PLAIN_CHAT)
def test_plain_chat_gets_no_tools(text: str) -> None:
    assert tools_for(text) == set(), tools_for(text)


@pytest.mark.parametrize(("text", "tool"), TASKS)
def test_tasks_get_their_tool(text: str, tool: str) -> None:
    assert tool in tools_for(text)
    assert offer_tools(text)
