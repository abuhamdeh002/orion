"""The home screen's data and reminder controls."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _client():
    from service.api import app

    return TestClient(app, client=("127.0.0.1", 50000))


def _add(title: str, minutes: int):
    from service.runtime import get_runtime
    from storage.reminder_repository import Reminder

    return get_runtime().reminders.create(Reminder(title=title, due_at=datetime.now(timezone.utc) + timedelta(minutes=minutes)))


def test_today_lists_upcoming_reminders_soonest_first():
    later, sooner = _add("later thing", 90), _add("sooner thing", 5)
    body = _client().get("/today").json()
    titles = [item["title"] for item in body["reminders"]]
    assert titles.index("sooner thing") < titles.index("later thing")
    assert {"system", "memory", "brain", "weather"} <= set(body)
    for item in (later, sooner):
        _client().delete(f"/reminders/{item.id}")


def test_snooze_done_and_delete():
    client = _client()
    item = _add("stretch", 1)
    snoozed = client.post(f"/reminders/{item.id}/snooze", json={"minutes": 10}).json()
    moved = datetime.fromisoformat(snoozed["due_at"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=10) < moved <= timedelta(minutes=11, seconds=5)
    assert client.post(f"/reminders/{item.id}/done").json() == {"ok": True}
    assert item.id not in [entry["id"] for entry in client.get("/reminders").json()]
    other = _add("bins", 30)
    assert client.delete(f"/reminders/{other.id}").json() == {"ok": True}
    assert client.delete(f"/reminders/{other.id}").status_code == 404


def test_voice_levels_are_scaled_and_honest_about_online_voices():
    from service.today import levels_from

    class Mic:
        level = 0.12

    class Speaker:
        def __init__(self, out):
            self.out = out

        def output_level(self):
            return self.out

    reading = levels_from(Mic(), Speaker(0.0), "listening")
    assert reading["mic"] == 1.0 and reading["out"] == 0.0 and reading["phase"] == "listening"
    assert levels_from(None, Speaker(None), "speaking")["out"] is None


def test_read_aloud_uses_the_chosen_voice(monkeypatch):
    seen = {}

    def fake(voice, rate, text):
        seen.update(voice=voice, text=text)
        return b"RIFF....WAVE", "audio/wav"

    monkeypatch.setattr("voice.speech_output.render_sample", fake)
    response = _client().post("/voice/say", json={"text": "Rigel is a blue supergiant."})
    assert response.status_code == 200 and response.headers["content-type"] == "audio/wav"
    assert seen["text"] == "Rigel is a blue supergiant." and seen["voice"]


def test_skills_are_only_ready_when_set_up():
    from skills.registry import load_skills

    class Bare:
        calendar_ics_url = None
        telegram_bot_token = None
        default_city = None

    skills = {item["name"]: item for item in load_skills(["weather", "messaging", "memory", "power", "system_info"], Bare())}
    assert not skills["Calendar"]["ready"] and "ICS link" in skills["Calendar"]["missing"][0]
    assert not skills["Messaging"]["ready"]
    assert [item["name"] for item in load_skills([], Bare())].count("System and Power") == 1

    class Connected(Bare):
        calendar_ics_url = "https://example.invalid/cal.ics"

    assert {item["name"]: item for item in load_skills(["weather"], Connected())}["Calendar"]["ready"]
