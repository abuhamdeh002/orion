"""ORION service, router fallback, memory, pairing, and skills."""

from __future__ import annotations

from ai.base_provider import ChatResponse
from ai.router import ModelRouter, QuotaBook
from app.config import AppConfig
from app.errors import RateLimitError
from datetime import datetime, timezone

from evals.harness import score_tool_choice
from service.auth import DeviceStore
from service.runtime import OrionRuntime
from skills.registry import load_skills
from storage.database import Database
from storage.memory_repository import MemoryRepository


def _config() -> AppConfig:
    return AppConfig(
        ai_provider="ollama",
        ai_model="qwen3:8b",
        openai_api_key=None,
        openai_base_url="https://example.invalid",
        ollama_base_url="http://127.0.0.1:9",
        weather_api_key=None,
        weather_base_url="https://example.invalid",
        tts_provider="none",
        stt_provider="none",
        log_level="INFO",
        request_timeout_seconds=5,
        context_max_messages=8,
        temperature=0,
        max_tokens=64,
        speak_replies=False,
        push_to_talk=True,
        continuous_listening=False,
        default_city=None,
        response_style="concise",
        search_url_template="https://example.invalid/?q={query}",
        allowed_apps=[],
        groq_api_key="groq-test",
        gemini_api_key="gemini-test",
    )


def test_router_falls_back_to_local_after_rate_limit(tmp_path) -> None:
    router = ModelRouter(_config(), quota=QuotaBook(tmp_path / "quota.json"))
    calls = []

    def boom(*_args, **_kwargs):
        calls.append("cloud")
        raise RateLimitError("slow down", retry_after=30)

    def local(*_args, **_kwargs):
        calls.append("local")
        return ChatResponse(text="local ok", model="qwen3:8b")

    for _name, provider in router._cloud:
        provider.chat = boom
    router.local.chat = local
    reply = router.chat([{"role": "user", "content": "open notepad and tell me the weather in Lisbon in detail please now"}])
    assert reply.text == "local ok"
    assert calls[0] == "cloud"
    assert calls[-1] == "local"


def test_private_mode_skips_cloud() -> None:
    config = _config()
    config.private_mode = True
    router = ModelRouter(config, quota=QuotaBook())
    router.local.chat = lambda *a, **k: ChatResponse(text="private", model="local")
    for _name, provider in router._cloud:
        provider.chat = lambda *a, **k: (_ for _ in ()).throw(AssertionError("cloud called"))
    assert router.chat([{"role": "user", "content": "hello"}]).text == "private"


def test_memory_remember_recall_forget(tmp_path) -> None:
    database = Database(tmp_path / "mem.db")
    memory = MemoryRepository(database, ollama_base_url="http://127.0.0.1:9")
    memory_id = memory.remember("The desk plant is named Fern.")
    found = memory.recall("plant")
    assert any("Fern" in item["text"] for item in found)
    assert memory.forget(memory_id) is True
    assert memory.list_all() == []
    database.close()


def test_pairing_token_can_be_revoked(tmp_path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    token = store.pair("phone")
    assert store.valid(token) is True
    assert store.revoke(token) is True
    assert store.valid(token) is False


def test_skills_report_readiness() -> None:
    skills = load_skills([
        "weather", "computer", "memory", "power", "app_launcher", "reminders",
        "routines", "browser", "watch", "system_info", "music", "vision", "messaging",
    ])
    by_name = {skill["name"]: skill for skill in skills}
    assert by_name["Briefing"]["ready"] is True
    assert by_name["Routines"]["ready"] is True
    assert by_name["Phone"]["missing"] == ["KDE Connect (kdeconnect-cli)"] or by_name["Phone"]["ready"] is True


def test_pin_blocks_power_without_approval() -> None:
    from core.assistant import Assistant
    from tools.computer_tool import PowerArgs, PowerTool
    from tools.registry import ToolRegistry
    from ai.base_provider import LLMProvider

    class Scripted(LLMProvider):
        name = "script"

        def health(self):
            return True, "ok"

        def chat(self, messages, tools=None):
            if any(message.get("role") == "tool" for message in messages):
                return ChatResponse(text="stopped", model="script")
            return ChatResponse(
                text="",
                model="script",
                tool_calls=[],
            )

    from ai.base_provider import ToolCallRequest

    class Once(Scripted):
        def __init__(self):
            self.done = False

        def chat(self, messages, tools=None):
            if self.done:
                return ChatResponse(text="not run", model="script")
            self.done = True
            return ChatResponse(
                text="",
                model="script",
                tool_calls=[ToolCallRequest(id="1", name="power", arguments={"action": "shutdown"})],
            )

    tools = ToolRegistry()
    tools.register(PowerTool())
    assistant = Assistant(_config(), Once(), tools=tools, confirm=lambda _request: True)
    assistant.pin_check = lambda: False
    reply = assistant.handle_user_message("shutdown the pc")
    assert reply.tool_results
    assert any("PIN" in item["message"] for item in reply.tool_results)


def test_pin_must_match_configured_value() -> None:
    class Dummy:
        config = type("Config", (), {"orion_pin": "1234"})()
        pending_pin = True
        _pin = "0000"

    assert OrionRuntime._pin_ok(Dummy()) is False
    approved = Dummy()
    approved.pending_pin = True
    approved._pin = "1234"
    assert OrionRuntime._pin_ok(approved) is True
    assert OrionRuntime._pin_ok(approved) is False, "an approval is used up after one action"


def test_calendar_reads_today_without_opening_anything() -> None:
    from datetime import date

    from core.calendar_ics import agenda, events_on

    ics = "\n".join([
        "BEGIN:VCALENDAR",
        "BEGIN:VEVENT", "SUMMARY:Standup", "DTSTART:20261105T093000", "END:VEVENT",
        "BEGIN:VEVENT", "SUMMARY:Gym", "DTSTART:20261102T160000Z", "RRULE:FREQ=WEEKLY;BYDAY=MO,TH", "END:VEVENT",
        "BEGIN:VEVENT", "SUMMARY:Holiday", "DTSTART;VALUE=DATE:20261105", "END:VEVENT",
        "BEGIN:VEVENT", "SUMMARY:Cancelled thing", "DTSTART:20261105T120000Z", "STATUS:CANCELLED", "END:VEVENT",
        "BEGIN:VEVENT", "SUMMARY:Tomorrow only", "DTSTART:20261106T080000Z", "END:VEVENT",
        "END:VCALENDAR",
    ])
    thursday = date(2026, 11, 5)
    titles = [event.title for event in events_on(ics, thursday)]
    assert titles == ["Holiday", "Standup", "Gym"]
    line = agenda("https://example.invalid/cal.ics", thursday, fetch=lambda url: ics)
    assert line.split(":", 1)[0] in {"You have 3 things today", "You have 3 things on Thursday"}
    assert "Holiday (all day), Standup at 9:30 AM, and Gym at" in line
    assert "I can't see your calendar yet" in agenda(None)


def test_greeting_does_not_call_the_model() -> None:
    from ai.base_provider import LLMProvider
    from core.assistant import Assistant
    from tools.registry import ToolRegistry

    class Boom(LLMProvider):
        name = "boom"

        def health(self):
            return True, "ok"

        def chat(self, messages, tools=None):
            raise AssertionError("a greeting must not wait on the model")

    reply = Assistant(_config(), Boom(), tools=ToolRegistry()).handle_user_message("hi")
    assert reply.error is False
    assert "I'm here." in reply.text


def test_eval_harness_passes() -> None:
    assert score_tool_choice()["passed"] is True


def test_router_uses_cloud_when_ollama_is_down(tmp_path) -> None:
    router = ModelRouter(_config(), quota=QuotaBook(tmp_path / "quota.json"))
    router._mark_local(False, "down")
    used = []
    for name, provider in router._cloud:
        provider.chat = lambda *a, _n=name, **k: used.append(_n) or ChatResponse(text=f"from {_n}", model=_n)
    router.local.chat = lambda *a, **k: (_ for _ in ()).throw(AssertionError("local called"))
    assert router.chat([{"role": "user", "content": "hello"}]).text == "from groq"
    assert router.last_backend == "groq"


def test_router_falls_back_to_cloud_when_local_chat_fails(tmp_path) -> None:
    from app.errors import ProviderError

    router = ModelRouter(_config(), quota=QuotaBook(tmp_path / "quota.json"))
    router._mark_local(True, "up")

    def broken(*_a, **_k):
        raise ProviderError("Ollama error (500)")

    router.local.chat = broken
    for name, provider in router._cloud:
        provider.chat = lambda *a, _n=name, **k: ChatResponse(text=f"from {_n}", model=_n)
    assert router.chat([{"role": "user", "content": "hello"}]).text == "from groq"


def test_router_explains_when_no_brain_exists(tmp_path) -> None:
    import pytest

    from app.errors import ProviderConfigurationError, ProviderError
    from ai.router import NO_BRAIN

    config = _config()
    config.groq_api_key = None
    config.gemini_api_key = None
    router = ModelRouter(config, quota=QuotaBook(tmp_path / "quota.json"))
    router._mark_local(False, "down")

    def offline(*_a, **_k):
        raise ProviderError("Could not reach Ollama.")

    router.local.chat = offline
    with pytest.raises(ProviderConfigurationError) as caught:
        router.chat([{"role": "user", "content": "hello"}])
    assert str(caught.value) == NO_BRAIN


def test_local_model_gets_only_the_focused_tools(tmp_path) -> None:
    from core.voice_mode import TOOL_FOCUS

    config = _config()
    config.private_mode = True
    router = ModelRouter(config, quota=QuotaBook(tmp_path / "quota.json"))
    seen = {}
    router.local.chat = lambda messages, tools=None: seen.setdefault("tools", tools) or ChatResponse(text="ok", model="x")
    tools = [{"type": "function", "function": {"name": name}} for name in ("weather", "music", "time_date")]
    token = TOOL_FOCUS.set(frozenset({"weather"}))
    try:
        router.chat([{"role": "user", "content": "rain?"}], tools=tools)
    finally:
        TOOL_FOCUS.reset(token)
    assert [tool["function"]["name"] for tool in seen["tools"]] == ["weather"]
