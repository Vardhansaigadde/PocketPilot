"""Open Edge on a search results page (Bing, Google, YouTube or Amazon).

Only builds a search URL with the query safely encoded. It never logs in, buys,
books or clicks anything on the page.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote, quote_plus

from pydantic import BaseModel, Field

DESCRIPTION = "Search Bing, Google, YouTube, Amazon, GitHub or Spotify (songs), or ask ChatGPT a question."

Site = Literal["bing", "google", "youtube", "amazon", "github", "chatgpt", "spotify"]
_LABEL = {"bing": "the web", "google": "Google", "youtube": "YouTube", "amazon": "Amazon",
          "github": "GitHub", "chatgpt": "ChatGPT", "spotify": "Spotify"}


class SearchInput(BaseModel):
    site: Site = "bing"
    query: str = Field(min_length=1, max_length=200)


def search_url(site: str, query: str, amazon_domain: str = "www.amazon.in") -> str:
    s = SearchInput(site=site, query=query)
    q = quote_plus(s.query.strip())
    if s.site == "youtube":
        return f"https://www.youtube.com/results?search_query={q}"
    if s.site == "amazon":
        return f"https://{amazon_domain}/s?k={q}"
    if s.site == "spotify":
        return f"https://open.spotify.com/search/{quote(s.query.strip(), safe='')}"
    if s.site == "github":
        return f"https://github.com/search?q={q}"
    if s.site == "chatgpt":
        return f"https://chatgpt.com/?q={q}"   # opens ChatGPT with your question
    if s.site == "google":
        return f"https://www.google.com/search?q={q}"
    return f"https://www.bing.com/search?q={q}"


def spoken(site: str, query: str) -> str:
    if site == "chatgpt":
        return f"Asking ChatGPT: {query}"
    return f"Searching {_LABEL.get(site, 'the web')} for {query}."


def spotify_app_link(query: str) -> str:
    """Search link for the Spotify desktop app."""
    return "spotify:search:" + quote(SearchInput(site="spotify", query=query).query.strip(), safe="")


def open_in_edge(url: str) -> None:
    """Open a URL in Microsoft Edge (Windows). Only https URLs built above are allowed."""
    import os

    if not url.startswith("https://"):
        raise ValueError("only https search URLs can be opened")
    os.startfile("microsoft-edge:" + url)  # type: ignore[attr-defined]
