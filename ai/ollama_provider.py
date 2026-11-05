"""Local Ollama chat provider with tool-calling support. Optional; absence must not crash the app."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ai.base_provider import ChatResponse, LLMProvider, TextSink, ToolCallRequest
from app.errors import ProviderError, ProviderTimeoutError
from core.voice_mode import VOICE_TURN

# Ollama reloads the whole model when num_ctx changes, so every request (and the warmup) uses this.
NUM_CTX = 4096
# Longest a local reply may take before it counts as stuck (the GPU hang waited 2 minutes).
LOCAL_DEADLINE = 30.0

logger = logging.getLogger("orion.ai.ollama")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str,
        temperature: float,
        timeout: float,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.last_timing: dict[str, float] = {}
        self.temperature = temperature
        self.timeout = timeout
        self._client: httpx.Client | None = None

    def health(self) -> tuple[bool, str]:
        url = f"{self.base_url}/api/tags"
        try:
            with httpx.Client(timeout=min(self.timeout, 5.0)) as client:
                response = client.get(url)
            if response.status_code >= 400:
                return False, f"Ollama is not reachable ({response.status_code})"
            return True, f"Ollama ({self.model})"
        except httpx.HTTPError:
            return False, "Ollama is not running or OLLAMA_BASE_URL is wrong"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        url = f"{self.base_url}/api/chat"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": _ollama_messages(messages),
            "stream": False,
            "keep_alive": "2h",
            "options": {
                "temperature": self.temperature,
                "num_ctx": NUM_CTX,
                "num_predict": 120 if VOICE_TURN.get() and not tools else (320 if not tools else 480),
            },
        }
        if tools:
            body["tools"] = tools

        timeout = httpx.Timeout(LOCAL_DEADLINE, connect=5.0)
        client = httpx.Client(timeout=timeout)
        self._client = client
        try:
            response = client.post(url, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Ollama timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "Could not reach Ollama. Start Ollama locally or switch the AI provider."
            ) from exc
        finally:
            self._client = None
            client.close()

        if response.status_code >= 400:
            raise ProviderError(f"Ollama error ({response.status_code}): {response.text[:300]}")
        try:
            payload = response.json()
            self.last_timing = _timing(payload)
            message_data = payload["message"]
            text = message_data.get("content") or ""
            model = payload.get("model") or self.model

            # Parse tool calls if present (Ollama 0.3+ supports tool calling)
            tool_call_list: list[ToolCallRequest] = []
            raw_tool_calls = message_data.get("tool_calls") or []
            for i, tc in enumerate(raw_tool_calls):
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_call_list.append(
                    ToolCallRequest(
                        id=f"ollama_call_{i}",
                        name=fn.get("name", ""),
                        arguments=args if isinstance(args, dict) else {},
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Ollama returned an unexpected response.") from exc
        return ChatResponse(
            text=str(text).strip(),
            model=model,
            tool_calls=tool_call_list,
        )

    def chat_stream(self, messages: list[dict[str, Any]], on_text: TextSink) -> ChatResponse:
        voice = VOICE_TURN.get()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": _ollama_messages(messages),
            "stream": True,
            "keep_alive": "2h",
            "options": {
                "temperature": self.temperature,
                "num_ctx": NUM_CTX,
                "num_predict": 120 if voice else 320,
            },
        }
        client = httpx.Client(timeout=httpx.Timeout(LOCAL_DEADLINE, connect=5.0, read=LOCAL_DEADLINE))
        self._client = client
        pieces: list[str] = []
        model = self.model
        try:
            with client.stream("POST", f"{self.base_url}/api/chat", json=body) as response:
                if response.status_code >= 400:
                    response.read()
                    raise ProviderError(f"Ollama error ({response.status_code}): {response.text[:300]}")
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = (chunk.get("message") or {}).get("content") or ""
                    if piece:
                        pieces.append(piece)
                        on_text(piece)
                    model = chunk.get("model") or model
                    if chunk.get("done"):
                        self.last_timing = _timing(chunk)
                        break
        except httpx.TimeoutException as exc:
            if not pieces:
                raise ProviderTimeoutError("Ollama timed out.") from exc
        except httpx.HTTPError as exc:
            if not pieces:
                raise ProviderError("Could not reach Ollama. Start Ollama locally or switch the AI provider.") from exc
        finally:
            self._client = None
            client.close()
        return ChatResponse(text="".join(pieces).strip(), model=model)

    def abort(self) -> None:
        """Drop the in-flight request so a new thing the person said can win."""
        client = self._client
        if client is None:
            return
        try:
            client.close()
        except Exception:
            logger.debug("Could not close the Ollama request", exc_info=True)


def _timing(payload: dict[str, Any]) -> dict[str, float]:
    """Where the time went, from Ollama's own counters (nanoseconds)."""
    ms = lambda key: round((payload.get(key) or 0) / 1e6)  # noqa: E731
    timing = {
        "load_ms": ms("load_duration"),
        "prompt_tokens": payload.get("prompt_eval_count") or 0,
        "prompt_ms": ms("prompt_eval_duration"),
        "gen_tokens": payload.get("eval_count") or 0,
        "gen_ms": ms("eval_duration"),
    }
    if timing["gen_ms"]:
        timing["tok_per_s"] = round(timing["gen_tokens"] / (timing["gen_ms"] / 1000), 1)
    logger.info("Ollama timing %s", " ".join(f"{key}={value}" for key, value in timing.items()))
    return timing


def _ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ollama wants tool arguments as objects and tool_name on tool results."""
    adapted: list[dict[str, Any]] = []
    for message in messages:
        item = dict(message)
        if item.get("content") is None:
            item["content"] = ""
        calls = item.get("tool_calls")
        if isinstance(calls, list):
            rewritten = []
            for call in calls:
                function = dict(call.get("function") or {})
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments) if arguments else {}
                    except json.JSONDecodeError:
                        arguments = {}
                function["arguments"] = arguments if isinstance(arguments, dict) else {}
                rewritten.append({"function": function})
            item["tool_calls"] = rewritten
        if item.get("role") == "tool" and item.get("name") and "tool_name" not in item:
            item["tool_name"] = item["name"]
        adapted.append(item)
    return adapted
