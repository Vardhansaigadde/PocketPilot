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
import threading
import time
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Callable, Iterable

log = logging.getLogger("pocketpilot.smart_click")

# Control kinds we can click, and how much we trust a match on each kind
# (a list row beats a plain text label with the same name).
CLICKABLE = {
    "Button": 1.0, "Hyperlink": 1.0, "MenuItem": 1.0, "TabItem": 1.0, "SplitButton": 1.0,
    "ListItem": 1.0, "TreeItem": 1.0, "DataItem": 1.0, "CheckBox": 0.97, "RadioButton": 0.97,
    "ComboBox": 0.95, "Edit": 0.95, "OCR text": 0.95, "Text": 0.9, "Image": 0.85,
}
MIN_SCORE = 0.6
WAKE_BELOW = 10          # fewer named controls than this on the first pass -> ask again
UIA_BUDGET_S = 2.0       # windows slower than this (huge WhatsApp chats) -> use OCR instead
SLOW_MEMORY_S = 120.0    # remember a slow window for this long

# Words in a button name that mean "ask on the phone first".
RISKY = re.compile(
    r"\b(send|delete|remove|erase|discard|pay|payment|buy|purchase|order|checkout|check out|"
    r"sign ?in|log ?in|sign ?out|log ?out|submit|confirm|install|uninstall|transfer|"
    r"unsubscribe|post|publish|reset|format|"
    # closing / leaving things can lose work or end a call
    r"close|exit|quit|don'?t save|do not save|leave|end call|hang up|block|report|archive|"
    r"restart|shut ?down|sign off)\b",
    re.I,
)

_DROP = re.compile(r"\b(the|a|an|button|link|tab|icon|option|menu item|please)\b", re.I)

# Never treat these as "close enough" to each other.
_OPPOSITES = [("show", "hide"), ("open", "close"), ("on", "off"), ("enable", "disable"),
              ("start", "stop"), ("add", "remove"), ("next", "previous"), ("up", "down"),
              ("in", "out"), ("lock", "unlock"), ("mute", "unmute"), ("yes", "no"),
              ("accept", "reject"), ("accept", "decline"), ("allow", "block"), ("allow", "deny"),
              ("increase", "decrease"), ("expand", "collapse"), ("maximize", "minimize"),
              ("follow", "unfollow"), ("like", "unlike"), ("pin", "unpin"),
              ("subscribe", "unsubscribe"), ("before", "after"), ("first", "last")]


@dataclass(frozen=True)
class Candidate:
    name: str
    kind: str                         # "Button", "Hyperlink", ... or "OCR text"
    rect: tuple[int, int, int, int]   # left, top, right, bottom (screen pixels)
    score: float = 1.0                # how well it matched what the user said (set by best_match)

    @property
    def center(self) -> tuple[int, int]:
        l, t, r, b = self.rect
        return (l + r) // 2, (t + b) // 2


def normalize(text: str) -> str:
    t = re.sub(r"[^\w\s+#.-]", " ", text.lower())
    return " ".join(t.split())


def clean_target(target: str) -> str:
    """'on the Sign in button' -> 'sign in' ("on" is only dropped at the start: "turn on" stays)."""
    t = re.sub(r"^on\s+", "", normalize(target))
    return " ".join(_DROP.sub(" ", t).split()) or normalize(target)


def _squash(s: str) -> str:
    return re.sub(r"[\s._-]", "", s)


def _collapse(s: str) -> str:
    """'kidduuu' -> 'kidu': speech-to-text often doubles or drops repeated letters."""
    return re.sub(r"(.)\1+", r"\1", s)


def _opposed(t: str, n: str) -> bool:
    tw, nw = set(t.split()), set(n.split())
    return any((x in tw and y in nw) or (y in tw and x in nw) for x, y in _OPPOSITES)


def _core(t: str, n: str) -> float:
    if n == t:
        return 1.0
    if _squash(n) == _squash(t):                 # "log in" / "login"
        return 0.95
    a, b = _collapse(_squash(t)), _collapse(_squash(n))
    if a == b:                                   # "kidd u" / "Kidduuu"
        return 0.92
    if len(t) >= 3 and n.startswith(t + " "):
        return 0.9
    if len(a) >= 4 and b.startswith(a):          # "kidd" / "Kidduuu"
        return 0.85
    if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", n):
        return 0.8 if len(t) >= 3 else 0.6
    if a and b and a[0] == b[0]:                 # close spelling, same first sound
        ratio = SequenceMatcher(None, a, b).ratio()
        if ratio >= 0.8:
            return 0.6 + (ratio - 0.8) * 1.5     # 0.6 .. 0.9
    return 0.0


def score(target: str, name: str) -> float:
    """How well a control's name matches what the user said (0..1).

    Forgiving about speech-to-text spelling ("kidd u" finds "Kidduuu", "log in" finds
    "Login") but never across opposite words ("show sidebar" never finds "Hide sidebar").
    Long labels such as a chat row "Kidduuu 🎀 Yesterday ..." are matched by their first words.
    """
    t, n = clean_target(target), normalize(name)
    if not t or not n or _opposed(normalize(target), n):
        return 0.0
    best = _core(t, n)
    words = n.split()
    for k in range(1, min(len(words), len(t.split()) + 2) + 1):
        best = max(best, _core(t, " ".join(words[:k])) * 0.98)
    return best


def best_match(target: str, candidates: Iterable[Candidate]) -> Candidate | None:
    """The best-matching candidate (with its score), or None if nothing is close enough."""
    best: tuple[float, int, int, int] | None = None
    winner: Candidate | None = None
    for c in candidates:
        s = score(target, c.name)
        if s < MIN_SCORE:
            continue
        # Plain text and long labels (paragraphs, chat messages) only count on a strong
        # match of the whole label or its first words, never "contains the words somewhere".
        if (c.kind in ("Text", "Image") or len(c.name) > 40) and s < 0.88:
            continue
        key = (s * CLICKABLE.get(c.kind, 0.9), -len(c.name), -c.rect[1], -c.rect[0])
        if best is None or key > best:
            best, winner = key, replace(c, score=round(s, 3))
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
        window_id: Callable[[], int] | None = None,
        budget_s: float = UIA_BUDGET_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.uia = uia
        self.ocr_words = ocr_words if ocr_words is not None else _screen_words
        self.window_id = window_id or (lambda: int(ctypes.windll.user32.GetForegroundWindow() or 0))
        self.budget_s = budget_s
        self.clock = clock
        self._slow_until: dict[int, float] = {}

    def find(self, target: str) -> Candidate | None:
        hit = best_match(target, self._uia_in_time())
        if hit is not None:
            return hit
        try:
            return best_match(target, ocr_candidates(self.ocr_words()))
        except Exception:
            log.exception("OCR failed")
            return None

    def visible_names(self, limit: int = 40) -> str:
        """Short screen description for the task agent: window title + clickable names."""
        title = ""
        try:
            buf = ctypes.create_unicode_buffer(200)
            ctypes.windll.user32.GetWindowTextW(self.window_id(), buf, 200)
            title = buf.value
        except Exception:  # pragma: no cover - non-Windows
            pass
        names: list[str] = []
        for c in sorted(self._uia_in_time(), key=lambda c: (c.rect[1] // 20, c.rect[0])):
            name = " ".join(c.name.split())[:40]
            if name and name not in names:
                names.append(name)
        if not names:
            try:
                names = [" ".join(w.name.split()) for w in ocr_candidates(self.ocr_words()) if " " not in w.name]
            except Exception:
                log.exception("OCR failed")
        shown = " | ".join(names[:limit]) or "(nothing readable)"
        return f"window '{title}'; visible: {shown}"

    def _uia_in_time(self) -> list[Candidate]:
        """UI Automation, but give up after budget_s (then OCR is used instead).

        Some windows are huge (a WhatsApp chat can have 20,000 elements and take
        15 s); those are remembered for a while and go straight to OCR.
        """
        win = self.window_id()
        if self._slow_until.get(win, 0.0) > self.clock():
            return []
        result: list[list[Candidate]] = []

        def run() -> None:
            try:
                result.append(self.uia())
            except Exception:
                log.exception("UI Automation failed; trying OCR")
                result.append([])

        worker = threading.Thread(target=run, name="uia-find", daemon=True)
        worker.start()
        worker.join(self.budget_s)
        if not result:
            log.info("window too slow for UI Automation; using OCR")
            self._slow_until[win] = self.clock() + SLOW_MEMORY_S
            return []
        return result[0]


def _screen_words() -> list:
    from .screen import capture, ocr

    return ocr(capture(), words=True)
