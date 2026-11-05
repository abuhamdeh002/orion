"""OpenAI-compatible Chat Completions provider with function-calling support."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ai.base_provider import ChatResponse, LLMProvider, TextSink, ToolCallRequest
from app.errors import ProviderConfigurationError, ProviderError, ProviderTimeoutError, RateLimitError

logger = logging.getLogger("orion.ai.openai")


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def health(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "OPENAI_API_KEY is not configured"
        return True, f"OpenAI-compatible ({self.model})"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        if not self.api_key:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is not configured. Add it to your .env file or switch to Ollama."
            )
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The AI provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error talking to the AI provider: {exc}") from exc

        if response.status_code == 401:
            raise ProviderConfigurationError("The AI provider rejected the API key.")
        if response.status_code == 429:
            retry_after = 1.0
            raw = response.headers.get("retry-after")
            if raw:
                try:
                    retry_after = float(raw)
                except ValueError:
                    retry_after = 1.0
            raise RateLimitError("The AI provider rate-limited the request.", retry_after=retry_after)
        if response.status_code >= 400:
            detail = _safe_error_detail(response)
            raise ProviderError(f"AI provider error ({response.status_code}): {detail}")

        try:
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
            text = message.get("content") or ""
            finish = choice.get("finish_reason") or "stop"
            model = payload.get("model") or self.model

            # Parse tool calls if present
            tool_call_list: list[ToolCallRequest] = []
            raw_tool_calls = message.get("tool_calls") or []
            for tc in raw_tool_calls:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    args = {}
                tool_call_list.append(
                    ToolCallRequest(
                        id=tc.get("id", ""),
                        name=tc["function"]["name"],
                        arguments=args,
                    )
                )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("The AI provider returned an unexpected response.") from exc

        return ChatResponse(
            text=text.strip(),
            model=model,
            finish_reason=finish,
            tool_calls=tool_call_list,
        )

    def chat_stream(self, messages: list[dict[str, Any]], on_text: TextSink) -> ChatResponse:
        if not self.api_key:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is not configured. Add it to your .env file or switch to Ollama."
            )
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        pieces: list[str] = []
        model = self.model
        finish = "stop"
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout, read=30)) as client:
                with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=body) as response:
                    if response.status_code >= 400:
                        response.read()
                        _raise_for_status(response)
                    for line in response.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            choice = chunk["choices"][0]
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
                        piece = (choice.get("delta") or {}).get("content") or ""
                        if piece:
                            pieces.append(piece)
                            on_text(piece)
                        model = chunk.get("model") or model
                        finish = choice.get("finish_reason") or finish
        except httpx.TimeoutException as exc:
            if not pieces:
                raise ProviderTimeoutError("The AI provider timed out.") from exc
        except httpx.HTTPError as exc:
            if not pieces:
                raise ProviderError(f"Network error talking to the AI provider: {exc}") from exc
        return ChatResponse(text="".join(pieces).strip(), model=model, finish_reason=finish)


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise ProviderConfigurationError("The AI provider rejected the API key.")
    if response.status_code == 429:
        try:
            retry_after = float(response.headers.get("retry-after") or 1.0)
        except ValueError:
            retry_after = 1.0
        raise RateLimitError("The AI provider rate-limited the request.", retry_after=retry_after)
    if response.status_code >= 400:
        raise ProviderError(f"AI provider error ({response.status_code}): {_safe_error_detail(response)}")


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        return str(error or payload)[:300]
    except ValueError:
        return response.text[:300]
