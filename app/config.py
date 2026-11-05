"""Environment and user-preference configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import env_file, settings_path


ProviderName = Literal["openai", "ollama"]
TtsProviderName = Literal["kokoro", "edge", "pyttsx3", "none"]
SttProviderName = Literal["speech_recognition", "none"]


class EnvConfig(BaseSettings):
    """Secrets and process-level settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=str(env_file()),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    ai_provider: ProviderName = "openai"
    ai_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_base_url: str = "http://127.0.0.1:11434"
    # The local model when AI_PROVIDER is not ollama (with ollama, AI_MODEL is the local model).
    ollama_model: str | None = None
    weather_api_key: str | None = None
    weather_base_url: str = "https://api.openweathermap.org/data/2.5"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    private_mode: bool = False
    orion_host: str = "127.0.0.1"
    orion_port: int = Field(default=8765, ge=1, le=65535)
    orion_pin: str | None = None
    orion_relay_url: str | None = None
    orion_public_url: str | None = None
    orion_account_id: str | None = None
    orion_account_token: str | None = None
    orion_phone_token: str | None = None
    tts_provider: TtsProviderName = "kokoro"
    stt_provider: SttProviderName = "speech_recognition"
    log_level: str = "INFO"
    request_timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)
    context_max_messages: int = Field(default=20, ge=2, le=200)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=64, le=8192)

    @field_validator(
        "openai_api_key",
        "weather_api_key",
        "telegram_bot_token",
        "groq_api_key",
        "gemini_api_key",
        "telegram_chat_id",
        "orion_pin",
        "orion_relay_url",
        "orion_public_url",
        "orion_account_id",
        "orion_account_token",
        "orion_phone_token",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()


class AllowedApplication(BaseModel):
    alias: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1)

    @field_validator("alias")
    @classmethod
    def normalize_alias(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if any(ch in cleaned for ch in "\\/:*?\"<>|"):
            raise ValueError("Application alias contains invalid characters")
        return cleaned


class UserPreferences(BaseModel):
    """Non-secret settings the user can change in the UI."""

    ai_provider: ProviderName | None = None
    ai_model: str | None = None
    openai_base_url: str | None = None
    ollama_base_url: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=64, le=8192)
    context_max_messages: int | None = Field(default=None, ge=2, le=200)
    speak_replies: bool = False
    push_to_talk: bool = True
    continuous_listening: bool = False
    microphone_device_index: int | None = None
    tts_voice_id: str | None = None
    tts_rate: int | None = Field(default=None, ge=50, le=400)
    default_city: str | None = None
    response_style: str = "concise"
    search_url_template: str = "https://duckduckgo.com/?q={query}"
    allowed_apps: list[AllowedApplication] = Field(default_factory=list)
    history_retention_days: int = Field(default=30, ge=1, le=3650)
    music_app_alias: str | None = None
    theme: Literal["night", "light"] = "night"
    display_name: str | None = None
    reply_suffix: str | None = None
    work_days: str | None = None
    briefing_hour: int = Field(default=8, ge=0, le=23)
    focus_mode: bool = False
    persona: str = "calm"
    calendar_ics_url: str | None = None


class AppConfig(BaseModel):
    """Effective runtime configuration after merging env and preferences."""

    ai_provider: ProviderName
    ai_model: str
    openai_api_key: str | None
    openai_base_url: str
    ollama_base_url: str
    weather_api_key: str | None
    weather_base_url: str
    tts_provider: TtsProviderName
    stt_provider: SttProviderName
    log_level: str
    request_timeout_seconds: float
    context_max_messages: int
    temperature: float
    max_tokens: int
    speak_replies: bool
    push_to_talk: bool
    continuous_listening: bool
    microphone_device_index: int | None = None
    tts_voice_id: str | None = None
    tts_rate: int = 180
    default_city: str | None
    response_style: str
    search_url_template: str
    allowed_apps: list[AllowedApplication]
    history_retention_days: int = 30
    music_app_alias: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    ollama_model: str | None = None
    private_mode: bool = False
    orion_host: str = "127.0.0.1"
    orion_port: int = 8765
    display_name: str | None = None
    reply_suffix: str | None = None
    work_days: str | None = None
    briefing_hour: int = 8
    focus_mode: bool = False
    persona: str = "calm"
    calendar_ics_url: str | None = None
    orion_pin: str | None = None
    orion_relay_url: str | None = None
    orion_public_url: str | None = None
    orion_account_id: str | None = None
    orion_account_token: str | None = None
    orion_phone_token: str | None = None

    def provider_ready(self) -> bool:
        if self.ai_provider == "openai":
            return bool(self.openai_api_key)
        return True

    def missing_provider_message(self) -> str | None:
        if self.ai_provider == "openai" and not self.openai_api_key:
            return (
                "OpenAI is selected but OPENAI_API_KEY is not set. "
                "Copy .env.example to .env and add a key, or switch the provider to Ollama."
            )
        return None


def parse_allowed_apps(text: str) -> list[AllowedApplication]:
    """Parse 'alias|path' lines. Blank lines are ignored."""
    apps: list[AllowedApplication] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        alias, separator, path = line.partition("|")
        if not separator or not alias.strip() or not path.strip():
            raise ValueError(f"Expected alias|path, got: {line}")
        apps.append(AllowedApplication(alias=alias, path=path.strip()))
    return apps


def format_allowed_apps(apps: list[AllowedApplication]) -> str:
    return "\n".join(f"{app.alias}|{app.path}" for app in apps)


def load_preferences(path: Path | None = None) -> UserPreferences:
    target = path or settings_path()
    if not target.exists():
        return UserPreferences()
    payload = json.loads(target.read_text(encoding="utf-8"))
    return UserPreferences.model_validate(payload)


def save_preferences(preferences: UserPreferences, path: Path | None = None) -> None:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(preferences.model_dump_json(indent=2), encoding="utf-8")


def merge_config(env: EnvConfig, preferences: UserPreferences) -> AppConfig:
    def pick(pref_value, env_value):
        return env_value if pref_value is None else pref_value

    return AppConfig(
        ai_provider=pick(preferences.ai_provider, env.ai_provider),
        ai_model=pick(preferences.ai_model, env.ai_model),
        openai_api_key=env.openai_api_key,
        openai_base_url=pick(preferences.openai_base_url, env.openai_base_url),
        ollama_base_url=pick(preferences.ollama_base_url, env.ollama_base_url),
        weather_api_key=env.weather_api_key,
        weather_base_url=env.weather_base_url,
        tts_provider=env.tts_provider,
        stt_provider=env.stt_provider,
        log_level=env.log_level,
        request_timeout_seconds=env.request_timeout_seconds,
        context_max_messages=pick(preferences.context_max_messages, env.context_max_messages),
        temperature=pick(preferences.temperature, env.temperature),
        max_tokens=pick(preferences.max_tokens, env.max_tokens),
        speak_replies=preferences.speak_replies,
        push_to_talk=preferences.push_to_talk,
        continuous_listening=preferences.continuous_listening,
        microphone_device_index=preferences.microphone_device_index,
        tts_voice_id=preferences.tts_voice_id,
        tts_rate=preferences.tts_rate or 180,
        default_city=preferences.default_city,
        response_style=preferences.response_style,
        search_url_template=preferences.search_url_template,
        allowed_apps=list(preferences.allowed_apps),
        history_retention_days=preferences.history_retention_days,
        music_app_alias=preferences.music_app_alias,
        telegram_bot_token=env.telegram_bot_token,
        telegram_chat_id=env.telegram_chat_id,
        groq_api_key=env.groq_api_key,
        groq_model=env.groq_model,
        groq_base_url=env.groq_base_url,
        gemini_api_key=env.gemini_api_key,
        gemini_model=env.gemini_model,
        gemini_base_url=env.gemini_base_url,
        ollama_model=env.ollama_model,
        private_mode=env.private_mode,
        orion_host=env.orion_host,
        orion_port=env.orion_port,
        display_name=preferences.display_name,
        reply_suffix=preferences.reply_suffix,
        work_days=preferences.work_days,
        briefing_hour=preferences.briefing_hour,
        focus_mode=preferences.focus_mode,
        persona=preferences.persona,
        calendar_ics_url=preferences.calendar_ics_url,
        orion_pin=env.orion_pin,
        orion_relay_url=env.orion_relay_url,
        orion_public_url=env.orion_public_url,
        orion_account_id=env.orion_account_id,
        orion_account_token=env.orion_account_token,
        orion_phone_token=env.orion_phone_token,
    )


def load_config(preferences_path: Path | None = None) -> AppConfig:
    return merge_config(EnvConfig(), load_preferences(preferences_path))
