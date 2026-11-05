"""Instant replies for greetings. A local model should not spend 20 seconds on 'hi'."""

from __future__ import annotations

import re
from datetime import datetime

from app.config import AppConfig

_GREETING = re.compile(
    r"^(?:hey|hi|hello|yo|howdy|good\s+(?:morning|afternoon|evening|night))"
    r"(?:\s+(?:there|orion))?[!.?\s]*$",
    re.IGNORECASE,
)
_WELLBEING = re.compile(
    r"^(?:how are you|how're you|how is it going|how's it going|what's up|whats up|you there|are you there)"
    r"(?:\s+orion)?[!.?\s]*$",
    re.IGNORECASE,
)
_THANKS = re.compile(r"^(?:thanks|thank you|cheers)(?:\s+orion)?[!.?\s]*$", re.IGNORECASE)
_TIME = re.compile(
    r"^(?:what(?:'s| is) the time|what time is it|tell me the time|the time|time"
    r"|(?:do you have|have you got|got) the time)[?.!\s]*$",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"^(?:what(?:'s| is) (?:the date|today(?:'s date)?|the day|the date today|today's date)(?: today)?"
    r"|what (?:day|date) is (?:it|today)(?: today)?|today's date|which day is (?:it|today)|what is the day today)[?.!\s]*$",
    re.IGNORECASE,
)
_HOUR = ["twelve", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"]
_SMALL = [
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty"]


def _minute_words(minute: int) -> str:
    if minute < 10:
        return f"oh {_SMALL[minute - 1]}"
    if minute < 20:
        return _SMALL[minute - 1]
    ten, one = divmod(minute, 10)
    if one == 0:
        return _TENS[ten]
    return f"{_TENS[ten]} {_SMALL[one - 1]}"


def _clock(now: datetime) -> str:
    hour = _HOUR[now.hour % 12]
    minute = now.minute
    if minute == 0:
        return f"{hour} o'clock"
    if minute == 15:
        return f"quarter past {hour}"
    if minute == 30:
        return f"half past {hour}"
    if minute == 45:
        return f"quarter to {_HOUR[(now.hour + 1) % 12]}"
    return f"{hour} {_minute_words(minute)}"


def instant_reply(text: str, config: AppConfig) -> str | None:
    cleaned = " ".join(text.strip().split())
    now = datetime.now()
    if _TIME.match(cleaned):
        return f"It's {_clock(now)}."
    if _DATE.match(cleaned):
        return f"It's {now.strftime('%A')}, {now.strftime('%B')} {now.day}."
    if _WELLBEING.match(cleaned):
        return "I'm well. What do you need?"
    if _THANKS.match(cleaned):
        return "Of course."
    if not _GREETING.match(cleaned):
        return None
    hour = datetime.now().hour
    if hour < 5:
        hello = "Still up"
    elif hour < 12:
        hello = "Good morning"
    elif hour < 18:
        hello = "Good afternoon"
    else:
        hello = "Good evening"
    name = (config.display_name or "").strip()
    who = f", {name}" if name else ""
    return f"{hello}{who}. I'm here."
