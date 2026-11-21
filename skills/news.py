"""Top headlines (GNews, free key from gnews.io; set POCKETPILOT_GNEWS_KEY in .env)."""

from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, Field

from .common import SkillError

DESCRIPTION = "Today's top news headlines, or news about a topic."
TOP_URL = "https://gnews.io/api/v4/top-headlines"
SEARCH_URL = "https://gnews.io/api/v4/search"
NEEDS_KEY = ("News needs a free key: sign up at gnews.io, then put it in .env as "
             "POCKETPILOT_GNEWS_KEY=your-key and restart PocketPilot.")


class NewsInput(BaseModel):
    topic: str | None = Field(default=None, max_length=80)


def headlines(client: httpx.Client, key: str | None, topic: str | None = None, country: str = "in",
              sleep=time.sleep) -> str:
    if not key:
        raise SkillError(NEEDS_KEY)
    q = NewsInput(topic=(topic or "").strip() or None)
    params = {"lang": "en", "max": 5, "apikey": key}
    def ask() -> httpx.Response:
        if q.topic:
            return client.get(SEARCH_URL, params={**params, "q": q.topic})
        return client.get(TOP_URL, params={**params, "country": country})

    r = ask()
    if r.status_code == 429:          # the free plan also allows only ~1 request a second
        sleep(1.5)
        r = ask()
    if r.status_code in (401, 403):
        raise SkillError("The news key didn't work. Check POCKETPILOT_GNEWS_KEY in .env.")
    if r.status_code == 429:
        raise SkillError("The news service says the free limit is used up for now (100 a day). Try again later.")
    r.raise_for_status()
    titles = [a.get("title", "").strip() for a in r.json().get("articles", []) if a.get("title")]
    if not titles:
        return f"I couldn't find news about {q.topic}." if q.topic else "No headlines right now."
    head = f"News about {q.topic}" if q.topic else "Top news"
    return f"{head}: " + " ".join(f"{i}) {t.rstrip('.')}." for i, t in enumerate(titles[:3], 1))
