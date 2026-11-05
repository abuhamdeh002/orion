"""Real streaming: providers deliver text as it arrives, and the assistant passes it on per turn."""

from __future__ import annotations

import json

import httpx

from ai.base_provider import ChatResponse
from ai.ollama_provider import OllamaProvider
from ai.openai_provider import OpenAIProvider
from core.assistant import Assistant
from tests.conftest import FakeProvider
from tools.registry import ToolRegistry


def _patch_client(monkeypatch, handler) -> None:
    real = httpx.Client

    def make(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", make)


def test_ollama_streams_pieces(monkeypatch) -> None:
    lines = [{"message": {"content": "Good "}}, {"message": {"content": "evening."}}, {"done": True, "model": "m"}]
    body = "\n".join(json.dumps(line) for line in lines)
    _patch_client(monkeypatch, lambda request: httpx.Response(200, text=body))
    seen: list[str] = []
    reply = OllamaProvider("m", "http://ollama.test", 0, 5).chat_stream([{"role": "user", "content": "hi"}], seen.append)
    assert seen == ["Good ", "evening."]
    assert reply.text == "Good evening."


def test_openai_compatible_streams_sse(monkeypatch) -> None:
    events = [
        {"choices": [{"delta": {"content": "Hel"}}]},
        {"choices": [{"delta": {"content": "lo."}, "finish_reason": "stop"}]},
    ]
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
    _patch_client(monkeypatch, lambda request: httpx.Response(200, text=body))
    seen: list[str] = []
    provider = OpenAIProvider("key", "m", "https://cloud.test/v1", 0, 64, 5)
    reply = provider.chat_stream([{"role": "user", "content": "hi"}], seen.append)
    assert seen == ["Hel", "lo."]
    assert reply.text == "Hello."


def test_assistant_streams_to_the_turn_that_asked(app_config) -> None:
    class Streamer(FakeProvider):
        def chat_stream(self, messages, on_text):
            for piece in ("One ", "two."):
                on_text(piece)
            return ChatResponse(text="One two.", model="fake")

    assistant = Assistant(app_config, Streamer(), tools=ToolRegistry())
    pieces: list[str] = []
    reply = assistant.handle_user_message("tell me a story", source="ws-1", on_token=pieces.append)
    assert pieces == ["One ", "two."]
    assert reply.text == "One two."
    # A turn without a listener is not streamed to anyone.
    other: list[str] = []
    assistant.on_token = None
    assistant.handle_user_message("another story", source="web")
    assert other == []


def test_every_ollama_request_uses_one_context_size(monkeypatch) -> None:
    """Ollama reloads the model when num_ctx changes; voice and typed turns must not trigger that."""
    from ai.ollama_provider import NUM_CTX, OllamaProvider
    from core.voice_mode import VOICE_TURN

    sent = []

    class Response:
        status_code = 200

        def json(self):
            return {"message": {"content": "ok"}, "model": "m"}

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout

        def post(self, url, json):
            sent.append(json["options"]["num_ctx"])
            return Response()

        def close(self):
            pass

    monkeypatch.setattr("ai.ollama_provider.httpx.Client", Client)
    provider = OllamaProvider(model="m", base_url="http://x", temperature=0.2, timeout=30)
    provider.chat([{"role": "user", "content": "hi"}])
    token = VOICE_TURN.set(True)
    try:
        provider.chat([{"role": "user", "content": "hi"}])
    finally:
        VOICE_TURN.reset(token)
    assert sent == [NUM_CTX, NUM_CTX]


def test_a_slow_model_is_not_called_offline(app_config) -> None:
    from core.assistant import Assistant

    reply = Assistant._error_reply(object.__new__(Assistant), "Ollama timed out.", None)
    assert "too slow" in reply.text and "offline" not in reply.text
