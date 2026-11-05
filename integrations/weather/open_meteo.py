"""Open-Meteo current weather. No API key. Never invents data."""

from __future__ import annotations

import httpx

from app.errors import ProviderError, ProviderTimeoutError

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"

_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    85: "light snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}


class OpenMeteoClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def current(self, location: str) -> dict:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                geo = client.get(
                    _GEOCODE,
                    params={"name": location, "count": 1, "language": "en", "format": "json"},
                )
                if geo.status_code >= 400:
                    raise ProviderError(f"Weather lookup failed ({geo.status_code}).")
                results = geo.json().get("results") or []
                if not results:
                    raise ProviderError(f"No weather location matched '{location}'.")
                place = results[0]
                forecast = client.get(
                    _FORECAST,
                    params={
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                        "daily": "temperature_2m_max,temperature_2m_min",
                        "timezone": "auto",
                        "forecast_days": 1,
                    },
                )
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The weather service timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Could not reach the weather service: {exc}") from exc
        if forecast.status_code >= 400:
            raise ProviderError(f"Weather service error ({forecast.status_code}).")
        try:
            payload = forecast.json()
            current = payload["current"]
            daily = payload.get("daily") or {}
            code = int(current["weather_code"])
            name = place.get("name") or location
            country = place.get("country")
            label = f"{name}, {country}" if country else name
            return {
                "location": label,
                "description": _CODES.get(code, "unknown conditions"),
                "temperature_c": current["temperature_2m"],
                "humidity": current.get("relative_humidity_2m"),
                "wind_kmh": current.get("wind_speed_10m"),
                "high_c": (daily.get("temperature_2m_max") or [None])[0],
                "low_c": (daily.get("temperature_2m_min") or [None])[0],
            }
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("The weather service returned an unexpected response.") from exc
