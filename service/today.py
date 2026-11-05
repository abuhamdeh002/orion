"""The home screen's data, reminder controls, and live voice levels.

/today            one call for the home screen: reminders, weather, the PC, memory, the brain
/reminders        upcoming reminders; snooze, complete or delete one
/voice/levels     a stream of microphone and voice loudness, so the constellation moves with real sound
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from service.runtime import get_runtime

router = APIRouter()
_weather_lock = threading.Lock()
_weather_fetching = False


def _reminder(item) -> dict:
    return {"id": item.id, "title": item.title, "due_at": item.due_at.isoformat(), "recurrence": item.recurrence}


def _weather(runtime) -> dict | None:
    """Cached weather for the saved city. Never blocks the page: a miss starts a fetch in the background."""
    global _weather_fetching
    from core.reflex import cached_weather, store_weather

    city = runtime.config.default_city
    if not city:
        return None
    line = cached_weather(city)
    if line:
        return {"city": city, "line": line}
    with _weather_lock:
        if _weather_fetching:
            return {"city": city, "line": None}
        _weather_fetching = True

    def fetch() -> None:
        global _weather_fetching
        try:
            from tools.weather_tool import WeatherArgs, WeatherTool

            result = WeatherTool(runtime.config).execute(WeatherArgs(location=city))
            if result.ok:
                store_weather(city, result.message)
        except Exception:
            pass
        finally:
            with _weather_lock:
                _weather_fetching = False

    threading.Thread(target=fetch, name="OrionWeather", daemon=True).start()
    return {"city": city, "line": None}


def _system() -> dict:
    try:
        import psutil
    except ImportError:
        return {}
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    return {
        "cpu": round(psutil.cpu_percent(interval=None)),
        "memory": round(psutil.virtual_memory().percent),
        "battery": None if battery is None else {"percent": round(battery.percent), "charging": bool(battery.power_plugged)},
    }


@router.get("/today")
def today() -> dict:
    runtime = get_runtime()
    reminders = sorted(runtime.reminders.list_open(), key=lambda item: item.due_at)
    memories = runtime.memory.list_all()
    facts = [item for item in memories if item.get("kind") != "instruction"]
    health = runtime.assistant.provider.health() if hasattr(runtime.assistant.provider, "health") else (True, "")
    return {
        "name": runtime.config.display_name,
        "reminders": [_reminder(item) for item in reminders[:6]],
        "reminder_count": len(reminders),
        "weather": _weather(runtime),
        "system": _system(),
        "memory": {"count": len(facts), "latest": facts[0]["text"] if facts else None},
        # Only a brain that answers is named; "Ollama is not running..." doesn't belong on the home screen.
        "brain": health[1].split(";")[0].strip() if health and health[0] else "",
    }


@router.get("/reminders")
def reminders() -> list[dict]:
    runtime = get_runtime()
    return [_reminder(item) for item in sorted(runtime.reminders.list_open(), key=lambda item: item.due_at)]


class SnoozeIn(BaseModel):
    minutes: int = Field(default=10, ge=1, le=24 * 60)


def _find(reminder_id: str):
    item = get_runtime().reminders.get(reminder_id)
    if item is None:
        raise HTTPException(status_code=404, detail="That reminder is gone.")
    return item


@router.post("/reminders/{reminder_id}/snooze")
def snooze(reminder_id: str, body: SnoozeIn) -> dict:
    item = _find(reminder_id)
    item.due_at = max(item.due_at, datetime.now(timezone.utc)) + timedelta(minutes=body.minutes)
    item.status = "pending"
    get_runtime().reminders.update(item)
    return _reminder(item)


@router.post("/reminders/{reminder_id}/done")
def done(reminder_id: str) -> dict:
    item = _find(reminder_id)
    item.status = "completed"
    item.fired_at = datetime.now(timezone.utc)
    get_runtime().reminders.update(item)
    return {"ok": True}


@router.delete("/reminders/{reminder_id}")
def delete(reminder_id: str) -> dict:
    _find(reminder_id)
    get_runtime().reminders.delete(reminder_id)
    return {"ok": True}


@router.get("/voice/levels")
async def voice_levels(request: Request) -> StreamingResponse:
    """About 15 readings a second of how loud the room (mic) and ORION's own voice (out) are, 0..1."""
    runtime = get_runtime()

    async def generate():
        while not await request.is_disconnected():
            reading = runtime.voice.levels()
            yield f"data: {json.dumps(reading)}\n\n"
            await asyncio.sleep(0.066)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


def levels_from(mic, speaker, phase: str) -> dict:
    """Loudness scaled to 0..1 for drawing. None for 'out' means speaking, but not measurable (an online voice)."""
    raw_mic = float(getattr(mic, "level", 0.0) or 0.0) if mic is not None else 0.0
    out = speaker.output_level() if hasattr(speaker, "output_level") else None
    scale = lambda value: min(1.0, (value / 0.12) ** 0.7) if value else 0.0  # noqa: E731
    return {
        "mic": round(scale(raw_mic), 3),
        "out": None if out is None else round(scale(out), 3),
        "phase": phase,
        "t": round(time.time(), 2),
    }


class SayIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/voice/say")
def say(body: SayIn):
    """A reply read aloud in the browser, in the chosen voice (works on a paired phone too)."""
    from fastapi.responses import Response

    from service.api import _current_voice
    from voice.speech_output import render_sample

    runtime = get_runtime()
    try:
        audio, media = render_sample(_current_voice(), runtime.speaker.rate, body.text)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"I can't read that aloud right now ({exc}).") from exc
    return Response(content=audio, media_type=media, headers={"Cache-Control": "no-store"})
