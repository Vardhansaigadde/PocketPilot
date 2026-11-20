"""Skills: small tools the assistant can use. Free, no API keys.

Each skill module has a DESCRIPTION (for the AI planner), a Pydantic input
model, one function, and tests that use a fake HTTP transport.
`WebSkills` bundles them for the executor.
"""

from __future__ import annotations

import logging
from typing import Callable

import httpx

from . import air_quality, weather, web_search, websites, wikipedia
from .common import SkillError

log = logging.getLogger("pocketpilot.skills")

USER_AGENT = "PocketPilot/0.2"


def user_agent(contact: str | None = None) -> str:
    """Wikipedia only answers apps that name a contact link (e.g. your GitHub repo)."""
    extra = f" ({contact})" if contact else " (personal voice assistant)"
    return f"{USER_AGENT}{extra} python-httpx/{httpx.__version__}"


def make_client(transport: httpx.BaseTransport | None = None, contact: str | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(8.0, connect=5.0),
        headers={"User-Agent": user_agent(contact)},
        transport=transport,
        follow_redirects=True,
    )


class WebSkills:
    """What the executor calls. Turns failures into short spoken sentences."""

    def __init__(
        self,
        client: httpx.Client,
        open_url: Callable[[str], None],
        home_city: str | None = None,
        amazon_domain: str = "www.amazon.in",
        open_app_link: Callable[[str], None] | None = None,
        app_available: Callable[[str], bool] = lambda target: False,
    ) -> None:
        self.client = client
        self.open_url = open_url
        self.home_city = home_city
        self.amazon_domain = amazon_domain
        self.open_app_link = open_app_link
        self.app_available = app_available

    def _place(self, place: str | None) -> str | None:
        return (place or self.home_city or "").strip() or None

    def _safe(self, fn: Callable[[], str], what: str) -> str:
        try:
            return fn()
        except SkillError as exc:
            return str(exc)
        except httpx.HTTPError:
            log.exception("%s request failed", what)
            return f"I couldn't get the {what} right now. Is the internet on?"

    def weather(self, place: str | None) -> str:
        where = self._place(place)
        if not where:
            return "Which city? Say: weather in Hyderabad. Or set POCKETPILOT_HOME_CITY in .env."
        return self._safe(lambda: weather.weather(self.client, where), "weather")

    def air_quality(self, place: str | None) -> str:
        where = self._place(place)
        if not where:
            return "Which city? Say: air quality in Hyderabad."
        return self._safe(lambda: air_quality.air_quality(self.client, where), "air quality")

    def wiki(self, topic: str) -> str:
        try:
            return self._safe(lambda: wikipedia.summary(self.client, topic), "Wikipedia summary")
        except wikipedia.NeedsContact:
            return ("Wikipedia needs a contact link. Put your GitHub repo URL in .env as "
                    "POCKETPILOT_CONTACT=https://github.com/you/pocketpilot")

    def open_site(self, site: str) -> str:
        url = websites.resolve(site)
        if url is None:
            return (f"I don't know the website {site}. Say its address, "
                    "like github.com or codechef.com.")
        self.open_url(url)
        return f"Opening {websites.label(url)}."

    def search(self, site: str, query: str) -> str:
        if site == "spotify" and self.open_app_link and self.app_available("spotify:"):
            self.open_app_link(web_search.spotify_app_link(query))   # Spotify app installed
            return web_search.spoken(site, query)
        url = web_search.search_url(site, query, amazon_domain=self.amazon_domain)
        self.open_url(url)
        return web_search.spoken(site, query)
