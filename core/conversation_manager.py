"""In-memory conversation context with configurable truncation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    role: Role
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ConversationManager:
    def __init__(self, max_messages: int = 20, system_prompt: str = "") -> None:
        if max_messages < 2:
            raise ValueError("max_messages must be at least 2")
        self.max_messages = max_messages
        self.system_prompt = system_prompt
        self._messages: list[ChatMessage] = []

    def set_system_prompt(self, prompt: str) -> None:
        self.system_prompt = prompt

    def add(
        self,
        role: Role,
        content: str,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            role=role,
            content=content.strip(),
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_calls=tool_calls,
        )
        self._messages.append(message)
        return message

    def clear(self) -> None:
        self._messages.clear()

    def history(self) -> list[ChatMessage]:
        return list(self._messages)

    def replace_history(self, messages: list[ChatMessage]) -> None:
        self._messages = list(messages)

    def context_window(self) -> list[ChatMessage]:
        """System prompt plus the most recent messages.

        Truncation never starts on a tool result. The assistant message that
        requested those tools is kept with them, even if that exceeds the limit.
        """
        if not self._messages:
            recent: list[ChatMessage] = []
        else:
            start = max(0, len(self._messages) - self.max_messages)
            while start > 0 and self._messages[start].role == "tool":
                start -= 1
            recent = self._messages[start:]
            while recent and recent[0].role == "tool":
                recent = recent[1:]
        window: list[ChatMessage] = []
        if self.system_prompt:
            window.append(ChatMessage(role="system", content=self.system_prompt))
        window.extend(recent)
        return window

    def provider_payload(self) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for message in self.context_window():
            item: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.role == "assistant" and message.tool_calls:
                item["tool_calls"] = message.tool_calls
                if not message.content:
                    item["content"] = None
            if message.role == "tool":
                if message.tool_call_id:
                    item["tool_call_id"] = message.tool_call_id
                if message.tool_name:
                    item["name"] = message.tool_name
            payload.append(item)
        return payload
