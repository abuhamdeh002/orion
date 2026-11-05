"""Pieces of a sentence that should be answered without a language model."""

from __future__ import annotations

import re
import time

_SPLIT = re.compile(r"\s*,\s*|\s+\band\b\s+", re.IGNORECASE)
_WEATHER = re.compile(
    r"^(?:what(?:'s| is) the weather(?: like)?|how(?:'s| is) the weather|weather)"
    r"(?:\s+(?:in|for|at)\s+(?P<place>.+))?$",
    re.IGNORECASE,
)
_CACHE_SECONDS = 600
_cached: tuple[float, str, str] | None = None


def is_calendar(text: str) -> bool:
    from core.hands import calendar_kind

    return calendar_kind(text) is not None


def clauses(text: str) -> list[str]:
    cleaned = " ".join(text.strip().split())
    parts = _SPLIT.split(cleaned)
    return [part.strip(" .") for part in parts if part.strip(" .")]


def weather_place(text: str) -> str | None:
    cleaned = " ".join(text.strip().rstrip("?.!").split())
    match = _WEATHER.match(cleaned)
    if match is None:
        return None
    return (match.group("place") or "").strip(" .")


def cached_weather(place: str) -> str | None:
    if _cached is None:
        return None
    stored_at, key, line = _cached
    if key != place.lower() or time.time() - stored_at > _CACHE_SECONDS:
        return None
    return line


def store_weather(place: str, line: str) -> None:
    global _cached
    _cached = (time.time(), place.lower(), line)


_STOP_YOU = re.compile(
    r"^(?:how (?:do|can|could) i|how to|what'?s the way to|is there a way to)\s+(?:turn|switch|shut|power)\s+(?:you\s+)?(?:off|down)(?:\s+you)?"
    r"|^how (?:do|can) i (?:stop|mute|quiet|silence|disable|close|quit|exit) you"
    r"|^how (?:do|can) i make you (?:stop|be quiet|shut up)",
    re.IGNORECASE,
)
_ABILITIES = re.compile(
    r"^(?:what (?:can|could) you do|what are you able to do|what do you do|what are your (?:skills|abilities|features|capabilities)|help|what can i (?:ask|say to) you|how can you help(?: me)?)$",
    re.IGNORECASE,
)
_WHO = re.compile(r"^(?:who|what) are you$", re.IGNORECASE)


def about_me(text: str) -> str | None:
    """Questions about ORION himself get the true answer, not a guess. A model said "say standby"."""
    body = " ".join(text.strip().rstrip("?.!").split())
    if _STOP_YOU.match(body):
        return (
            "Say 'Orion, stop' or press Escape and I'll stop talking. 'Goodbye' ends the conversation. "
            "To switch me off completely, press Stop at the bottom of the left rail, or Ctrl+Alt+Esc. Press it again to bring me back."
        )
    if _ABILITIES.match(body):
        return (
            "I can set reminders, timers and alarms, tell you the time and weather, open apps, control your music, "
            "search the web, remember things about you, check your PC, read a photo or your screen, and talk it all through out loud. "
            "Just ask the way you'd ask a person."
        )
    if _WHO.match(body):
        return "I'm Orion, your assistant on this PC. Ask me anything, or say Hey Orion from across the room."
    return None


_WEB = re.compile(
    r"^(?:search|look up|google|find)\s+(?:the\s+)?(?:web|internet|online|google)\s+for\s+(?P<a>.+)$"
    r"|^(?:search|look up|google)\s+(?:for\s+)?(?P<b>.+?)(?:\s+(?:online|on the web|on google|on the internet))?$"
    r"|^(?:do a|run a)\s+(?:web|google|quick)\s+search\s+(?:for|on)\s+(?P<c>.+)$",
    re.IGNORECASE,
)
_IN_APP = re.compile(r"\s+(?:on|in)\s+(?:youtube|spotify|discord|whatsapp|steam|amazon|netflix)$", re.IGNORECASE)


def web_search_query(text: str) -> str | None:
    """'search the web for the best pizza near me' -> 'the best pizza near me'. Searches inside an app are not web searches."""
    body = " ".join(text.strip().rstrip("?.!").split())
    if _IN_APP.search(body):
        return None
    match = _WEB.match(body)
    if not match:
        return None
    query = (match.group("a") or match.group("b") or match.group("c") or "").strip(" .,")
    query = re.sub(r"\s+for me$", "", query, flags=re.IGNORECASE)
    # The time, the date and the weather have their own answers; they are not web searches.
    if re.match(r"^(?:the\s+)?(?:current\s+|today'?s\s+|local\s+)?(?:time|date|day|weather|forecast)\b", query, re.IGNORECASE):
        return None
    return query if len(query) >= 2 else None


_BATTERY = re.compile(
    r"^(?:how much battery|what(?:'s| is) (?:my |the )?battery(?: level| at| percentage)?|battery(?: level| status| percentage)?|how(?:'s| is) (?:my |the )?battery"
    r"|am i charging|is (?:my |the )?(?:laptop|pc|computer|battery) charging|how long (?:will|does) (?:my |the )?battery last)\b",
    re.IGNORECASE,
)


def battery_question(text: str) -> bool:
    return bool(_BATTERY.match(" ".join(text.strip().rstrip("?.!").split())))


def battery_line(data: dict) -> str:
    """The battery reading as a sentence. A model turned 'no battery' into 'the system is not powered'."""
    if not data or data.get("status") == "no battery":
        return "This PC has no battery. It runs straight off the mains."
    if data.get("error"):
        return "I couldn't read the battery just now."
    percent = str(data.get("percent", "")).rstrip("%")
    charging = data.get("is_charging")
    minutes = data.get("time_remaining_mins")
    line = f"You're at {percent} percent"
    if charging:
        return line + ", and charging."
    if isinstance(minutes, int) and minutes > 0:
        hours, rest = divmod(minutes, 60)
        left = f"{hours} hour{'s' if hours != 1 else ''} and {rest} minutes" if hours else f"{rest} minutes"
        return line + f", about {left} left."
    return line + "."
