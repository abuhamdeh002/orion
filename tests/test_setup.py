"""First-run setup: keys go into .env, only from the PC, and nothing else in the file changes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.env_file import set_env_values


def test_env_values_are_updated_in_place(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("# comment\nAI_PROVIDER=ollama\nGROQ_API_KEY=\n", encoding="utf-8")
    set_env_values(path, {"GROQ_API_KEY": "gsk_test123", "GEMINI_API_KEY": "AIzaTest"})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[:3] == ["# comment", "AI_PROVIDER=ollama", "GROQ_API_KEY=gsk_test123"]
    assert lines[3] == "GEMINI_API_KEY=AIzaTest"


def test_env_values_reject_injection(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        set_env_values(tmp_path / ".env", {"GROQ_API_KEY": "x\nPRIVATE_MODE=false"})
    with pytest.raises(ValueError):
        set_env_values(tmp_path / ".env", {"lower": "x"})


def test_setup_only_from_the_pc(monkeypatch, tmp_path: Path) -> None:
    from service import api

    remote = TestClient(api.app)
    assert remote.post("/setup", json={"groq_api_key": "gsk_x"}).status_code == 401

    target = tmp_path / ".env"
    monkeypatch.setattr("app.paths.env_file", lambda: target)
    monkeypatch.setattr(api.get_runtime(), "reload_config", lambda: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    local = TestClient(api.app, client=("127.0.0.1", 50000))
    response = local.post("/setup", json={"groq_api_key": "gsk_x"})
    assert response.status_code == 200
    assert "GROQ_API_KEY=gsk_x" in target.read_text(encoding="utf-8")
    assert "gsk_x" not in response.text, "the key is never echoed back"
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
