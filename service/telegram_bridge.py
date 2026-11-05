"""Two-way Telegram commands, locked to the configured chat id."""

from __future__ import annotations

import threading
import time

import httpx

from service.runtime import KILL, OrionRuntime


def start(runtime: OrionRuntime) -> threading.Thread | None:
    token = runtime.config.telegram_bot_token
    chat_id = runtime.config.telegram_chat_id
    if not token or not chat_id:
        return None

    def _run() -> None:
        offset = 0
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        while True:
            if KILL.is_set():
                time.sleep(2)
                continue
            try:
                with httpx.Client(timeout=30) as client:
                    response = client.get(url, params={"timeout": 10, "offset": offset})
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                time.sleep(5)
                continue
            for update in payload.get("result") or []:
                offset = int(update.get("update_id") or offset) + 1
                message = update.get("message") or {}
                sender = str((message.get("chat") or {}).get("id") or "")
                text = str(message.get("text") or "").strip()
                if sender != str(chat_id) or not text:
                    continue
                from service.runtime import KILL

                if KILL.is_set():
                    _send(token, chat_id, "Kill switch is on.")
                    continue
                reply = runtime.assistant.handle_user_message(text, source="telegram", ask_on_reply=True)
                _send(token, chat_id, reply.text)
            time.sleep(1)

    thread = threading.Thread(target=_run, name="OrionTelegram", daemon=True)
    thread.start()
    return thread


def _send(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=20) as client:
            client.post(url, json={"chat_id": chat_id, "text": text[:4000]})
    except httpx.HTTPError:
        return
