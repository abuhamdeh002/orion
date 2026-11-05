"""Morning briefing from weather, reminders, and an optional ICS calendar."""

from __future__ import annotations

from datetime import datetime

from service.runtime import OrionRuntime
from tools.weather_tool import WeatherArgs, WeatherTool


def build_briefing(runtime: OrionRuntime, ics_url: str | None = None) -> str:
    parts = [f"Good morning. It is {datetime.now().strftime('%H:%M')}."]
    weather = WeatherTool(runtime.config)
    city = runtime.config.default_city
    if city:
        result = weather.execute(WeatherArgs(location=city))
        if result.ok:
            parts.append(result.message)
    pending = runtime.reminders.list_open()
    if pending:
        parts.append(f"{len(pending)} reminders still open.")
    if ics_url:
        from core.calendar_ics import agenda

        parts.append(agenda(ics_url))
    if runtime.config.focus_mode:
        parts.append("Focus mode is on. I will stay quiet.")
    return " ".join(part for part in parts if part)
