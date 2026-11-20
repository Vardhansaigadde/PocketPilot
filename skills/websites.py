"""Open a website by name ("github", "chatgpt") or by address ("github.com/user/repo").

Safety: the result is always a plain https:// address built here. Only letters,
digits and normal URL characters are allowed, so nothing else (files, scripts,
programs, other protocols) can be opened this way.
"""

from __future__ import annotations

import re

DESCRIPTION = "Open a website in the browser by its name (github, chatgpt, codechef) or address (example.com/page)."

# Spoken name -> address. Keys are lowercase with spaces removed.
SITES: dict[str, str] = {
    "github": "github.com",
    "chatgpt": "chatgpt.com",
    "openai": "chatgpt.com",
    "codechef": "www.codechef.com",
    "leetcode": "leetcode.com",
    "hackerrank": "www.hackerrank.com",
    "codeforces": "codeforces.com",
    "geeksforgeeks": "www.geeksforgeeks.org",
    "gfg": "www.geeksforgeeks.org",
    "stackoverflow": "stackoverflow.com",
    "youtube": "www.youtube.com",
    "google": "www.google.com",
    "gmail": "mail.google.com",
    "googledrive": "drive.google.com",
    "drive": "drive.google.com",
    "googledocs": "docs.google.com",
    "googlemaps": "maps.google.com",
    "maps": "maps.google.com",
    "bing": "www.bing.com",
    "wikipedia": "en.wikipedia.org",
    "linkedin": "www.linkedin.com",
    "instagram": "www.instagram.com",
    "facebook": "www.facebook.com",
    "twitter": "x.com",
    "x": "x.com",
    "reddit": "www.reddit.com",
    "whatsappweb": "web.whatsapp.com",
    "amazon": "www.amazon.in",
    "flipkart": "www.flipkart.com",
    "netflix": "www.netflix.com",
    "spotifyweb": "open.spotify.com",
    "claude": "claude.ai",
    "gemini": "gemini.google.com",
    "kaggle": "www.kaggle.com",
    "coursera": "www.coursera.org",
    "udemy": "www.udemy.com",
    "w3schools": "www.w3schools.com",
}

# Words speech-to-text puts around names ("the github website", "git hub").
_FILLER = re.compile(r"\b(?:the|website|web site|site|page|homepage|home page|web page|please|my)\b", re.I)

_DOMAIN = re.compile(
    r"^(?P<host>(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})"
    r"(?P<path>/[a-z0-9/_\-.~%+=&?#]*)?$",
    re.I,
)

LABELS = {"github.com": "GitHub", "chatgpt.com": "ChatGPT", "www.codechef.com": "CodeChef",
          "www.youtube.com": "YouTube", "leetcode.com": "LeetCode", "mail.google.com": "Gmail"}


def spoken_to_address(text: str) -> str:
    """'github dot com slash user' -> 'github.com/user' (keeps upper/lower case of paths)."""
    t = text.strip().strip(" .!?,")
    t = re.sub(r"\s+dot\s+", ".", t, flags=re.I)
    t = re.sub(r"\s*\bslash\b\s*", "/", t, flags=re.I)
    t = re.sub(r"\s*/\s*", "/", t)
    t = re.sub(r"\s*\.\s*", ".", t)
    return t


def resolve(text: str) -> str | None:
    """Turn what the user said into a safe https URL, or None if it isn't a website."""
    if not text or len(text) > 200:
        return None
    t = spoken_to_address(text)
    # Any scheme other than http(s) (file:, javascript:, data:, C:\ ...) is refused.
    if re.match(r"^[a-z][a-z0-9+.-]*:", t, re.I) and not re.match(r"^https?://", t, re.I):
        return None
    t = re.sub(r"^https?://", "", t, flags=re.I)

    # A known site name? ("git hub", "the chatgpt website")
    name = re.sub(r"\s+", "", _FILLER.sub(" ", t.lower()))
    if name in SITES:
        return "https://" + SITES[name]

    if " " in t:
        return None
    host, sep, path = t.partition("/")
    path = sep + path
    # A name with a path, e.g. "github/vardhansaigadde"
    if host.lower() in SITES and path and _DOMAIN.match(SITES[host.lower()] + path):
        return f"https://{SITES[host.lower()]}{path}"
    # A real address with a dot in the host: example.org, github.com/user/repo
    if "." in host and _DOMAIN.match(host + path):
        return f"https://{host.lower()}{path}"
    return None


def label(url: str) -> str:
    host = url.removeprefix("https://").split("/")[0]
    rest = url.removeprefix("https://")[len(host):].strip("/")
    name = LABELS.get(host, host.removeprefix("www."))
    return f"{name}/{rest}" if rest else name
