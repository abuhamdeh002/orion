"""Decide when a request should be offered tools, and which ones.

A small local model calls a tool for almost any sentence if tools are offered,
and offering tools also routes the turn to a cloud model. So this has to be
precise: whole words only ("day" must not fire on "Monday", "ram" not on
"program", "lock" not on "clock", "play" not on "display").
"""

from __future__ import annotations

import re

_RULES: dict[str, tuple[str, ...]] = {
    "time_date": (
        r"\btime\b",
        r"\bdate\b",
        r"\bwhat day\b",
        r"\bwhich day\b",
        r"\bwhat year\b",
    ),
    "weather": (
        r"\bweather\b",
        r"\btemperature\b",
        r"\bforecast\b",
        r"\brain(?:ing|y)?\b",
        r"\bsnow(?:ing|y)?\b",
        r"\bhumid(?:ity)?\b",
        r"\bumbrella\b",
        r"\bsunny\b",
        r"\bwind(?:y)?\b",
    ),
    "system_info": (
        r"\bbattery\b",
        r"\bcpu\b",
        r"\bram\b",
        r"\bdisk\b",
        r"\bstorage\b",
        r"\bnetwork\b",
        r"\bwi-?fi\b",
        r"\bsystem (?:info|information|status|stats)\b",
        r"\bhow much memory\b",
        r"\bmemory (?:usage|free|left|used)\b",
        r"\buptime\b",
    ),
    "apps": (
        r"\b(?:open|launch|start|close|quit)\s+(?!the door\b)\w+",
        r"\bnotepad\b",
        r"\bcalc(?:ulator)?\b",
        r"\bpaint\b",
        r"\bfile explorer\b",
        r"\bspotify\b",
        r"\bdiscord\b",
        r"\bwhatsapp\b",
        r"\bsteam\b",
    ),
    "browser": (
        r"\bsearch\b",
        r"\bgoogle\b",
        r"\blook up\b",
        r"\bbrowse\b",
        r"\bwebsite\b",
        r"\bweb ?page\b",
    ),
    "reminders": (
        r"\bremind(?:er|ers)?\b",
        r"\btimer\b",
        r"\balarm\b",
        r"\bwake me\b",
    ),
    "music": (
        r"\bmusic\b",
        r"\bsong\b",
        r"\btrack\b",
        r"\bplaylist\b",
        r"\bpause\b",
        r"\bresume\b",
        r"\bskip\b",
        r"\bplay\b",
    ),
    "messaging": (
        r"\be-?mail\b",
        r"\btelegram\b",
        r"\bsend (?:a |an )?(?:message|text|note)\b",
        r"\bmessage (?:him|her|them|my)\b",
    ),
    "vision": (
        r"\bocr\b",
        r"\bimage\b",
        r"\bpicture\b",
        r"\bphoto\b",
    ),
    "computer": (
        r"\bwindows? (?:open|are open)\b",
        r"\bopen windows\b",
        r"\bfocus (?:on )?the\b",
        r"\bclipboard\b",
        r"\bvolume\b",
        r"\b(?:un)?mute\b",
        r"\block (?:the |my )?(?:pc|computer|screen|laptop)\b",
        r"\bon (?:my|the) screen\b",
        r"\bread (?:my |the )?screen\b",
        r"\bclick\b",
    ),
    "memory": (
        r"\bremember\b",
        r"\brecall\b",
        r"\bforget\b",
        r"\bwhat do you know about me\b",
    ),
    "power": (
        r"\bshut ?down\b",
        r"\brestart\b",
        r"\breboot\b",
    ),
    "routines": (
        r"\bgood ?night\b",
        r"\bfocus mode\b",
        r"\bstart focus\b",
        r"\broutine\b",
    ),
    "watch": (r"\bwatch (?:my |the )?(?:\w+ )?(?:folder|downloads|directory)\b",),
}

_COMPILED = {tool: tuple(re.compile(pattern) for pattern in patterns) for tool, patterns in _RULES.items()}


def _normalise(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


def tools_for(user_text: str) -> set[str]:
    """Tool names this sentence plausibly needs. Empty means plain conversation."""
    lowered = _normalise(user_text)
    if not lowered:
        return set()
    return {tool for tool, patterns in _COMPILED.items() if any(pattern.search(lowered) for pattern in patterns)}


def offer_tools(user_text: str) -> bool:
    return bool(tools_for(user_text))
