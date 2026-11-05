"""Auth, events, commands, license, and relay framing."""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.license import current_license, set_public_key, sign_license, verify_license
from service.commands import perform
from service.relay_client import RelayClient

from app import license as _license_module

_DEV_PUBLIC = _license_module._PUBLIC_RAW


def test_remote_routes_require_a_paired_token():
    from service.api import app

    remote = TestClient(app)
    assert remote.get("/skills").status_code == 401
    local = TestClient(app, client=("127.0.0.1", 50000))
    paired = local.post("/pair", json={"name": "s24"})
    assert paired.status_code == 200
    token = paired.json()["token"]
    assert remote.get("/skills", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert local.delete(f"/pair/{token[-6:]}").json()["revoked"] is True
    assert remote.get("/skills", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_events_have_a_kind():
    from service.runtime import get_runtime

    runtime = get_runtime()
    listener = runtime.subscribe()
    runtime.push("Dinner", kind="reminder", data={"fire": "due"})
    item = listener.get(timeout=1)
    runtime.unsubscribe(listener)
    assert item["kind"] == "reminder"
    assert item["text"] == "Dinner"


def test_commands_call_the_real_functions(monkeypatch):
    def fake_open(name: str):
        from tools.base_tool import ToolResult

        return ToolResult(ok=True, message=f"Opened {name}.")

    monkeypatch.setattr("tools.app_control.open_app", fake_open)
    runtime = type("R", (), {"_pin_ok": lambda self: False})()
    assert perform(runtime, "open", {"name": "notepad"})["message"] == "Opened notepad."
    assert perform(runtime, "shutdown", {})["confirm"] is True


def test_license_signature_expiry_and_trial(tmp_path: Path):
    private = Ed25519PrivateKey.generate()
    set_public_key(private.public_key().public_bytes_raw())
    try:
        token = sign_license({"plan": "lifetime", "cloud": True, "exp": 2_000_000_000}, private.private_bytes_raw())
        assert verify_license(token, now=1_700_000_000).allows_cloud is True
        assert verify_license(token, now=2_100_000_000).plan == "expired"
        assert verify_license(token + "x", now=1_700_000_000).reason == "The license key is not valid."
        assert current_license(tmp_path / "license.key", now=1_000.0).plan == "trial"
        assert current_license(tmp_path / "license.key", now=1_000.0 + 15 * 24 * 60 * 60).plan == "expired"
    finally:
        set_public_key(_DEV_PUBLIC)


def test_relay_frames_do_not_touch_the_network():
    class Assistant:
        def handle_user_message(self, text: str, **_turn):
            return type("Reply", (), {"text": text.upper(), "error": None})()

    runtime = type("R", (), {"assistant": Assistant(), "events": []})()
    client = RelayClient(runtime, "ws://example", "token")
    reply = client.handle_frame({"type": "chat", "id": "1", "text": "time"})
    assert reply is not None
    assert reply["text"] == "TIME"
    assert reply["id"] == "1"


def test_license_key_was_rotated_away_from_the_leaked_one():
    leaked_public = bytes.fromhex("381d433be33c7015f68436081884a41e74f0ed97d6e9a307579e08c3f269cae7")
    assert _license_module._PUBLIC_RAW != leaked_public


def test_relay_url_carries_role_and_account():
    from service.relay_client import relay_url

    url = relay_url("wss://relay.example/connect", "acct_1")
    assert "role=pc" in url and "account=acct_1" in url


def test_relay_frames_respect_the_kill_switch():
    from service.runtime import KILL

    class Assistant:
        def handle_user_message(self, text: str, **_turn):
            raise AssertionError("must not run while killed")

    runtime = type("R", (), {"assistant": Assistant(), "events": []})()
    client = RelayClient(runtime, "ws://example", "token")
    KILL.set()
    try:
        assert client.handle_frame({"type": "chat", "id": "1", "text": "hi"})["error"] is True
    finally:
        KILL.clear()


def test_phone_pair_link_matches_what_android_expects():
    from urllib.parse import parse_qs, urlsplit

    from service.api import phone_pair_link

    config = type("C", (), {"orion_relay_url": "wss://relay.test/ws", "orion_account_id": "acct_1", "orion_phone_token": "tok"})()
    link = phone_pair_link(config)
    parts = urlsplit(link)
    assert parts.scheme == "orion" and parts.netloc == "pair"
    assert parse_qs(parts.query) == {"relay": ["wss://relay.test/ws"], "account": ["acct_1"], "token": ["tok"]}
    missing = type("C", (), {"orion_relay_url": None, "orion_account_id": None, "orion_phone_token": None})()
    assert phone_pair_link(missing) is None


def test_phone_shutdown_carries_its_own_pin(monkeypatch):
    import ctypes

    calls = []
    monkeypatch.setattr(ctypes.windll.user32, "ExitWindowsEx", lambda *a: calls.append(a))

    class Runtime:
        pending_pin = False
        _pin = ""

        def set_pin(self, pin):
            self._pin = pin

        def _pin_ok(self):
            return self.pending_pin and self._pin == "1234"

    assert perform(Runtime(), "shutdown", {})["confirm"] is True
    assert calls == []
    assert perform(Runtime(), "shutdown", {"pin": "1234"})["ok"] is True
    assert calls, "shutdown ran only with the right PIN"
