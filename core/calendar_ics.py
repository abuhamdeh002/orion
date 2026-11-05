"""Read a calendar from its secret ICS link (Google: Settings > "Secret address in iCal format";
Outlook: Settings > Shared calendars > Publish). Read only: asking about the calendar never
opens anything (it used to start Outlook).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


@dataclass(frozen=True)
class Event:
    title: str
    start: datetime  # local, aware
    all_day: bool = False

    def spoken(self) -> str:
        if self.all_day:
            return f"{self.title} (all day)"
        return f"{self.title} at {self.start.strftime('%I:%M %p').lstrip('0')}"


def _unfold(text: str) -> list[str]:
    """ICS wraps long lines with a leading space."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _when(name: str, value: str) -> tuple[datetime, bool] | None:
    """DTSTART;TZID=Europe/Lisbon:20261105T090000, DTSTART:20261105T060000Z, DTSTART;VALUE=DATE:20261105."""
    value = value.strip()
    try:
        if re.fullmatch(r"\d{8}", value):
            day = datetime.strptime(value, "%Y%m%d")
            return day.replace(tzinfo=datetime.now().astimezone().tzinfo), True
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(), False
        moment = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        zone = re.search(r"TZID=([^;:]+)", name)
        if zone and ZoneInfo is not None:
            try:
                return moment.replace(tzinfo=ZoneInfo(zone.group(1))).astimezone(), False
            except Exception:
                pass
        return moment.astimezone(), False
    except ValueError:
        return None


def _repeats_on(rule: str, start: datetime, day: date) -> bool:
    """Enough of RRULE for everyday calendars: DAILY, WEEKLY (with BYDAY), and UNTIL/COUNT ends."""
    if day < start.date():
        return False
    parts = dict(part.split("=", 1) for part in rule.split(";") if "=" in part)
    until = parts.get("UNTIL")
    if until:
        found = _when("UNTIL", until)
        if found and day > found[0].date():
            return False
    interval = max(1, int(parts.get("INTERVAL", "1") or 1))
    gap = (day - start.date()).days
    frequency = parts.get("FREQ", "")
    if frequency == "DAILY":
        return gap % interval == 0
    if frequency == "WEEKLY":
        days = [_DAYS.index(code[-2:]) for code in parts.get("BYDAY", "").split(",") if code[-2:] in _DAYS] or [start.weekday()]
        return day.weekday() in days and (gap // 7) % interval == 0
    if frequency == "MONTHLY":
        return day.day == start.day
    if frequency == "YEARLY":
        return (day.month, day.day) == (start.month, start.day)
    return False


def events_on(text: str, day: date | None = None) -> list[Event]:
    day = day or datetime.now().astimezone().date()
    events: list[Event] = []
    block: dict[str, tuple[str, str]] = {}
    inside = False
    for line in _unfold(text):
        if line.startswith("BEGIN:VEVENT"):
            inside, block = True, {}
            continue
        if line.startswith("END:VEVENT") and inside:
            inside = False
            if "DTSTART" not in block or block.get("STATUS", ("", ""))[1].upper() == "CANCELLED":
                continue
            found = _when(*block["DTSTART"])
            if found is None:
                continue
            start, all_day = found
            title = block.get("SUMMARY", ("", "Busy"))[1].replace("\\,", ",").replace("\\n", " ").strip() or "Busy"
            if start.date() == day or ("RRULE" in block and _repeats_on(block["RRULE"][1], start, day)):
                moment = datetime.combine(day, start.timetz()) if start.date() != day else start
                events.append(Event(title=title, start=moment, all_day=all_day))
            continue
        if inside and ":" in line:
            name, value = line.split(":", 1)
            key = name.split(";", 1)[0].upper()
            if key in {"DTSTART", "SUMMARY", "RRULE", "STATUS"}:
                block[key] = (name, value)
    return sorted(events, key=lambda event: (not event.all_day, event.start))


def agenda(url: str | None, day: date | None = None, fetch=None) -> str:
    """Today's events as one spoken line, or how to connect a calendar."""
    if not url:
        return "I can't see your calendar yet. Paste its secret ICS link in Settings, under Ambient, and I'll read it from then on."
    try:
        if fetch is None:
            import httpx

            with httpx.Client(timeout=8, follow_redirects=True) as client:
                text = client.get(url).text
        else:
            text = fetch(url)
    except Exception:
        return "I couldn't reach your calendar just now."
    events = events_on(text, day)
    when = "today" if day is None or day == datetime.now().astimezone().date() else day.strftime("on %A")
    if not events:
        return f"Nothing on your calendar {when}."
    spoken = [event.spoken() for event in events[:6]]
    head = f"You have {len(events)} thing{'s' if len(events) != 1 else ''} {when}: "
    return head + (", ".join(spoken[:-1]) + f", and {spoken[-1]}" if len(spoken) > 1 else spoken[0]) + "."
