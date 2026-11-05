"""Local API safety: DNS rebinding, cross-site pages, and proxied callers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from service.guard import host_allowed, is_local, origin_allowed


def test_host_rules_block_rebinding_domains():
    assert host_allowed("127.0.0.1:8765")
    assert host_allowed("localhost:8765")
    assert host_allowed("[::1]:8765")
    assert host_allowed("192.168.1.20:8765")
    assert host_allowed("desktop-pc:8765")
    assert host_allowed("orion-pc.tail1234.ts.net")
    assert not host_allowed("evil.example:8765")
    assert not host_allowed("127.0.0.1.nip.io")
    assert not host_allowed("")


def test_extra_hosts_from_env(monkeypatch):
    monkeypatch.setenv("ORION_ALLOWED_HOSTS", "orion.home.lan")
    assert host_allowed("orion.home.lan:8765")


def test_origin_must_match_host_or_be_localhost():
    assert origin_allowed(None, "127.0.0.1:8765")
    assert origin_allowed("http://127.0.0.1:8765", "127.0.0.1:8765")
    assert origin_allowed("http://localhost:5173", "127.0.0.1:8765")
    assert not origin_allowed("https://evil.example", "127.0.0.1:8765")
    assert not origin_allowed("null", "127.0.0.1:8765")


def test_proxied_loopback_is_not_local():
    assert is_local("127.0.0.1", {})
    assert not is_local("127.0.0.1", {"x-forwarded-for": "100.64.0.9"})
    assert not is_local("127.0.0.1", {"tailscale-user-login": "someone@example.com"})
    assert not is_local("100.64.0.9", {})


def test_api_refuses_cross_site_and_proxied_requests():
    from service.api import app

    local = TestClient(app, client=("127.0.0.1", 50000))
    assert local.get("/skills").status_code == 200
    assert local.get("/skills", headers={"Origin": "https://evil.example"}).status_code == 403
    assert local.get("/skills", headers={"Host": "evil.example"}).status_code == 421
    assert local.get("/skills", headers={"X-Forwarded-For": "100.64.0.9"}).status_code == 401
    assert local.post("/pair", json={"name": "x"}, headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 403


def test_pair_link_keeps_the_token_out_of_the_query():
    from service.api import app

    local = TestClient(app, client=("127.0.0.1", 50000))
    body = local.post("/pair", json={"name": "test"}).json()
    assert "?token=" not in body["link"]
    assert body["link"].endswith(f"#token={body['token']}")
    local.delete(f"/pair/{body['token'][-6:]}")


def test_websocket_rejects_other_sites_and_unpaired_callers():
    import pytest
    from starlette.websockets import WebSocketDisconnect

    from service.api import app

    remote = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with remote.websocket_connect("/ws", headers={"Origin": "https://evil.example"}) as socket:
            socket.receive_json()
    with remote.websocket_connect("/ws") as socket:
        socket.send_json({"type": "auth", "token": "wrong"})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_web_chat_over_the_socket_streams_and_keeps_one_source():
    """The web page streams over /ws; a 'yes' on a fresh socket must reach the same pending turn."""
    from service.api import app
    from service.runtime import get_runtime

    local = TestClient(app, client=("127.0.0.1", 50000))
    seen = []
    assistant = get_runtime().assistant
    original = assistant.handle_user_message

    def spy(text, **turn):
        seen.append(turn["source"])
        return original(text, **turn)

    assistant.handle_user_message = spy
    try:
        for _ in range(2):
            with local.websocket_connect("/ws") as socket:
                socket.send_json({"type": "auth", "token": "already-trusted"})
                assert socket.receive_json() == {"type": "ready"}
                socket.send_json({"text": "what is 2 + 2"})
                frame = socket.receive_json()
                while frame["type"] == "token":
                    frame = socket.receive_json()
                assert frame["type"] == "reply" and frame["text"] == "That's 4."
                assert frame["actions"] == [] and frame["confirm"] is False
    finally:
        assistant.handle_user_message = original
    assert seen == ["web", "web"]


def test_pairing_only_offers_a_qr_code_a_phone_can_open(monkeypatch):
    """127.0.0.1 on a phone is the phone, so without Tailscale or ORION_PUBLIC_URL there is no QR code."""
    from service.api import app

    local = TestClient(app, client=("127.0.0.1", 50000))
    from service.runtime import get_runtime

    monkeypatch.setattr("service.api.public_base", lambda config: None)
    before = len(get_runtime().devices.path.read_text(encoding="utf-8")) if get_runtime().devices.path.exists() else 0
    body = local.post("/pair", json={"name": "test"}).json()
    assert body["reachable"] is False and "token" not in body and "Tailscale" in body["detail"]
    after = len(get_runtime().devices.path.read_text(encoding="utf-8")) if get_runtime().devices.path.exists() else 0
    assert after == before

    monkeypatch.setattr("service.api.public_base", lambda config: "https://pc.tail1234.ts.net")
    body = local.post("/pair", json={"name": "test"}).json()
    assert body["reachable"] is True and body["link"] == f"https://pc.tail1234.ts.net/#token={body['token']}"
    local.delete(f"/pair/{body['token'][-6:]}")


def test_public_url_setting_wins_over_tailscale(monkeypatch):
    from service import reach

    monkeypatch.setattr(reach, "tailscale_name", lambda: "pc.tail1234.ts.net")
    assert reach.public_base(type("C", (), {"orion_public_url": "https://orion.example/"})()) == "https://orion.example"
    assert reach.public_base(type("C", (), {"orion_public_url": None})()) == "https://pc.tail1234.ts.net"
