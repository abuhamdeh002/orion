"""Telegram Bot API send. The token stays in the environment."""

from __future__ import annotations

import httpx

from app.errors import ConfigurationError, ProviderError, ProviderTimeoutError


class TelegramClient:
    def __init__(self, token: str | None, timeout: float = 20.0) -> None:
        self.token = token
        self.timeout = timeout

    def send_message(self, chat_id: str, text: str) -> dict:
        if not self.token:
            raise ConfigurationError(
                "TELEGRAM_BOT_TOKEN is not set. Add it to .env before sending Telegram messages."
            )
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json={"chat_id": chat_id, "text": text})
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Telegram timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach Telegram: {exc}") from exc
        if response.status_code == 401:
            raise ConfigurationError("Telegram rejected the bot token.")
        if response.status_code >= 400:
            raise ProviderError(f"Telegram error ({response.status_code}).")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("Telegram returned an unexpected response.") from exc
        if not payload.get("ok"):
            raise ProviderError("Telegram did not accept the message.")
        return {"message_id": payload.get("result", {}).get("message_id")}
