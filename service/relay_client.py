"""Outbound relay. The PC connects to the cloud; nothing on the PC has to accept inbound internet traffic."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.license import license_gate
from service.commands import perform

logger = logging.getLogger("orion.relay")

FrameHook = Callable[[dict[str, Any]], dict[str, Any] | None]


def relay_url(base: str, account: str | None) -> str:
    """The relay routes by account and checks the token against role=pc, so both must be on the URL."""
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query))
    query["role"] = "pc"
    if account:
        query["account"] = account
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class RelayClient:
    def __init__(
        self,
        runtime: Any,
        url: str,
        token: str,
        connect: Callable[..., Any] | None = None,
        account: str | None = None,
    ) -> None:
        self.runtime = runtime
        self.url = relay_url(url, account)
        self.token = token
        self._connect = connect
        self._stop = threading.Event()

    def start(self) -> None:
        state = license_gate()
        if not state.allows_cloud:
            logger.info("Relay skipped: %s", state.notice or "this license does not include the cloud relay.")
            return
        threading.Thread(target=self._loop, name="OrionRelay", daemon=True).start()

    def handle_frame(self, frame: dict[str, Any]) -> dict[str, Any] | None:
        from service.runtime import KILL

        kind = str(frame.get("type") or "")
        if kind in {"chat", "do"} and not license_gate().allows_cloud:
            # The license can lapse while the relay is connected; stop serving instead of waiting for a restart.
            self._stop.set()
            return {"type": "ack" if kind == "do" else "reply", "id": frame.get("id"), "ok": False, "error": True,
                    "text": "The ORION license for the cloud relay has ended."}
        if kind in {"chat", "do"} and KILL.is_set():
            return {"type": "ack" if kind == "do" else "reply", "id": frame.get("id"), "ok": False, "text": "Kill switch is on.", "error": True}
        if kind == "chat":
            reply = self.runtime.assistant.handle_user_message(str(frame.get("text") or ""), source="phone", ask_on_reply=True)
            return {"type": "reply", "id": frame.get("id"), "text": reply.text, "error": reply.error, "confirm": bool(getattr(reply, "needs_confirm", False))}
        if kind == "do":
            result = perform(self.runtime, str(frame.get("action") or ""), frame.get("arguments") or {})
            result["type"] = "ack"
            result["id"] = frame.get("id")
            return result
        if kind == "ping":
            return {"type": "presence", "pc": "online"}
        return None

    def _loop(self) -> None:
        delay = 1
        while not self._stop.is_set():
            try:
                asyncio.run(self._session())
                delay = 1
            except Exception as exc:
                logger.warning("Relay disconnected: %s", exc)
                self._stop.wait(delay)
                delay = min(delay * 2, 60)

    async def _session(self) -> None:
        import websockets

        opener = self._connect or websockets.connect
        async with opener(self.url, additional_headers={"Authorization": f"Bearer {self.token}"}) as socket:
            await socket.send(json.dumps({"type": "hello", "role": "pc"}))
            async for raw in socket:
                frame = json.loads(raw)
                answer = self.handle_frame(frame)
                if answer is not None:
                    await socket.send(json.dumps(answer))
                if self._stop.is_set():
                    return
                if frame.get("type") == "event_pull":
                    for event in self.runtime.events[-20:]:
                        await socket.send(json.dumps({"type": "event", **event}))
