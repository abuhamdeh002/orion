from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Before anything imports app.config: tests never read the real .env or write the real data/ folder.
_SANDBOX = Path(tempfile.mkdtemp(prefix="orion-tests-"))
os.environ["ORION_DATA_DIR"] = str(_SANDBOX / "data")
os.environ["ORION_ENV_FILE"] = str(_SANDBOX / "no.env")
for _secret in (
    "GROQ_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "ORION_RELAY_URL", "ORION_ACCOUNT_ID", "ORION_ACCOUNT_TOKEN", "ORION_PHONE_TOKEN",
):
    os.environ.pop(_secret, None)
os.environ["ORION_PUBLIC_URL"] = "https://orion-test.example"
os.environ["ORION_NO_HEAL"] = "1"  # healing would unload the real model on this PC

import pytest  # noqa: E402

from ai.base_provider import ChatResponse, LLMProvider
from app.config import AppConfig, EnvConfig, UserPreferences, merge_config


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(
        self,
        text: str = "Acknowledged.",
        fail: Exception | None = None,
        on_chat=None,
        responses: list[ChatResponse] | None = None,
    ) -> None:
        self.text = text
        self.fail = fail
        self.on_chat = on_chat
        self.responses = list(responses) if responses else None
        self.calls: list[list[dict[str, Any]]] = []

    def health(self) -> tuple[bool, str]:
        return True, "fake provider"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        self.calls.append(messages)
        if self.on_chat:
            self.on_chat()
        if self.fail:
            raise self.fail
        if self.responses:
            return self.responses.pop(0)
        return ChatResponse(text=self.text, model="fake")


@pytest.fixture
def env_config() -> EnvConfig:
    return EnvConfig(
        ai_provider="openai",
        ai_model="gpt-4o-mini",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        ollama_base_url="http://127.0.0.1:11434",
    )


@pytest.fixture
def app_config(env_config: EnvConfig) -> AppConfig:
    return merge_config(env_config, UserPreferences())


@pytest.fixture
def prefs_path(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


@pytest.fixture(autouse=True)
def _trial_license(monkeypatch):
    """Tests run as if in the trial, whatever this machine's real trial date is.

    Tests about expiry patch license_gate themselves.
    """
    import time

    from app import license as lic

    state = lic.LicenseState("trial", True, None, "Trial.")
    monkeypatch.setattr(lic, "_cached", (time.monotonic() + 10**9, state))
