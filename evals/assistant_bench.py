"""Real-world benchmark: everyday requests through ORION's full pipeline and the real model.

    python -m evals.assistant_bench                 # all cases, prints a table
    python -m evals.assistant_bench --json out.json # also save results for before/after

Runs in a throwaway data folder, so your history, reminders and memories are untouched.
Tools with side effects (apps, music, power, messages, browser, computer, screen) are
recorded instead of run: the check is that ORION *chose* the right action.
Each case checks the outcome (was a reminder really created, at the right time?),
not just the wording.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["ORION_DATA_DIR"] = tempfile.mkdtemp(prefix="orion-bench-")

from tools.base_tool import ToolResult  # noqa: E402

SIDE_EFFECTS = {"apps", "app_launcher", "browser", "computer", "music", "messaging", "power", "vision", "watch", "routines"}


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def wrap(self, tool) -> None:
        name = tool.name

        def execute(arguments):
            data = arguments.model_dump() if hasattr(arguments, "model_dump") else dict(arguments)
            self.calls.append((name, data))
            return ToolResult(ok=True, message=f"Done: {name} {json.dumps(data)}")

        tool.execute = execute

    def used(self, name: str, **expected) -> bool:
        for called, data in self.calls:
            if called != name:
                continue
            text = json.dumps(data).lower()
            if all(str(value).lower() in text for value in expected.values()):
                return True
        return False


def _reminders(runtime):
    return runtime.reminders.list_open()


def _due_in(reminder) -> float:
    return (reminder.due_at - datetime.now(timezone.utc)).total_seconds()


def _next_local(hour: int, minute: int, days: int = 0) -> datetime:
    now = datetime.now().astimezone()
    at = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days)
    if days == 0 and at <= now:
        at += timedelta(days=1)
    return at


def _has_reminder(runtime, words: str, seconds: tuple[float, float] | None = None, at: datetime | None = None) -> bool:
    for reminder in _reminders(runtime):
        if not all(word in reminder.title.lower() for word in words.split()):
            continue
        if seconds and not (seconds[0] <= _due_in(reminder) <= seconds[1]):
            continue
        if at and abs((reminder.due_at - at.astimezone(timezone.utc)).total_seconds()) > 90:
            continue
        return True
    return False


def _says(reply: str, *patterns: str) -> bool:
    return all(re.search(pattern, reply, re.IGNORECASE) for pattern in patterns)


def _not_says(reply: str, *patterns: str) -> bool:
    return not any(re.search(pattern, reply, re.IGNORECASE) for pattern in patterns)


# (request, check(reply, recorder, runtime) -> bool, what a right answer is)
CASES = [
    ("what time is it", lambda r, rec, rt: bool(re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d{1,2})\b", r)), "says the time"),
    ("what's the date today", lambda r, rec, rt: _says(r, datetime.now().strftime("%B")) or _says(r, datetime.now().strftime("%A")), "says today's date"),
    ("Remind me in 10 minutes to drink water", lambda r, rec, rt: _has_reminder(rt, "water", (540, 660)), "creates the reminder, 10 min"),
    ("set a reminder, beep sound after 10 seconds", lambda r, rec, rt: any(0 < _due_in(x) <= 60 for x in _reminders(rt)), "creates a reminder ~10 s out"),
    ("remind me at 4:01 am to stretch", lambda r, rec, rt: _has_reminder(rt, "stretch", at=_next_local(4, 1)), "creates it for the next 04:01"),
    ("remind me tomorrow at 9 to call the bank", lambda r, rec, rt: _has_reminder(rt, "bank", at=_next_local(9, 0, days=1)), "creates it for tomorrow 09:00"),
    ("what reminders do I have?", lambda r, rec, rt: _says(r, "water") and _says(r, "bank|stretch"), "lists the real reminders"),
    ("I want you to open my calculator.", lambda r, rec, rt: rec.used("apps", app="calc") or rec.used("apps", name="calc") or rec.used("app_launcher", app_name="calc"), "opens the calculator"),
    ("can you open notepad please", lambda r, rec, rt: rec.used("apps", x="notepad") or rec.used("app_launcher", x="notepad"), "opens notepad"),
    ("what's 15% of 240", lambda r, rec, rt: _says(r, r"\b36\b"), "36"),
    ("convert 5 miles to kilometers", lambda r, rec, rt: _says(r, r"\b8(\.0[0-9])?\b"), "about 8 km"),
    ("how much battery do I have", lambda r, rec, rt: _says(r, r"\d+\s*(%|percent)|plugged|no battery|desktop|mains|charging|(?:doesn't|does not|don't) (?:have|detect|see) a battery|battery (?:isn't|is not|wasn't) (?:detected|found|available)"), "reports the battery"),
    ("what's the weather like", lambda r, rec, rt: _says(r, r"degree|°|rain|cloud|sun|clear|wind") or (not rt.config.default_city and _says(r, r"which city")), "real weather, or asks for the city once"),
    ("pause the music", lambda r, rec, rt: rec.used("music") or rec.used("apps", x="pause"), "pauses music"),
    ("search the web for the best pizza near me", lambda r, rec, rt: rec.used("browser"), "opens a web search"),
    ("My name is Nick", lambda r, rec, rt: _says(r, "nick"), "acknowledges the name"),
    ("what's my name?", lambda r, rec, rt: _says(r, r"\bnick\b"), "Nick"),
    ("remember that my sister is called Lina", lambda r, rec, rt: any("lina" in m["text"].lower() for m in rt.memory.list_all()), "saves the fact"),
    ("who is my sister?", lambda r, rec, rt: _says(r, r"\blina\b"), "Lina"),
    ("How can I turn you off?", lambda r, rec, rt: _says(r, r"stop|goodbye|kill|ctrl") and _not_says(r, "standby"), "real ways to stop ORION"),
    ("what can you do?", lambda r, rec, rt: _says(r, "remind|weather|open|music") and len(r) < 700, "accurate, short"),
    ("In one sentence, why is the sky blue?", lambda r, rec, rt: _says(r, "scatter") and r.count(".") <= 2, "one correct sentence"),
    ("tell me a short joke", lambda r, rec, rt: 10 < len(r) < 400, "a joke, short"),
    ("From now on, say sir at the end of everything you say.", lambda r, rec, rt: len(r) > 0, "agrees"),
    ("how are you today?", lambda r, rec, rt: _says(r, r"sir[.!?]?\s*$"), "follows the standing instruction"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="save results here")
    parser.add_argument("--only", help="run cases whose text contains this")
    args = parser.parse_args()

    from service.runtime import OrionRuntime

    runtime = OrionRuntime()
    recorder = Recorder()
    for name in SIDE_EFFECTS:
        tool = runtime.tools.get(name)
        if tool is not None:
            recorder.wrap(tool)
    provider = runtime.assistant.provider
    print(f"Brain: {provider.health()[1] if hasattr(provider, 'health') else provider}")
    rows = []
    for text, check, expected in CASES:
        if args.only and args.only.lower() not in text.lower():
            continue
        recorder.calls.clear()
        local = getattr(provider, "local", None)
        if local is not None:
            local.last_timing = {}
        started = time.monotonic()
        try:
            reply = runtime.assistant.handle_user_message(text, source="bench", confirm=lambda request: True).text or ""
        except Exception as exc:  # a crash is a failed case, not a crashed benchmark
            reply = f"[error] {exc}"
        seconds = time.monotonic() - started
        try:
            ok = bool(check(reply, recorder, runtime))
        except Exception:
            ok = False
        timing = dict(getattr(local, "last_timing", {}) or {})
        tools = [call[0] for call in recorder.calls]
        rows.append({"request": text, "ok": ok, "seconds": round(seconds, 2), "reply": reply, "tools": tools, "expected": expected, "ollama": timing})
        mark = "PASS" if ok else "FAIL"
        detail = (
            f"prompt {timing.get('prompt_tokens')} tok in {timing.get('prompt_ms')} ms, {timing.get('gen_tokens')} tok at {timing.get('tok_per_s')}/s"
            if timing else "no model call"
        )
        print(f"{mark}  {seconds:5.1f}s  {text}\n        -> {reply[:150]!r}  tools={tools}  [{detail}]", flush=True)

    passed = sum(row["ok"] for row in rows)
    times = sorted(row["seconds"] for row in rows)
    median = times[len(times) // 2] if times else 0
    print(f"\n{passed}/{len(rows)} correct · median {median:.1f}s · slowest {max(times, default=0):.1f}s · total {sum(times):.0f}s")
    if args.json:
        Path(args.json).write_text(json.dumps({"passed": passed, "total": len(rows), "median_s": median, "rows": rows}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
