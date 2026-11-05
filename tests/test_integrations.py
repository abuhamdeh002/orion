from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import AppConfig
from app.errors import ConfigurationError, ProviderError
from integrations.weather.openweathermap import OpenWeatherMapClient
from tools.messaging_tool import MessagingArgs, MessagingTool
from tools.music_tool import MusicArgs, MusicTool
from tools.vision_tool import VisionArgs, VisionTool
from tools.weather_tool import WeatherArgs, WeatherTool


def test_weather_without_key_uses_open_meteo_and_does_not_invent(app_config: AppConfig) -> None:
    client = MagicMock()
    client.current.return_value = {
        "location": "Riyadh, Saudi Arabia",
        "description": "clear sky",
        "temperature_c": 34.0,
        "humidity": 10,
        "high_c": 37.0,
        "low_c": 24.0,
        "wind_kmh": 12.0,
    }
    result = WeatherTool(app_config, client=client).execute(WeatherArgs(location="Riyadh"))
    assert result.ok is True
    assert "34.0" in result.message
    assert "Riyadh" in result.message
    client.current.side_effect = ProviderError("The weather service timed out.")
    failed = WeatherTool(app_config, client=client).execute(WeatherArgs(location="Riyadh"))
    assert failed.ok is False
    assert "°C" not in failed.message


def test_weather_uses_default_city_and_reports_payload(app_config: AppConfig) -> None:
    app_config.default_city = "Riyadh"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "Riyadh"
        return httpx.Response(
            200,
            json={
                "name": "Riyadh",
                "weather": [{"description": "clear sky"}],
                "main": {"temp": 36.2, "humidity": 12},
            },
        )

    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    with patch("integrations.weather.openweathermap.httpx.Client", side_effect=factory):
        data = OpenWeatherMapClient("test-key", "https://example.test").current("Riyadh")
    assert data["temperature_c"] == 36.2
    tool = WeatherTool(app_config, client=MagicMock(current=lambda location: data))
    result = tool.execute(WeatherArgs())
    assert result.ok is True
    assert "Riyadh" in result.message


def test_weather_client_missing_key() -> None:
    with pytest.raises(ConfigurationError):
        OpenWeatherMapClient(None, "https://example.test").current("Riyadh")


def test_music_media_key_is_windows_only(app_config: AppConfig) -> None:
    tool = MusicTool(app_config)
    with patch("tools.music_tool.sys.platform", "linux"):
        result = tool.execute(MusicArgs(action="play_pause"))
    assert result.ok is False
    assert "Windows" in result.message


def test_music_open_requires_alias(app_config: AppConfig) -> None:
    result = MusicTool(app_config).execute(MusicArgs(action="open"))
    assert result.ok is False
    assert "music app" in result.message.lower()


def test_messaging_without_token(app_config: AppConfig) -> None:
    result = MessagingTool(app_config).execute(
        MessagingArgs(action="telegram", recipient="123", body="hello")
    )
    assert result.ok is False
    assert "TELEGRAM_BOT_TOKEN" in result.message


def test_email_draft_uses_mailto(app_config: AppConfig) -> None:
    with patch("integrations.messaging.email_draft.webbrowser.open") as opened:
        result = MessagingTool(app_config).execute(
            MessagingArgs(action="email_draft", recipient="a@example.com", subject="Hi", body="There")
        )
    assert result.ok is True
    opened.assert_called_once()
    assert opened.call_args.args[0].startswith("mailto:")


def test_vision_missing_file(app_config: AppConfig) -> None:
    result = VisionTool(app_config).execute(VisionArgs(action="ocr", image_path="C:\\missing.png"))
    assert result.ok is False


def test_vision_ocr_without_tesseract(app_config: AppConfig, tmp_path) -> None:
    image = tmp_path / "note.png"
    image.write_bytes(b"not-a-real-image")
    with patch("tools.vision_tool._find_tesseract", return_value=None):
        result = VisionTool(app_config).execute(VisionArgs(action="ocr", image_path=str(image)))
    assert result.ok is False
    assert "Tesseract" in result.message


def test_telegram_token_is_redacted() -> None:
    from app.logging_config import RedactingFilter

    token = "123456789:AAFakeTokenValueForTestsXXXX"
    assert token not in RedactingFilter([token]).redact(f"using {token}")
