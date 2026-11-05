"""Understand reminder, timer and alarm requests without a model.

"remind me tomorrow at 9 to call the bank", "beep after 10 seconds", "wake me up at 7am",
"set a timer for 15 minutes", "remind me every day at 8 to take my pills".

A small local model got these wrong in real use: it dropped the title, couldn't do seconds,
misread "401 am", and said "Got it" without creating anything. This parser is deterministic
and tested, so the common cases are instant and always right.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "twenty five": 25, "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60,
    "ninety": 90, "couple of": 2, "couple": 2, "few": 3,
}
_AMOUNT = r"(?P<n>\d+(?:\.\d+)?|" + "|".join(sorted((re.escape(w).replace(r"\ ", r"[\s-]") for w in _WORDS), key=len, reverse=True)) + r")"
_UNIT = r"(?P<unit>seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?)"
_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Durations: "in 10 minutes", "after 10 seconds", "for 15 minutes" (timers), "10 minutes from now".
_RELATIVE = re.compile(rf"\b(?:in|after|within|for)\s+(?:about\s+)?{_AMOUNT}\s*{_UNIT}(?:\s+and\s+a\s+half)?\b", re.IGNORECASE)
_FROM_NOW = re.compile(rf"\b{_AMOUNT}\s*{_UNIT}\s+from\s+now\b", re.IGNORECASE)
_HALF_HOUR = re.compile(r"\b(?:in|after|for)\s+(?:half\s+an|a\s+half)\s+hour\b", re.IGNORECASE)
# Clock times: "at 4:01 am", "at 5pm", "at 17:30", "at noon", "4:01 am", "at 401 am".
_CLOCK = re.compile(
    r"\b(?:(?P<at>at|for|by)\s+)?(?:(?P<word>noon|midday|midnight)|(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>a\.?m\.?|p\.?m\.?)|(?P<compact>\d{3,4})\s*(?P<ap2>a\.?m\.?|p\.?m\.?)|(?P<h24>\d{1,2}):(?P<m24>\d{2})|(?P<oclock>\d{1,2})\s+o'?clock|(?<=at\s)(?P<bare>\d{1,2})(?!\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|%|\d)))\b",
    re.IGNORECASE,
)
_DAY = re.compile(
    r"\b(?P<day>today|tonight|tomorrow(?:\s+(?:morning|afternoon|evening|night))?|this\s+(?:morning|afternoon|evening)|(?:on\s+|next\s+|this\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
    re.IGNORECASE,
)
_EVERY = re.compile(r"\b(?P<every>every\s+week\s*day|every\s+work\s*day|(?:on\s+)?week\s*days|(?:on\s+)?work\s*days|every\s*day|daily|every\s+(?:morning|evening|night)|every\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|weekly)\b", re.IGNORECASE)
WORKDAYS = frozenset({0, 1, 2, 3, 4})  # Monday..Friday; core/when.workdays_from() reads the setting
_INTENT = re.compile(r"\b(?:remind|reminder|timer|alarm|alert|beep|wake\s+me|ping\s+me|notify\s+me|nudge\s+me)\b", re.IGNORECASE)
_LIST = re.compile(
    r"^(?:what|which|show|list|read|tell me)?\s*(?:me\s+)?(?:are\s+)?(?:my\s+|the\s+|all\s+)?(?:upcoming\s+)?reminders(?:\s+do\s+i\s+have)?(?:\s+(?:today|for today|left|pending))?\s*\??$"
    r"|^(?:do\s+i\s+have|have\s+i\s+got|are\s+there)\s+any\s+reminders.*$"
    r"|^what\s+(?:reminders|timers)\s+do\s+i\s+have.*$",
    re.IGNORECASE,
)
_FILLER = re.compile(
    r"^(?:(?:hey\s+)?orion[,\s]+|please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+|will\s+you\s+|i\s+want\s+you\s+to\s+|i(?:'d| would)\s+like\s+you\s+to\s+|just\s+|go\s+ahead\s+and\s+)+",
    re.IGNORECASE,
)
_LEAD = re.compile(
    r"^(?:(?:set|create|add|make|start|put)\s+(?:me\s+)?(?:a|an|another|the)?\s*(?:quick\s+)?(?:reminder|timer|alarm|alert|beep)s?(?:\s+(?:for\s+me|to\s+remind\s+me))?|remind\s+me|ping\s+me|nudge\s+me|notify\s+me|alert\s+me|beep\s+me|wake\s+me(?:\s+up)?)\b",
    re.IGNORECASE,
)
_GLUE = re.compile(r"^(?:[\s,;:.-]|to\b|that\b|about\b|of\b|for\b|so\s+(?:that\s+)?i\b|i\s+need\s+to\b|i\s+have\s+to\b|i\s+should\b|i\s+must\b|and\b|with\b|please\b)+", re.IGNORECASE)
_TAIL = re.compile(r"(?:[\s,;:.!?-]|\bplease\b|\bthanks\b|\bthank\s+you\b|\bok(?:ay)?\b|\bfor\s+me\b)+$", re.IGNORECASE)
_BEEPS = {"", "beep", "a beep", "beep sound", "a beep sound", "sound", "a sound", "alarm", "an alarm", "timer", "a timer", "reminder", "a reminder", "alert"}


@dataclass(frozen=True)
class QuickReminder:
    title: str
    due: datetime  # local, timezone-aware
    recurrence: str = "none"  # none | daily | weekly
    kind: str = "reminder"  # reminder | timer | alarm

    def spoken(self, now: datetime | None = None) -> str:
        """'in 10 seconds', 'at 4:01', 'tomorrow at 9:00', 'every day at 8:00', 'on Friday at 3:00 PM'."""
        now = now or datetime.now().astimezone()
        gap = (self.due - now).total_seconds()
        clock = self.due.strftime("%I:%M %p").lstrip("0")
        if self.recurrence == "daily":
            return f"every day at {clock}"
        if self.recurrence == "weekly":
            return f"every {self.due.strftime('%A')} at {clock}"
        if self.recurrence == "weekdays":
            return f"every weekday at {clock}"
        if gap < 90:
            return f"in {max(1, round(gap))} seconds"
        if gap < 3600:
            minutes = round(gap / 60)
            return f"in {minutes} minute{'s' if minutes != 1 else ''}"
        if self.due.date() == now.date():
            return f"at {clock}"
        if self.due.date() == (now + timedelta(days=1)).date():
            return f"tomorrow at {clock}"
        return f"on {self.due.strftime('%A')} at {clock}"

    def reply(self, now: datetime | None = None) -> str:
        when = self.spoken(now)
        if self.kind == "timer":
            return f"Timer set. I'll beep {when}."
        if self.kind == "alarm":
            return f"Alarm set {when}."
        return f"Okay, I'll remind you to {self.title} {when}."


def _amount(raw: str) -> float | None:
    raw = re.sub(r"[\s-]+", " ", raw.lower()).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return float(raw)
    return float(_WORDS[raw]) if raw in _WORDS else None


def _seconds(unit: str) -> int:
    unit = unit.lower()
    if unit.startswith("s"):
        return 1
    if unit.startswith("h"):
        return 3600
    if unit.startswith("d"):
        return 86400
    return 60


def _clock(match: re.Match[str]) -> tuple[int, int, bool] | None:
    """Hour, minute, and whether am/pm (or 24-hour) made it unambiguous."""
    if match.group("word"):
        return (0, 0, True) if match.group("word").lower() == "midnight" else (12, 0, True)
    ap = match.group("ap") or match.group("ap2")
    if match.group("compact"):
        digits = match.group("compact")
        hour, minute = int(digits[:-2]), int(digits[-2:])
    elif match.group("h"):
        hour, minute = int(match.group("h")), int(match.group("m") or 0)
    elif match.group("h24"):
        hour, minute = int(match.group("h24")), int(match.group("m24"))
        if hour > 23 or minute > 59:
            return None
        return hour, minute, hour >= 13 or hour == 0 or match.group("h24").startswith("0")
    elif match.group("oclock"):
        hour, minute = int(match.group("oclock")), 0
    elif match.group("bare"):
        hour, minute = int(match.group("bare")), 0
    else:
        return None
    if not 0 <= minute <= 59 or not 0 <= hour <= 23:
        return None
    if ap:
        if hour > 12 or hour == 0:
            return None
        pm = ap.lower().startswith("p")
        hour = (hour % 12) + (12 if pm else 0)
        return hour, minute, True
    return hour, minute, hour >= 13


def _day_offset(day: str, now: datetime) -> tuple[int, str | None]:
    """Days from today, and a part of day that sets the hour when none is given."""
    day = re.sub(r"\s+", " ", day.lower()).strip()
    part = None
    for word in ("morning", "afternoon", "evening", "night"):
        if day.endswith(word):
            part = word
    if day == "tonight":
        return 0, "night"
    if day.startswith("this "):
        return 0, part
    if day == "today":
        return 0, None
    if day.startswith("tomorrow"):
        return 1, part
    name = day.split()[-1]
    target = _DAYS.index(name)
    ahead = (target - now.weekday()) % 7
    if ahead == 0 or day.startswith("next "):
        ahead = ahead or 7
    return ahead, None


_PART_HOUR = {"morning": 9, "afternoon": 15, "evening": 19, "night": 21}


def workdays_from(setting: str | None) -> frozenset[int]:
    """'sun,mon,tue,wed,thu' -> {6, 0, 1, 2, 3}. Unknown or empty keeps Monday to Friday."""
    names = [part.strip().lower()[:3] for part in (setting or "").split(",") if part.strip()]
    days = {[day[:3] for day in _DAYS].index(name) for name in names if name in [day[:3] for day in _DAYS]}
    return frozenset(days) or WORKDAYS


def next_workday(moment: datetime, workdays: frozenset[int] = WORKDAYS) -> datetime:
    while moment.weekday() not in workdays:
        moment += timedelta(days=1)
    return moment


def parse_reminder(text: str, now: datetime | None = None, workdays: frozenset[int] = WORKDAYS) -> QuickReminder | None:
    """A reminder, timer or alarm request with a time in it, or None for anything else."""
    now = now or datetime.now().astimezone()
    body = " ".join(text.strip().split())
    if not body or len(body) > 220 or not _INTENT.search(body):
        return None
    lowered = body.lower()
    kind = "timer" if re.search(r"\b(?:timer|beep)\b", lowered) else "alarm" if re.search(r"\b(?:alarm|wake\s+me)\b", lowered) else "reminder"
    spans: list[tuple[int, int]] = []
    due: datetime | None = None
    recurrence = "none"

    half = _HALF_HOUR.search(body)
    relative = _RELATIVE.search(body) or _FROM_NOW.search(body)
    if half:
        due = now + timedelta(minutes=30)
        spans.append(half.span())
    elif relative:
        amount = _amount(relative.group("n") or "")
        unit = relative.group("unit") or "minutes"
        if amount is None or amount <= 0:
            return None
        seconds = amount * _seconds(unit)
        if "and a half" in relative.group(0).lower():
            seconds += _seconds(unit) / 2
        due = now + timedelta(seconds=seconds)
        spans.append(relative.span())
    else:
        every = _EVERY.search(body)
        day_match = _DAY.search(body)
        clock_match = None
        for candidate in _CLOCK.finditer(body):
            if _clock(candidate) is not None:
                clock_match = candidate
                break
        if clock_match is None and day_match is None and every is None:
            return None
        offset, part = (0, None)
        if day_match:
            offset, part = _day_offset(day_match.group("day"), now)
            spans.append(day_match.span())
        if every:
            word = every.group("every").lower()
            spans.append(every.span())
            if re.search(r"week\s*day|work\s*day", word):
                recurrence = "weekdays"
            elif any(name in word for name in _DAYS) or word == "weekly":
                recurrence = "weekly"
                name = next((name for name in _DAYS if name in word), None)
                if name:
                    offset = (_DAYS.index(name) - now.weekday()) % 7
            else:
                recurrence = "daily"
                for key in _PART_HOUR:
                    if key in word:
                        part = key
        if clock_match:
            hour, minute, certain = _clock(clock_match)  # type: ignore[misc]
            spans.append(clock_match.span())
            if not certain:
                # "at 7" in the evening, or "tonight at 8", means pm.
                if part in {"evening", "night", "afternoon"} and hour < 12:
                    hour += 12
        elif part:
            hour, minute, certain = _PART_HOUR[part], 0, True
        else:
            hour, minute, certain = 9, 0, True  # "tomorrow" alone: nine in the morning
        base = now + timedelta(days=offset)
        due = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if not certain and offset == 0 and due <= now and hour < 12 and due + timedelta(hours=12) > now:
            due += timedelta(hours=12)  # "at 5" at 3 pm means 5 pm
        if due <= now:
            due += timedelta(days=1 if recurrence != "weekly" else 7)
        if recurrence == "weekdays":
            due = next_workday(due, workdays)

    # The title is whatever is left once the time and the "remind me" words are gone.
    rest = body
    for start, end in sorted(spans, reverse=True):
        rest = rest[:start] + " " + rest[end:]
    rest = " ".join(rest.split())
    rest = _FILLER.sub("", rest)
    rest = _LEAD.sub("", rest, count=1)
    rest = _GLUE.sub("", rest)
    rest = _TAIL.sub("", rest)
    rest = re.sub(r"\s+(?:to|at|on|for|in)$", "", rest, flags=re.IGNORECASE).strip(" ,.;:-")
    if rest.lower() in _BEEPS or re.fullmatch(r"(?:a\s+)?beep(?:\s+sound)?", rest, re.IGNORECASE):
        title = {"timer": "Timer", "alarm": "Wake up" if "wake" in lowered else "Alarm"}.get(kind, "Reminder")
        if kind == "reminder":
            kind = "timer"
            title = "Timer"
    else:
        title = rest[0].lower() + rest[1:] if rest[:2].isupper() is False else rest
        if kind == "timer":
            kind = "reminder"
    if kind == "alarm" and title not in {"Alarm", "Wake up"}:
        kind = "reminder"
    return QuickReminder(title=title, due=due, recurrence=recurrence, kind=kind)


def wants_reminder_list(text: str) -> bool:
    return bool(_LIST.match(" ".join(text.strip().rstrip("?.!").split()) + ("?" if text.strip().endswith("?") else "")))



@dataclass(frozen=True)
class ReminderCommand:
    kind: str  # cancel | move | snooze | next
    what: str = ""  # words that pick the reminder ("" = the only one, or the obvious one)
    every: bool = False  # cancel all
    when: str = ""  # move: the new time, as said
    minutes: int = 10  # snooze


_THING = r"(?:reminders?|timers?|alarms?)"
# Everything only when they say so: "cancel the alarm" once cleared every reminder.
_CANCEL_ALL = re.compile(r"^(?:please\s+)?(?:(?:cancel|delete|remove|clear|drop)\s+(?:all\s+(?:of\s+)?(?:my|the)\s+|all\s+(?:my\s+|the\s+)?)(?:reminders|timers|alarms)|clear\s+(?:my\s+|the\s+)?(?:reminders|timers|alarms))$", re.IGNORECASE)
_CANCEL = re.compile(rf"^(?:please\s+)?(?:cancel|delete|remove|drop|forget about|stop|turn off)\s+(?:my\s+|the\s+|that\s+)?(?P<thing>{_THING})(?:\s+(?:to|about|for|called|named))?\s*(?P<what>.*?)$", re.IGNORECASE)
_CANCEL_NAMED = re.compile(rf"^(?:please\s+)?(?:cancel|delete|remove|drop|stop)\s+(?:my\s+|the\s+)?(?P<what>.+?)\s+{_THING}$", re.IGNORECASE)
# No "set" here: "set an alarm for 7 am" is a new alarm, not a move (it once moved the stretch reminder).
_MOVE_NAMED = re.compile(rf"^(?:please\s+)?(?:move|change|reschedule|push|shift)\s+(?:my\s+|the\s+)?(?P<what>.+?)\s+{_THING}\s+(?:to|until|till|for)\s+(?P<when>.+)$", re.IGNORECASE)
_MOVE = re.compile(rf"^(?:please\s+)?(?:move|change|reschedule|push|shift)\s+(?:my\s+|the\s+)?{_THING}\s+(?:to|about|for)\s+(?P<what>.+?)\s+(?:to|until|till)\s+(?P<when>.+)$", re.IGNORECASE)
_SNOOZE = re.compile(r"^(?:please\s+)?(?:snooze|remind me again)(?:\s+(?:it|that|this|the reminder|my reminder|the alarm|the timer))?(?:\s+(?:for|in|by))?\s*(?P<amount>.*?)$", re.IGNORECASE)
_NEXT = re.compile(rf"^(?:how long (?:until|till|before)|when(?:'s| is)|what(?:'s| is)|what time is)\s+(?:my\s+|the\s+)?next\s+{_THING}", re.IGNORECASE)


def reminder_command(text: str) -> ReminderCommand | None:
    """Managing reminders that exist: 'cancel my reminder to stretch', 'move the bank reminder to 10',
    'snooze for 5 minutes', 'when's my next reminder?'. A model said 'no reminder found' to all of these."""
    body = " ".join(text.strip().rstrip("?.!").split())
    if not body:
        return None
    if _NEXT.match(body):
        return ReminderCommand("next")
    if _CANCEL_ALL.match(body):
        return ReminderCommand("cancel", every=True)
    match = _MOVE.match(body) or _MOVE_NAMED.match(body)
    if match:
        return ReminderCommand("move", what=match.group("what").strip(), when=match.group("when").strip())
    match = _CANCEL.match(body)
    if match:
        what = match.group("what").strip()
        thing = match.group("thing").lower().rstrip("s")
        # "cancel the alarm" means the one called Alarm; "stop the timer" the one called Timer.
        return ReminderCommand("cancel", what=what or (thing if thing in {"alarm", "timer"} else ""))
    match = _CANCEL_NAMED.match(body)
    if match:
        return ReminderCommand("cancel", what=match.group("what").strip())
    match = _SNOOZE.match(body)
    if match:
        amount = match.group("amount").strip()
        minutes = 10
        if amount:
            found = parse_reminder(f"remind me in {amount} to x")
            if found is None:
                return None
            minutes = max(1, round((found.due - datetime.now().astimezone()).total_seconds() / 60))
        return ReminderCommand("snooze", minutes=minutes)
    return None


_SKIP = {"my", "the", "a", "an", "to", "about", "for", "reminder", "reminders", "that", "one"}


def pick(reminders: list, what: str):
    """The reminder these words mean: the best word match, or the only one when nothing is named."""
    words = {word for word in re.findall(r"[a-z0-9']+", what.lower()) if word not in _SKIP}
    if not words:
        return reminders[0] if len(reminders) == 1 else None
    best, score = None, 0
    for reminder in reminders:
        title = set(re.findall(r"[a-z0-9']+", reminder.title.lower()))
        overlap = len(words & title) + sum(0.5 for word in words for part in title if len(word) > 3 and word != part and (word in part or part in word))
        if overlap > score:
            best, score = reminder, overlap
    return best


def new_time(when: str, original: datetime, now: datetime | None = None, workdays: frozenset[int] = WORKDAYS) -> datetime | None:
    """'10', 'to 10am', 'tomorrow at 9', 'in an hour'. Without a day, the reminder keeps its own day."""
    now = now or datetime.now().astimezone()
    spoken = when.strip()
    if re.fullmatch(r"\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?", spoken, re.IGNORECASE):
        spoken = f"at {spoken}"
    found = parse_reminder(f"remind me {spoken} to x", now=now, workdays=workdays)
    if found is None:
        return None
    if not _DAY.search(spoken) and not re.search(r"\b(?:in|after)\b", spoken, re.IGNORECASE):
        hour = found.due.hour
        if not re.search(r"[ap]\.?m\b|\d:\d\d|noon|midnight", spoken, re.IGNORECASE):
            # "10" with no am/pm means the 10 nearest the old time: 9 AM moves to 10 AM, not 10 PM.
            base = original.astimezone().hour
            hour = min((hour % 12, hour % 12 + 12), key=lambda candidate: abs(candidate - base))
        kept = original.astimezone().replace(hour=hour, minute=found.due.minute, second=0, microsecond=0)
        if kept > now:
            return kept
    return found.due
