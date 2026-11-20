"""Smart click: "click the Login button" -> find that control on screen and click it.

1. Windows UI Automation (pywinauto) lists the named buttons, links, tabs... of
   the active window. Fast and exact. Chromium apps (Edge, Chrome, VS Code,
   WhatsApp) only share their full list after being asked once, so we ask twice.
2. If nothing matches, Windows OCR reads the visible text and we click the words.
3. Otherwise we say so, and the numbered grid is the fallback.

Buttons whose name sounds risky (send, delete, pay, sign in...) are never
clicked straight away: the executor asks for Approve on the phone first.
"""

from __future__ import annotations

import ctypes
import logging
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Iterable

log = logging.getLogger("pocketpilot.smart_click")

CLICKABLE = {
    "Button": 1.0, "Hyperlink": 1.0, "MenuItem": 1.0, "TabItem": 1.0, "SplitButton": 1.0,
    "ListItem": 0.95, "TreeItem": 0.95, "CheckBox": 0.95, "RadioButton": 0.95,
    "ComboBox": 0.9, "Edit": 0.9, "DataItem": 0.9, "Text": 0.85, "Image": 0.8,
}
MIN_SCORE = 0.6
WAKE_BELOW = 10          # fewer named controls than this on the first pass -> ask again

# Words in a button name that mean "ask on the phone first".
RISKY = re.compile(
    r"\b(send|delete|remove|erase|discard|pay|payment|buy|purchase|order|checkout|check out|"
    r"sign ?in|log ?in|sign ?out|log ?out|submit|confirm|install|uninstall|transfer|"
    r"unsubscribe|post|publish|reset|format)\b",
    re.I,
)

_DROP = re.compile(r"\b(the|a|an|button|link|tab|icon|option|menu item|on|please)\b", re.I)


@dataclass(frozen=True)
class Candidate:
    name: str
    kind: str                         # "Button", "Hyperlink", ... or "OCR text"
    rect: tuple[int, int, int, int]   # left, top, right, bottom (screen pixels)

    @property
    def center(self) -> tuple[int, int]:
        l, t, r, b = self.rect
        return (l + r) // 2, (t + b) // 2


def normalize(text: str) -> str:
    t = re.sub(r"[^\w\s+#.-]", " ", text.lower())
    return " ".join(t.split())


def clean_target(target: str) -> str:
    """'the Sign in button' -> 'sign in'."""
    return " ".join(_DROP.sub(" ", normalize(target)).split()) or normalize(target)


def score(target: str, name: str) -> float:
    """How well a control's name matches what the user said (0..1).

    Strict on purpose: "show sidebar" must not match "Hide sidebar". Only small
    speech-to-text differences ("log in" / "login", "sign-in" / "sign in") are forgiven.
    """
    t, n = clean_target(target), normalize(name)
    if not t or not n:
        return 0.0
    if n == t:
        return 1.0
    squash = lambda s: re.sub(r"[\s.-]", "", s)  # noqa: E731
    if squash(n) == squash(t):
        return 0.95
    if len(t) >= 3 and n.startswith(t + " "):
        return 0.9
    if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", n):
        return 0.8 if len(t) >= 3 else 0.6
    ratio = SequenceMatcher(None, t, n).ratio()
    return ratio * 0.8 if ratio >= 0.9 else 0.0


def best_match(target: str, candidates: Iterable[Candidate]) -> Candidate | None:
    """The best-matching candidate, or None if nothing is close enough.
    Ties go to the more clickable kind, then the shorter name, then top-left."""
    best: tuple[float, float, int, int, int] | None = None
    winner: Candidate | None = None
    for c in candidates:
        s = score(target, c.name)
        if s < MIN_SCORE:
            continue
        # Plain text and long labels (paragraphs, chat messages) only count when the
        # whole label matches, not when it merely contains the words somewhere.
        if (c.kind in ("Text", "Image") or len(c.name) > 40) and s < 0.9:
            continue
        key = (s, CLICKABLE.get(c.kind, 0.85), -len(c.name), -c.rect[1], -c.rect[0])
        if best is None or key > best:
            best, winner = key, c
    return winner


def is_risky(name: str) -> bool:
    return bool(RISKY.search(name))


# ---- where candidates come from ------------------------------------------------------------

def uia_candidates(hwnd: int | None = None, sleep: Callable[[float], None] = time.sleep) -> list[Candidate]:
    """Named, visible, enabled controls of the active window (UI Automation).

    Uses one cached request for the whole window (~0.2 s) instead of asking for
    every property of every control separately (~2 s on big apps).
    """
    from pywinauto.uia_defines import IUIA

    hwnd = hwnd or ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return []
    ia = IUIA()
    iuia, uia = ia.iuia, ia.UIA_dll
    kinds = {v: k for k, v in ia.known_control_types.items()}
    request = iuia.CreateCacheRequest()
    for prop in (uia.UIA_NamePropertyId, uia.UIA_ControlTypePropertyId, uia.UIA_BoundingRectanglePropertyId,
                 uia.UIA_IsOffscreenPropertyId, uia.UIA_IsEnabledPropertyId):
        request.AddProperty(prop)

    def collect() -> list[Candidate]:
        found = iuia.ElementFromHandle(hwnd).FindAllBuildCache(
            uia.TreeScope_Descendants, iuia.CreateTrueCondition(), request)
        out = []
        for i in range(found.Length):
            try:
                e = found.GetElement(i)
                name, kind = (e.CachedName or "").strip(), kinds.get(e.CachedControlType, "")
                if not name or kind not in CLICKABLE or e.CachedIsOffscreen or not e.CachedIsEnabled:
                    continue
                r = e.CachedBoundingRectangle
                if r.right - r.left < 3 or r.bottom - r.top < 3:
                    continue
                out.append(Candidate(name, kind, (r.left, r.top, r.right, r.bottom)))
            except Exception:  # an element can vanish while we read it
                continue
        return out

    found = collect()
    if len(found) < WAKE_BELOW:          # Chromium apps wake up after the first request
        sleep(0.3)
        found = collect()
    return found


def ocr_candidates(boxes: list) -> list[Candidate]:
    """OCR words -> candidates for every run of 1-5 consecutive words on a line."""
    out: list[Candidate] = []
    words = sorted(boxes, key=lambda b: (b.y // 10, b.x))
    for i in range(len(words)):
        line_y = words[i].y
        for j in range(i, min(i + 5, len(words))):
            if abs(words[j].y - line_y) > max(words[i].h, 8):
                break
            run = words[i:j + 1]
            text = " ".join(w.text for w in run)
            left = min(w.x for w in run)
            top = min(w.y for w in run)
            right = max(w.x + w.w for w in run)
            bottom = max(w.y + w.h for w in run)
            out.append(Candidate(text, "OCR text", (left, top, right, bottom)))
    return out


class SmartClicker:
    """Finds what to click. The sources are passed in, so tests can use fakes."""

    def __init__(
        self,
        uia: Callable[[], list[Candidate]] = uia_candidates,
        ocr_words: Callable[[], list] | None = None,
    ) -> None:
        self.uia = uia
        self.ocr_words = ocr_words if ocr_words is not None else _screen_words

    def find(self, target: str) -> Candidate | None:
        try:
            hit = best_match(target, self.uia())
            if hit is not None:
                return hit
        except Exception:
            log.exception("UI Automation failed; trying OCR")
        try:
            return best_match(target, ocr_candidates(self.ocr_words()))
        except Exception:
            log.exception("OCR failed")
            return None


def _screen_words() -> list:
    from .screen import capture, ocr

    return ocr(capture(), words=True)
