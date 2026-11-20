"""Weather now + today's rain chance and sunset (Open-Meteo, free, no key)."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from .common import find_place

DESCRIPTION = "Current weather, today's high/low, chance of rain and sunset time for a city."
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherInput(BaseModel):
    place: str = Field(min_length=1, max_length=80)


# WMO weather codes -> words
_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "cloudy",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "heavy showers", 85: "snow showers", 86: "snow showers", 95: "thunderstorms",
    96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def describe(code: int | None) -> str:
    return _CODES.get(int(code), "mixed weather") if code is not None else "unknown weather"


def _time(iso: str) -> str:
    """'2026-11-20T17:42' -> '5:42 PM'."""
    hh, mm = iso.split("T")[1][:5].split(":")
    h = int(hh)
    return f"{(h % 12) or 12}:{mm} {'AM' if h < 12 else 'PM'}"


def weather(client: httpx.Client, place: str) -> str:
    WeatherInput(place=place)
    p = find_place(client, place)
    r = client.get(FORECAST_URL, params={
        "latitude": p.latitude, "longitude": p.longitude,
        "current": "temperature_2m,apparent_temperature,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunset",
        "timezone": "auto", "forecast_days": 1,
    })
    r.raise_for_status()
    data = r.json()
    cur, day = data["current"], data["daily"]
    temp = round(cur["temperature_2m"])
    feels = round(cur["apparent_temperature"])
    now = f"{p.name}: {temp}°C and {describe(cur.get('weather_code'))}"
    if abs(feels - temp) >= 3:
        now += f", feels like {feels}°C"
    today = [f"Today {round(day['temperature_2m_min'][0])} to {round(day['temperature_2m_max'][0])}°C"]
    rain = (day.get("precipitation_probability_max") or [None])[0]
    if rain is not None:
        today.append(f"{rain}% chance of rain")
    if day.get("sunset"):
        today.append(f"sunset at {_time(day['sunset'][0])}")
    return f"{now}. {', '.join(today)}."
