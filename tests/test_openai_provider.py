from __future__ import annotations

import httpx
import pytest

from ai.openai_provider import OpenAIProvider
from app.errors import ProviderConfigurationError, ProviderError, ProviderTimeoutError


def _provider() -> OpenAIProvider:
    return OpenAIProvider(
        api_key="sk-test",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        temperature=0.2,
        max_tokens=128,
        timeout=5.0,
    )


def test_missing_key_raises_configuration_error() -> None:
    provider = OpenAIProvider(None, "gpt-4o-mini", "https://api.openai.com/v1", 0.7, 256, 10)
    ready, message = provider.health()
    assert ready is False
    assert "OPENAI_API_KEY" in message
    with pytest.raises(ProviderConfigurationError):
        provider.chat([{"role": "user", "content": "hi"}])


def test_successful_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" in request.headers
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
            },
        )

    transport = httpx.MockTransport(handler)
    original = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    result = _provider().chat([{"role": "user", "content": "hi"}])
    assert result.text == "Hello"


def test_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(429, json={"error": {"message": "slow down"}}))
    original = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    with pytest.raises(ProviderError, match="rate-limited"):
        _provider().chat([{"role": "user", "content": "hi"}])


def test_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(handler)
    original = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    with pytest.raises(ProviderTimeoutError):
        _provider().chat([{"role": "user", "content": "hi"}])
