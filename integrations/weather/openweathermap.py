"""OpenWeatherMap current-weather client. Never invents data."""

from __future__ import annotations

import httpx

from app.errors import ConfigurationError, ProviderError, ProviderTimeoutError


class OpenWeatherMapClient:
    def __init__(self, api_key: str | None, base_url: str, timeout: float = 15.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def current(self, location: str) -> dict:
        if not self.api_key:
            raise ConfigurationError(
                "WEATHER_API_KEY is not set. Add it to .env to enable weather."
            )
        url = f"{self.base_url}/weather"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    url,
                    params={"q": location, "appid": self.api_key, "units": "metric"},
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The weather service timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach the weather service: {exc}") from exc
        if response.status_code == 401:
            raise ConfigurationError("The weather service rejected WEATHER_API_KEY.")
        if response.status_code == 404:
            raise ProviderError(f"No weather location matched '{location}'.")
        if response.status_code >= 400:
            raise ProviderError(f"Weather service error ({response.status_code}).")
        try:
            payload = response.json()
            weather = payload["weather"][0]
            main = payload["main"]
            return {
                "location": payload.get("name") or location,
                "description": weather.get("description", ""),
                "temperature_c": main["temp"],
                "humidity": main.get("humidity"),
            }
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("The weather service returned an unexpected response.") from exc
