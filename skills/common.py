"""Shared helpers for skills: city lookup (Open-Meteo geocoding, free, no key)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


class SkillError(Exception):
    """A problem worth telling the user about, e.g. "I couldn't find that city"."""


@dataclass(frozen=True)
class Place:
    name: str
    latitude: float
    longitude: float
    region: str = ""
    country: str = ""


def find_place(client: httpx.Client, name: str) -> Place:
    r = client.get(GEOCODE_URL, params={"name": name, "count": 1, "language": "en", "format": "json"})
    r.raise_for_status()
    results = r.json().get("results") or []
    if not results:
        raise SkillError(f"I couldn't find a place called {name}.")
    p = results[0]
    return Place(
        name=p.get("name", name),
        latitude=float(p["latitude"]),
        longitude=float(p["longitude"]),
        region=p.get("admin1", "") or "",
        country=p.get("country", "") or "",
    )
