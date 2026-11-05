"""Quiet local checks: battery and a once-a-day briefing."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from service.briefing import build_briefing
from service.runtime import OrionRuntime


def start(runtime: OrionRuntime) -> threading.Thread:
    def _run() -> None:
        briefed = ""
        warned = False
        while True:
            now = datetime.now()
            if not runtime.config.focus_mode and now.hour == runtime.config.briefing_hour and briefed != now.date().isoformat():
                briefed = now.date().isoformat()
                spoken = build_briefing(runtime, runtime.config.calendar_ics_url)
                runtime.push(spoken, kind="briefing")
                runtime.speaker.speak(spoken, block=False)
            if not warned and not runtime.config.focus_mode:
                warned = _battery_low(runtime)
            time.sleep(30)

    def _reminders() -> None:
        # Every second: a 10-second timer has to go off at 10 seconds, not up to 30 s late.
        while True:
            try:
                runtime.scheduler.tick()
            except Exception:
                logging.getLogger("orion.nudges").warning("Reminder check failed", exc_info=True)
            time.sleep(1)

    threading.Thread(target=_reminders, name="OrionReminders", daemon=True).start()
    thread = threading.Thread(target=_run, name="OrionNudges", daemon=True)
    thread.start()
    return thread


def _battery_low(runtime: OrionRuntime) -> bool:
    try:
        import psutil
    except ImportError:
        return False
    battery = psutil.sensors_battery()
    if battery is None or battery.percent >= 20 or battery.power_plugged:
        return False
    runtime.push(f"Battery is at {int(battery.percent)} percent.", kind="battery", data={"percent": int(battery.percent)})
    return True
