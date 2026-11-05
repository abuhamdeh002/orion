"""After the trial: the PC keeps working; phone access and the cloud relay stop."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import license as lic
from app.license import LicenseState, current_license

EXPIRED = LicenseState("expired", False, 0, "The trial has ended.")
TRIAL = LicenseState("trial", True, None, "Trial.")
LIFETIME = LicenseState("lifetime", False, None, "Licensed.")


def test_what_each_state_allows() -> None:
    assert TRIAL.allows_phone and TRIAL.allows_cloud and TRIAL.notice is None
    assert LIFETIME.allows_phone and not LIFETIME.allows_cloud
    assert not EXPIRED.allows_phone and not EXPIRED.allows_cloud
    assert "keep working" in EXPIRED.notice


def test_deleting_trial_txt_does_not_restart_the_trial(tmp_path: Path, monkeypatch) -> None:
    saved = {}
    monkeypatch.setattr(lic, "_registry_trial", lambda: saved.get("start"))
    monkeypatch.setattr(lic, "_save_registry_trial", lambda start: saved.__setitem__("start", start))
    first = lic._trial_start(tmp_path, 1_000.0, use_registry=True)
    (tmp_path / "trial.txt").unlink()
    again = lic._trial_start(tmp_path, 9_000_000.0, use_registry=True)
    assert first == again == 1_000.0
    assert (tmp_path / "trial.txt").read_text() == "1000.0"


def test_tests_never_touch_the_real_registry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(lic, "_save_registry_trial", lambda start: (_ for _ in ()).throw(AssertionError("registry written")))
    assert current_license(tmp_path / "license.key", now=5.0).plan == "trial"


def _with_license(monkeypatch, state: LicenseState) -> None:
    monkeypatch.setattr("service.api.license_gate", lambda: state)


def test_expired_blocks_paired_phones_but_not_the_pc(monkeypatch) -> None:
    from service.api import app
    from service.runtime import get_runtime

    _with_license(monkeypatch, TRIAL)
    local = TestClient(app, client=("127.0.0.1", 50000))
    token = local.post("/pair", json={"name": "test"}).json()["token"]
    remote = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    assert remote.get("/skills", headers=headers).status_code == 200

    _with_license(monkeypatch, EXPIRED)
    blocked = remote.get("/skills", headers=headers)
    assert blocked.status_code == 402
    assert "still works on the PC" in blocked.json()["detail"]
    assert local.get("/skills").status_code == 200
    assert local.post("/chat", json={"text": "what is 2 + 2"}).json()["text"] == "That's 4."
    assert local.post("/pair", json={"name": "new"}).status_code == 402
    get_runtime().devices.revoke(token)


def test_relay_stops_when_the_license_lapses(monkeypatch) -> None:
    from service.relay_client import RelayClient

    class Assistant:
        def handle_user_message(self, text, **_turn):
            raise AssertionError("must not run without a cloud license")

    runtime = type("R", (), {"assistant": Assistant(), "events": []})()
    client = RelayClient(runtime, "ws://example", "token")
    monkeypatch.setattr("service.relay_client.license_gate", lambda: LIFETIME)
    answer = client.handle_frame({"type": "chat", "id": "1", "text": "hi"})
    assert answer["error"] is True and "license" in answer["text"]
    assert client._stop.is_set()


def test_relay_does_not_start_without_cloud(monkeypatch) -> None:
    from service.relay_client import RelayClient

    started = []
    monkeypatch.setattr("service.relay_client.license_gate", lambda: EXPIRED)
    monkeypatch.setattr("threading.Thread.start", lambda self: started.append(self.name))
    RelayClient(type("R", (), {})(), "ws://example", "token").start()
    assert started == []
