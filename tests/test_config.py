from __future__ import annotations

from pathlib import Path

from app.config import EnvConfig, UserPreferences, load_preferences, merge_config, save_preferences


def test_empty_api_key_becomes_none() -> None:
    env = EnvConfig(openai_api_key="  ")
    assert env.openai_api_key is None


def test_missing_openai_key_is_reported() -> None:
    config = merge_config(EnvConfig(ai_provider="openai", openai_api_key=None), UserPreferences())
    assert config.provider_ready() is False
    message = config.missing_provider_message()
    assert message is not None
    assert "OPENAI_API_KEY" in message


def test_ollama_is_ready_without_api_key() -> None:
    config = merge_config(EnvConfig(ai_provider="ollama", openai_api_key=None), UserPreferences())
    assert config.provider_ready() is True
    assert config.missing_provider_message() is None


def test_preferences_override_model_but_not_secrets(tmp_path: Path) -> None:
    env = EnvConfig(openai_api_key="sk-test-secret", ai_model="env-model")
    prefs = UserPreferences(ai_model="ui-model", temperature=0.2)
    config = merge_config(env, prefs)
    assert config.ai_model == "ui-model"
    assert config.temperature == 0.2
    assert config.openai_api_key == "sk-test-secret"


def test_allowed_app_lines_round_trip() -> None:
    from app.config import AllowedApplication, format_allowed_apps, parse_allowed_apps

    text = "notepad|C:\\Windows\\System32\\notepad.exe\n# comment\n"
    apps = parse_allowed_apps(text)
    assert apps == [AllowedApplication(alias="notepad", path="C:\\Windows\\System32\\notepad.exe")]
    assert "notepad|" in format_allowed_apps(apps)


def test_default_registry_includes_safe_apps(app_config: AppConfig) -> None:
    from tools.registry import create_default_registry

    registry = create_default_registry(app_config)
    launcher = registry.get("app_launcher")
    assert launcher is not None
    assert "notepad" in launcher.list_apps()


def test_preferences_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    original = UserPreferences(default_city="Riyadh", speak_replies=True)
    save_preferences(original, path)
    loaded = load_preferences(path)
    assert loaded.default_city == "Riyadh"
    assert loaded.speak_replies is True
