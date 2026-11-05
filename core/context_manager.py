"""Builds the model context from conversation history and preferences."""

from __future__ import annotations

from app.config import AppConfig
from core.conversation_manager import ConversationManager


class ContextManager:
    def __init__(self, conversation: ConversationManager, config: AppConfig) -> None:
        self.conversation = conversation
        self.config = config

    def provider_messages(self) -> list[dict]:
        self.conversation.max_messages = self.config.context_max_messages
        return self.conversation.provider_payload()
