"""Model router: the local model when it can do the job, free cloud models when it can't.

Order of preference:
* PRIVATE_MODE: local only, always.
* Tool turns and long requests: cloud first (Groq, then Gemini), local as fallback.
  Cloud models choose tools far better than a small local model.
* Plain chat: local first, cloud as fallback when Ollama is down or fails.

Ollama's health is cached for a few seconds so a dead Ollama costs nothing per
turn, instead of a timeout every time.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from ai.base_provider import ChatResponse, LLMProvider, TextSink
from ai.doctor import FROZE, WAKING, LocalDoctor, looks_stuck
from ai.ollama_provider import OllamaProvider
from ai.openai_provider import OpenAIProvider
from app.config import AppConfig
from app.errors import ProviderConfigurationError, ProviderError, RateLimitError
from app.paths import app_data_dir
from core.voice_mode import TOOL_FOCUS

logger = logging.getLogger("orion.ai.router")

_DAILY_CAP = {"groq": 1000, "gemini": 1500, "openai": 100_000}
_HEALTH_TTL = 15.0
_CLOUD_TIMEOUT = 20.0

NO_BRAIN = (
    "No AI model is available. Start Ollama, or add a free GROQ_API_KEY or GEMINI_API_KEY "
    "to your .env file and restart."
)


CLOUD_BUSY = "Ollama is offline and the cloud models didn't answer. Try again in a moment, or start Ollama."


def _unreachable(exc: Exception) -> bool:
    text = str(exc).lower()
    return "reach" in text or "timed out" in text


class QuotaBook:
    """Per-provider daily request counts and rate-limit cooldowns, persisted across restarts."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "quota.json")
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data), encoding="utf-8")
        except OSError:
            logger.debug("Could not save quota book", exc_info=True)

    def allow(self, name: str) -> bool:
        day = time.strftime("%Y-%m-%d")
        with self._lock:
            bucket = self._data.get(name) or {}
            if bucket.get("day") != day:
                return True
            return int(bucket.get("count") or 0) < _DAILY_CAP.get(name, 1000)

    def mark(self, name: str) -> None:
        day = time.strftime("%Y-%m-%d")
        with self._lock:
            bucket = self._data.get(name) or {}
            count = int(bucket.get("count") or 0) if bucket.get("day") == day else 0
            self._data[name] = {**bucket, "day": day, "count": count + 1}
            self._save()

    def block_until(self, name: str, seconds: float) -> None:
        with self._lock:
            self._data.setdefault(name, {})["blocked_until"] = time.time() + max(0.0, seconds)
            self._save()

    def cooled_down(self, name: str) -> bool:
        with self._lock:
            until = float((self._data.get(name) or {}).get("blocked_until") or 0)
        return time.time() >= until


def cloud_providers(config: AppConfig) -> list[tuple[str, OpenAIProvider]]:
    timeout = min(config.request_timeout_seconds, _CLOUD_TIMEOUT)
    chain: list[tuple[str, OpenAIProvider]] = []
    for name, key, model, base in (
        ("groq", config.groq_api_key, config.groq_model, config.groq_base_url),
        ("gemini", config.gemini_api_key, config.gemini_model, config.gemini_base_url),
        ("openai", config.openai_api_key, config.ai_model if config.ai_provider == "openai" else "gpt-4o-mini", config.openai_base_url),
    ):
        if key:
            chain.append((
                name,
                OpenAIProvider(
                    api_key=key,
                    model=model,
                    base_url=base,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    timeout=timeout,
                ),
            ))
    return chain


class ModelRouter(LLMProvider):
    name = "router"

    def __init__(self, config: AppConfig, quota: QuotaBook | None = None) -> None:
        self.config = config
        self.quota = quota or QuotaBook()
        self.local = OllamaProvider(
            model=config.ai_model if config.ai_provider == "ollama" else (config.ollama_model or config.ai_model),
            base_url=config.ollama_base_url,
            temperature=config.temperature,
            timeout=config.request_timeout_seconds,
        )
        self._cloud = cloud_providers(config)
        self.last_backend = "local"
        self._health: tuple[float, bool, str] = (0.0, False, "")
        self._health_lock = threading.Lock()
        self.doctor = LocalDoctor(self.local.base_url, self.local.model, mark=self._mark_local)

    # -- health -------------------------------------------------------------------------------

    def local_health(self, fresh: bool = False) -> tuple[bool, str]:
        with self._health_lock:
            stamp, ready, message = self._health
            if not fresh and time.monotonic() - stamp < _HEALTH_TTL and stamp:
                return ready, message
        ready, message = self.local.health()
        with self._health_lock:
            self._health = (time.monotonic(), ready, message)
        return ready, message

    def _mark_local(self, ready: bool, message: str) -> None:
        with self._health_lock:
            self._health = (time.monotonic(), ready, message)

    def cloud_names(self) -> list[str]:
        return [name for name, _provider in self._cloud]

    def health(self) -> tuple[bool, str]:
        local_ready, message = self.local_health()
        cloud = ", ".join(self.cloud_names()) or "none"
        mode = "private" if self.config.private_mode else "hybrid"
        ready = local_ready or (bool(self._cloud) and not self.config.private_mode)
        return ready, f"{message}; cloud={cloud}; mode={mode}"

    def backends(self) -> dict[str, Any]:
        local_ready, message = self.local_health()
        return {
            "local": {"ready": local_ready, "detail": message},
            "cloud": self.cloud_names(),
            "private": self.config.private_mode,
            "last": self.last_backend,
        }

    # -- chat ---------------------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        if self.config.private_mode:
            return self._local(messages, tools)
        local_ready, _ = self.local_health()
        if self._wants_cloud(messages, tools) or not local_ready:
            response = self._try_cloud(messages, tools)
            if response is not None:
                return response
            # Health can be stale, so the local model still gets its chance.
            try:
                return self._local(messages, tools)
            except ProviderError as exc:
                if str(exc) in (FROZE, WAKING):
                    raise
                if _unreachable(exc):
                    raise ProviderConfigurationError(NO_BRAIN if not self._cloud else CLOUD_BUSY) from exc
                raise
        try:
            return self._local(messages, tools)
        except ProviderError as exc:
            logger.info("Local model failed (%s); trying cloud", exc)
            response = self._try_cloud(messages, tools)
            if response is None:
                raise
            return response

    def chat_stream(self, messages: list[dict[str, Any]], on_text: TextSink) -> ChatResponse:
        """Same backend choice as chat(). Falls back only if nothing was streamed yet."""
        sent = {"any": False}

        def sink(piece: str) -> None:
            sent["any"] = True
            on_text(piece)

        def local() -> ChatResponse:
            self.last_backend = "local"
            self._await_brain()
            try:
                return self.local.chat_stream(messages, sink)
            except ProviderError as exc:
                if not sent["any"]:
                    self._diagnose(exc)
                raise

        def cloud() -> ChatResponse | None:
            for name, provider in self._cloud:
                if sent["any"] or not self.quota.allow(name) or not self.quota.cooled_down(name):
                    continue
                try:
                    response = provider.chat_stream(messages, sink)
                except RateLimitError as exc:
                    self.quota.block_until(name, exc.retry_after)
                    continue
                except ProviderError as exc:
                    logger.info("%s failed: %s", name, exc)
                    continue
                self.quota.mark(name)
                self.last_backend = name
                return response
            return None

        if self.config.private_mode:
            return local()
        local_ready, _ = self.local_health()
        if self._wants_cloud(messages, None) or not local_ready:
            response = cloud()
            if response is not None:
                return response
            try:
                return local()
            except ProviderError as exc:
                if str(exc) in (FROZE, WAKING):
                    raise
                if _unreachable(exc):
                    raise ProviderConfigurationError(NO_BRAIN if not self._cloud else CLOUD_BUSY) from exc
                raise
        try:
            return local()
        except ProviderError:
            if sent["any"]:
                raise
            response = cloud()
            if response is None:
                raise
            return response

    def abort(self) -> None:
        self.local.abort()

    def _local(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> ChatResponse:
        self.last_backend = "local"
        self._await_brain()
        try:
            return self.local.chat(messages, tools=_focus(tools))
        except ProviderError as exc:
            self._diagnose(exc)
            raise

    def _await_brain(self) -> None:
        """While the model wakes or heals, wait for it instead of failing straight away."""
        if not self.doctor.wait_ready():
            raise ProviderConfigurationError(WAKING)

    def _diagnose(self, exc: ProviderError) -> None:
        """A hang or a server error: heal in the background and say so plainly."""
        if _unreachable(exc):
            self._mark_local(False, str(exc))
        if looks_stuck(exc) and not isinstance(exc, ProviderConfigurationError):
            self.doctor.heal()
            raise ProviderError(FROZE) from exc

    def _try_cloud(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> ChatResponse | None:
        for name, provider in self._cloud:
            if not self.quota.allow(name) or not self.quota.cooled_down(name):
                continue
            try:
                response = provider.chat(messages, tools=tools)
            except RateLimitError as exc:
                logger.info("%s rate limited for %.1fs", name, exc.retry_after)
                self.quota.block_until(name, exc.retry_after)
                continue
            except ProviderError as exc:
                logger.info("%s failed: %s", name, exc)
                continue
            self.quota.mark(name)
            self.last_backend = name
            return response
        return None

    @staticmethod
    def _wants_cloud(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> bool:
        if tools:
            return True
        latest = ""
        for message in reversed(messages):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                latest = message["content"]
                break
        return len(latest.split()) > 40


def _focus(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """A small local model gets only the tools this sentence is about."""
    if not tools:
        return tools
    wanted = TOOL_FOCUS.get()
    if not wanted:
        return tools
    narrowed = [tool for tool in tools if tool.get("function", {}).get("name") in wanted]
    return narrowed or tools
