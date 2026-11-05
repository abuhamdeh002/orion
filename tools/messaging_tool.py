"""Messaging drafts and sends. Every send requires confirmation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.config import AppConfig
from app.errors import OrionError
from core.permissions import RiskLevel
from integrations.messaging.email_draft import EmailDraft
from integrations.messaging.telegram import TelegramClient
from tools.base_tool import BaseTool, ToolResult


class MessagingArgs(BaseModel):
    action: Literal["telegram", "email_draft"]
    recipient: str = Field(min_length=1, description="Telegram chat id or email address")
    body: str = Field(min_length=1)
    subject: str = ""


class MessagingTool(BaseTool):
    name = "messaging"
    description = "Send a Telegram message or open an email draft. Always confirm recipient and body first."
    risk = RiskLevel.HIGH
    requires_confirmation = True

    def __init__(
        self,
        config: AppConfig,
        telegram: TelegramClient | None = None,
        email: EmailDraft | None = None,
    ) -> None:
        self.config = config
        self.telegram = telegram or TelegramClient(config.telegram_bot_token, timeout=config.request_timeout_seconds)
        self.email = email or EmailDraft()

    @property
    def input_schema(self) -> type[BaseModel]:
        return MessagingArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, MessagingArgs):
            arguments = MessagingArgs.model_validate(arguments)
        if arguments.action == "email_draft":
            url = self.email.open_draft(arguments.recipient, arguments.subject, arguments.body)
            return ToolResult(ok=True, message=f"Opened an email draft to {arguments.recipient}.", data={"url": url})
        try:
            result = self.telegram.send_message(arguments.recipient, arguments.body)
        except OrionError as exc:
            return ToolResult(ok=False, message=str(exc))
        return ToolResult(ok=True, message=f"Sent the Telegram message to {arguments.recipient}.", data=result)
