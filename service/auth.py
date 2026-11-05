"""Device pairing tokens. Each phone gets its own revocable token."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from app.paths import app_data_dir


class DeviceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "devices.json")
        self._devices = self._load()

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._devices, indent=2), encoding="utf-8")

    def pair(self, name: str) -> str:
        token = secrets.token_urlsafe(24)
        self._devices[token] = {"name": name.strip() or "phone", "revoked": "0"}
        self._save()
        return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        device = self._devices.get(token)
        return bool(device) and device.get("revoked") != "1"

    def revoke(self, token: str) -> bool:
        device = self._devices.get(token)
        if not device:
            return False
        device["revoked"] = "1"
        self._save()
        return True

    def revoke_tail(self, tail: str) -> bool:
        needle = tail.strip()
        if len(needle) < 6:
            return False
        for token, device in self._devices.items():
            if token.endswith(needle):
                device["revoked"] = "1"
                self._save()
                return True
        return False

    def list_devices(self) -> list[dict[str, str]]:
        return [
            {"name": item["name"], "token_tail": token[-6:], "revoked": item.get("revoked", "0")}
            for token, item in self._devices.items()
        ]
