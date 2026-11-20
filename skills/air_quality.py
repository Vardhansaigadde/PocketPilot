"""Air quality (US AQI + PM2.5) with simple advice (Open-Meteo Air Quality, free, no key)."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from .common import find_place

DESCRIPTION = "Current air quality index (AQI) and PM2.5 for a city, with simple advice."
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


class AirInput(BaseModel):
    place: str = Field(min_length=1, max_length=80)


_LEVELS = [
    (50, "good", "Fine to be outside."),
    (100, "moderate", "OK for most people."),
    (150, "unhealthy for sensitive people", "If you have asthma, limit time outside."),
    (200, "unhealthy", "Wear a mask outside and keep windows closed."),
    (300, "very unhealthy", "Stay indoors if you can."),
    (10_000, "hazardous", "Stay indoors and avoid outdoor exercise."),
]


def level(aqi: float) -> tuple[str, str]:
    for top, name, advice in _LEVELS:
        if aqi <= top:
            return name, advice
    return _LEVELS[-1][1], _LEVELS[-1][2]  # pragma: no cover


def air_quality(client: httpx.Client, place: str) -> str:
    AirInput(place=place)
    p = find_place(client, place)
    r = client.get(AIR_URL, params={
        "latitude": p.latitude, "longitude": p.longitude,
        "current": "us_aqi,pm2_5", "timezone": "auto",
    })
    r.raise_for_status()
    cur = r.json()["current"]
    aqi = cur.get("us_aqi")
    if aqi is None:
        return f"No air quality data for {p.name} right now."
    name, advice = level(aqi)
    pm = cur.get("pm2_5")
    pm_text = f", PM2.5 {round(pm)}" if pm is not None else ""
    return f"Air quality in {p.name} is {name}: AQI {round(aqi)}{pm_text}. {advice}"
