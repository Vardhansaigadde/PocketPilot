"""Pick the Nth search result or video on screen ("play the second video", "open the first result").

Reads the page through Windows UI Automation (the same controls smart click uses) and keeps
only real results, counted top to bottom, then left to right, among what is on screen now.
After you scroll, "the second video" is the second one you can see.

What counts as a result (checked on Edge):
- YouTube: a video title link. Its name ends with the length ("... 4 minutes, 11 seconds");
  ads, the menu on the left, playlists ("Mix - ...") and channel names have none.
- Google: a link that has the web address inside it ("Python Tutorial W3Schools https://...").
- Bing: the title link of a result box that shows a web address ("https://www...").
- Ads ("Sponsored") are skipped everywhere.
"""

from __future__ import annotations

import re
from typing import Literal

from .smart_click import Candidate

Kind = Literal["result", "video", "link"]

DURATION = re.compile(r"\b\d+\s*(?:hours?|minutes?|mins?|seconds?|secs?)\b", re.I)
_ADDRESS = re.compile(r"https?://|\bwww\.|›")
_VIDEO_SITE = re.compile(r"\b(?:youtube|vimeo|dailymotion)\b", re.I)
# The end of a link name that isn't the title: views, length, "YouTube <channel> <date>".
_TITLE_END = re.compile(
    r"(?:\s+by\s.+?)?\s+\d[\d.,]*[kmb]?\s+views\b.*$"
    r"|\s+\d+\s*(?:hours?|minutes?|seconds?)(?:,?\s*\d+\s*(?:hours?|minutes?|seconds?|sec\w*|min\w*))*\s*$"
    r"|\s+YouTube\s.*$",
    re.I,
)
MIN_W, MIN_H, MIN_NAME = 120, 14, 8
MIN_BOX_W = 500             # a Bing result box; narrower boxes are side cards
ADDRESS_WITHIN = 40         # the address must come right after the site name
# AI answers and page furniture, never a result
_NOT_RESULT = re.compile(r"copilot|ai overview|ai mode|ai summary|sign in|feedback", re.I)


def _inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
    return (outer[0] - 2 <= inner[0] and outer[1] - 2 <= inner[1]
            and inner[2] <= outer[2] + 2 and inner[3] <= outer[3] + 2)


def _big_link(c: Candidate) -> bool:
    l, t, r, b = c.rect
    return (c.kind == "Hyperlink" and r - l >= MIN_W and b - t >= MIN_H and len(c.name.strip()) >= MIN_NAME
            and not _NOT_RESULT.search(c.name))


def _is_ad(link: Candidate, texts: list[Candidate], boxes: list[Candidate]) -> bool:
    """A "Sponsored" label in the same result box, or just above the link."""
    sponsored = [t for t in texts if t.name.strip().lower() in ("sponsored", "ad", "ads")]
    if not sponsored:
        return False
    box = _smallest_box(link, boxes)
    for s in sponsored:
        if box is not None and _inside(s.rect, box.rect):
            return True
        above = 0 <= link.rect[1] - s.rect[3] <= 60
        overlap = s.rect[0] < link.rect[2] and link.rect[0] < s.rect[2]
        if above and overlap:
            return True
    return False


def _smallest_box(link: Candidate, boxes: list[Candidate]) -> Candidate | None:
    around = [b for b in boxes if _inside(link.rect, b.rect)]
    return min(around, key=lambda b: (b.rect[2] - b.rect[0]) * (b.rect[3] - b.rect[1]), default=None)


def _order(cands: list[Candidate]) -> list[Candidate]:
    """Top to bottom, then left to right (a row of YouTube videos reads left to right)."""
    out: list[Candidate] = []
    for c in sorted(cands, key=lambda c: (c.rect[1] // 40, c.rect[0], c.rect[1])):
        if any(c.name == o.name and abs(c.rect[1] - o.rect[1]) < 40 for o in out):
            continue                                   # the same result read twice
        out.append(c)
    return out


def videos(cands: list[Candidate], on_youtube: bool = False) -> list[Candidate]:
    """Video links on screen: a length in the name ("4 minutes, 11 seconds"), or (on a search
    page) a video site in the name. On YouTube itself only a length counts: its ad player is
    called "YouTube Video Player"."""
    texts = [c for c in cands if c.kind == "Text"]
    boxes = [c for c in cands if c.kind == "ListItem"]

    def is_video(c: Candidate) -> bool:
        if DURATION.search(c.name):
            return True
        return not on_youtube and _video_site_link(c.name)

    found = [c for c in cands if _big_link(c) and is_video(c)
             and not c.name.lower().startswith("mix -") and not _is_ad(c, texts, boxes)]
    return _order(found)


def results(cands: list[Candidate]) -> list[Candidate]:
    """Search results on screen (Google, Bing and similar), ads skipped."""
    texts = [c for c in cands if c.kind == "Text"]
    boxes = [c for c in cands if c.kind == "ListItem"]
    links = sorted((c for c in cands if _big_link(c)), key=lambda c: (c.rect[1], c.rect[0]))
    found: list[Candidate] = []
    for link in links:                                 # Google: the address is part of the link
        if not _is_ad(link, texts, boxes) and (
                _ADDRESS.search(link.name) or DURATION.search(link.name) or _video_site_link(link.name)):
            found.append(link)
    taken = {f.rect for f in found}
    for box in boxes:                                  # Bing: a wide result box that shows an address
        if box.rect[2] - box.rect[0] < MIN_BOX_W:     # (the AI answer's source cards are narrow)
            continue
        # A result box starts with the site and its address ("W3Schoolhttps://www.w3schools.com › ...").
        # The AI answer box also holds addresses, but deep inside its long text.
        shows_address = _ADDRESS.search(box.name[:ADDRESS_WITHIN]) or any(
            t.name.strip().lower().startswith(("http", "www.")) and _smallest_box(t, boxes) is box
            for t in texts)                            # its own address, not one of a box inside it
        if not shows_address:
            continue
        inner = [l for l in links if l.rect not in taken and _smallest_box(l, boxes) is box]
        if not inner or _is_ad(inner[0], texts, boxes):
            continue
        # the title link has a text label of the same name; the site-name link above it doesn't
        titles = [l for l in inner if any(t.name.strip() == l.name.strip() and abs(t.rect[1] - l.rect[1]) < 8
                                          for t in texts)]
        found.append((titles or inner)[0])
    return _order(found)


def _video_site_link(name: str) -> bool:
    """'Python Full Course YouTube Programming with Mosh' yes; the 'YouTube Home' logo, the
    'YouTube Video Player' no."""
    if not _VIDEO_SITE.search(name) or "video player" in name.lower():
        return False
    return len(_VIDEO_SITE.sub("", name).replace("Home", "").strip()) >= 15


def pick(cands: list[Candidate], n: int, kind: Kind, page_title: str = "") -> tuple[Candidate | None, int]:
    """The nth (1-based; -1 = last) result or video on screen, and how many there are."""
    on_youtube = "youtube" in page_title.lower()
    if kind == "video" or on_youtube:
        found = videos(cands, on_youtube)
        if not found and not on_youtube:
            found = results(cands)                     # "second video" on a page of results
    else:
        found = results(cands) or videos(cands)
    if not found:
        return None, 0
    if n == -1:
        return found[-1], len(found)
    return (found[n - 1] if 1 <= n <= len(found) else None), len(found)


def short_title(name: str, limit: int = 60) -> str:
    """'Kesariya 8K Music Video | Arijit Singh 4 minutes, 11 seconds' -> 'Kesariya 8K Music Video | Arijit Singh'."""
    t = _TITLE_END.sub("", name.strip())
    t = re.split(r"\s+https?://|\s+www\.", t)[0].strip() or name.strip()
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def ordinal(n: int) -> str:
    if n == -1:
        return "last"
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
