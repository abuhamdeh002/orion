"""Turn written replies into the words a person would actually say.

Every voice (Kokoro, Edge, the system voice) speaks this text, so "04:07" is
"four oh seven", "21°C" is "21 degrees", and a date is read as a date.
"""

from __future__ import annotations

import random
import re
from datetime import date

_DIGITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_ONES = ["twelve", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

_ISO_DATETIME = re.compile(r"(\b(?:at|on)\s+)?\b(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}:\d{2})(?::\d{2})?\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})(?::\d{2})?(\s*[AaPp]\.?[Mm]\.?)?(?![\d:])")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF️‍]")
_UNITS = [
    (re.compile(r"(\d)\s*°\s*C\b"), r"\1 degrees Celsius"),
    (re.compile(r"(\d)\s*°\s*F\b"), r"\1 degrees Fahrenheit"),
    (re.compile(r"(\d)\s*°"), r"\1 degrees"),
    (re.compile(r"(\d)\s*km/h\b", re.IGNORECASE), r"\1 kilometres an hour"),
    (re.compile(r"(\d)\s*mph\b", re.IGNORECASE), r"\1 miles an hour"),
    (re.compile(r"(\d)\s*km\b"), r"\1 kilometres"),
    (re.compile(r"(\d)\s*GB\b"), r"\1 gigabytes"),
    (re.compile(r"(\d)\s*MB\b"), r"\1 megabytes"),
    (re.compile(r"(\d)\s*%"), r"\1 percent"),
]
_WORDS = [
    (re.compile(r"\be\.g\.,?", re.IGNORECASE), "for example,"),
    (re.compile(r"\bi\.e\.,?", re.IGNORECASE), "that is,"),
    (re.compile(r"\betc\.", re.IGNORECASE), "and so on."),
    (re.compile(r"\bvs\.?\s", re.IGNORECASE), "versus "),
    (re.compile(r"\bapprox\.\s", re.IGNORECASE), "about "),
    # All-caps names get spelled out letter by letter.
    (re.compile(r"\bORION\b"), "Orion"),
]


def _ordinal(day: int) -> str:
    suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _say_date(year: int, month: int, day: int, today: date | None = None) -> str:
    today = today or date.today()
    try:
        when = date(year, month, day)
    except ValueError:
        return f"{year}-{month:02d}-{day:02d}"
    gap = (when - today).days
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    if gap == -1:
        return "yesterday"
    spoken = f"{_MONTHS[month - 1]} {_ordinal(day)}"
    return spoken if year == today.year else f"{spoken}, {year}"


def say_clock(hour: int, minute: int) -> str:
    name = _ONES[hour % 12]
    if minute == 0:
        return f"{name} o'clock"
    if minute == 15:
        return f"quarter past {name}"
    if minute == 30:
        return f"half past {name}"
    if minute == 45:
        return f"quarter to {_ONES[(hour + 1) % 12]}"
    if minute < 10:
        return f"{name} oh {_DIGITS[minute]}"
    return f"{name} {minute}"


def speakable(text: str, today: date | None = None) -> str:
    """Times, dates, units and abbreviations in the words a person would use."""

    def date_time(match: re.Match[str]) -> str:
        hour, minute = (int(part) for part in match.group(5).split(":"))
        day = _say_date(int(match.group(2)), int(match.group(3)), int(match.group(4)), today)
        lead = "" if day in {"today", "tomorrow", "yesterday"} or not match.group(1) else "on "
        return f"{lead}{day} at {say_clock(hour, minute)}"

    def clock(match: re.Match[str]) -> str:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            return match.group(0)
        meridiem = (match.group(3) or "").strip().lower().replace(".", "")
        if not meridiem:
            return say_clock(hour, minute)
        half = "a.m." if meridiem.startswith("a") else "p.m."
        name = _ONES[hour % 12]
        return f"{name} {half}" if minute == 0 else f"{name} {minute if minute >= 10 else f'oh {_DIGITS[minute]}'} {half}"

    cleaned = _ISO_DATETIME.sub(date_time, text)
    cleaned = _ISO_DATE.sub(lambda m: _say_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), today), cleaned)
    cleaned = _CLOCK.sub(clock, cleaned)
    for pattern, spoken in _UNITS:
        cleaned = pattern.sub(spoken, cleaned)
    for pattern, spoken in _WORDS:
        cleaned = pattern.sub(spoken, cleaned)
    cleaned = _EMOJI.sub("", cleaned)
    cleaned = cleaned.replace("&", " and ").replace("/", " ").replace("|", ", ")
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def pause_after(chunk: str) -> float:
    """Seconds of silence after a spoken piece. People breathe longer after a question than a comma."""
    end = chunk.rstrip()[-1:] if chunk.strip() else ""
    base = {"?": 0.36, "!": 0.3, ".": 0.27, ",": 0.14, ";": 0.2, ":": 0.2}.get(end, 0.12)
    return base + random.uniform(-0.03, 0.05)


ACKNOWLEDGE = ("Yeah?", "Yes?", "Go ahead.")
HOLD_ON = ("One moment.", "Let me check.", "Give me a second.")
