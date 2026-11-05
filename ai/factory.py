"""Create the LLM provider. Always the router: local Ollama plus any free cloud keys that are set."""

from __future__ import annotations

from ai.base_provider import LLMProvider
from app.config import AppConfig


def create_provider(config: AppConfig) -> LLMProvider:
    from ai.router import ModelRouter

    return ModelRouter(config)
