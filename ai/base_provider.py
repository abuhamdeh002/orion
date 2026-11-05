"""Provider-agnostic LLM interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

TextSink = Callable[[str], None]

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    """A tool invocation requested by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    text: str
    model: str
    finish_reason: str = "stop"
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Return a complete assistant reply. Must not execute tool code."""

    def chat_stream(self, messages: list[dict[str, Any]], on_text: TextSink) -> ChatResponse:
        """Plain-text reply delivered piece by piece. Providers that cannot stream send it whole."""
        response = self.chat(messages, tools=None)
        if response.text:
            on_text(response.text)
        return response

    @abstractmethod
    def health(self) -> tuple[bool, str]:
        """Return (ready, human-readable status)."""
