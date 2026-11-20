"""Short Wikipedia summaries (free, no key): search for the best page, then its summary."""

from __future__ import annotations

import re
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from .common import SkillError

DESCRIPTION = "A 2-3 sentence Wikipedia summary of a person, place, thing or idea."
SEARCH_URL = "https://en.wikipedia.org/w/api.php"
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
MAX_SENTENCES = 3
MAX_CHARS = 400


class NeedsContact(Exception):
    """Wikipedia refused us (403): its rules require a contact link in the app name."""


def _check(r: httpx.Response) -> None:
    if r.status_code == 403:
        raise NeedsContact()
    r.raise_for_status()


class WikiInput(BaseModel):
    topic: str = Field(min_length=1, max_length=100)


def _shorten(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out = ""
    for s in sentences[:MAX_SENTENCES]:
        if out and len(out) + len(s) > MAX_CHARS:
            break
        out = f"{out} {s}".strip()
    return out[:MAX_CHARS]


def summary(client: httpx.Client, topic: str) -> str:
    WikiInput(topic=topic)
    r = client.get(SEARCH_URL, params={
        "action": "query", "list": "search", "srsearch": topic, "srlimit": 1,
        "format": "json", "formatversion": 2,
    })
    _check(r)
    hits = r.json().get("query", {}).get("search", [])
    if not hits:
        raise SkillError(f"I couldn't find anything on Wikipedia about {topic}.")
    title = hits[0]["title"]
    r = client.get(SUMMARY_URL + quote(title.replace(" ", "_"), safe=""))
    _check(r)
    extract = r.json().get("extract", "").strip()
    if not extract:
        raise SkillError(f"Wikipedia has a page on {title}, but no summary.")
    return _shorten(extract)
