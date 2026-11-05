"""Current weather through the configured provider."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import AppConfig
from app.errors import OrionError
from core.permissions import RiskLevel
from integrations.weather.open_meteo import OpenMeteoClient
from integrations.weather.openweathermap import OpenWeatherMapClient
from tools.base_tool import BaseTool, ToolResult


class WeatherArgs(BaseModel):
    location: str | None = Field(default=None, description="City name. Uses the saved city if omitted.")


class WeatherTool(BaseTool):
    name = "weather"
    description = (
        "Get the live weather for a city: conditions, temperature, humidity, and today's high and low. "
        "Does not guess when the service fails."
    )
    risk = RiskLevel.LOW

    def __init__(self, config: AppConfig, client: OpenWeatherMapClient | OpenMeteoClient | None = None) -> None:
        self.config = config
        if client is not None:
            self.client = client
        elif config.weather_api_key:
            self.client = OpenWeatherMapClient(
                config.weather_api_key,
                config.weather_base_url,
                timeout=min(config.request_timeout_seconds, 20),
            )
        else:
            self.client = OpenMeteoClient(timeout=min(config.request_timeout_seconds, 20))

    @property
    def input_schema(self) -> type[BaseModel]:
        return WeatherArgs

    def execute(self, arguments: BaseModel) -> ToolResult:
        if not isinstance(arguments, WeatherArgs):
            arguments = WeatherArgs.model_validate(arguments)
        location = (arguments.location or self.config.default_city or "").strip()
        if not location:
            return ToolResult(
                ok=False,
                message="Which city? Tell me a location or set a default city in Settings.",
            )
        try:
            data = self.client.current(location)
        except OrionError as exc:
            return ToolResult(ok=False, message=str(exc))
        message = (
            f"{data['location']}: {data['description']}, {data['temperature_c']}°C"
            + (f", humidity {data['humidity']}%" if data.get("humidity") is not None else "")
        )
        if data.get("high_c") is not None and data.get("low_c") is not None:
            message += f". Today {data['low_c']}°C to {data['high_c']}°C"
        if data.get("wind_kmh") is not None:
            message += f", wind {data['wind_kmh']} km/h"
        return ToolResult(ok=True, message=message, data=data)
