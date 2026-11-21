"""Names PocketPilot has seen in your WhatsApp chat list, saved on the laptop.

Speech-to-text mishears names it doesn't know ("Kidduuu" -> "Kid do", "Kitya").
Every time PocketPilot reads WhatsApp's chat list it remembers the names there, so it
can (1) give them to Whisper as hints and (2) snap a misheard name to a real chat.
Stored in data/known_names.json (git-ignored, never uploaded).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path

from .smart_click import EMOJI_WORD_SET, emoji_to_words

log = logging.getLogger("pocketpilot.names")

MAX_NAMES = 200


def plain(name: str) -> str:
    """'Amma ❤️' -> 'Amma', 'Kidduuu 🎀' -> 'Kidduuu' (letters only, for hints and matching)."""
    words = re.sub(r"[^\w\s'-]", " ", emoji_to_words(name)).split()
    return " ".join(w for w in words if w.lower() not in EMOJI_WORD_SET).strip()


class KnownNames:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._names: list[str] = self._read()

    def _read(self) -> list[str]:
        if self.path is None or not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [str(n) for n in data if isinstance(n, str)][:MAX_NAMES]
        except (OSError, ValueError):
            log.warning("could not read %s", self.path)
            return []

    def all(self) -> list[str]:
        with self._lock:
            return list(self._names)

    def plain_names(self) -> list[str]:
        """Without emoji, no duplicates: ['Amma', 'Kidduuu', ...] (most recent first)."""
        out: list[str] = []
        for n in self.all():
            p = plain(n)
            if p and p.lower() not in (x.lower() for x in out):
                out.append(p)
        return out

    def add(self, names: list[str]) -> None:
        """Remember these chat names (newest first); saved only when something changed."""
        clean = [n.strip() for n in names if n and n.strip() and re.search(r"[^\W\d_]", n)]
        if not clean:
            return
        with self._lock:
            merged = clean + [n for n in self._names if n not in clean]
            merged = list(dict.fromkeys(merged))[:MAX_NAMES]
            if merged == self._names:
                return
            self._names = merged
            if self.path is not None:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self.path.write_text(json.dumps(merged, ensure_ascii=False, indent=0), encoding="utf-8")
                except OSError:
                    log.warning("could not save %s", self.path)


# ---- sound-alike matching -------------------------------------------------------------------
# Similar consonants sound alike in Indian names spoken to an English model ("Kitya" ~ "Kiddu").
_SOUND_MAP = str.maketrans({"t": "d", "c": "k", "q": "k", "p": "b", "w": "v", "z": "s", "y": "i", "j": "g"})


def sound_key(name: str) -> str:
    """'Kidduuu' -> 'kidu', 'kid do' -> 'kidu'... letters only, doubled letters and vowel runs
    collapsed, silent h dropped."""
    s = re.sub(r"[^a-z]", "", plain(name).lower()).translate(_SOUND_MAP)
    s = re.sub(r"(?<=.)h", "", s)                         # "amah" -> "ama", keeps a leading h
    s = re.sub(r"(.)\1+", r"\1", s)                        # "kidduuu" -> "kidu"
    s = re.sub(r"([aeiou])[aeiou]+", r"\1", s)             # "kidia" -> "kidi"
    return s


def sounds_like(heard: str, name: str) -> float:
    """0..1: how alike two names sound (whole name, or the first words of a longer one)."""
    from difflib import SequenceMatcher

    a = sound_key(heard)
    if not a:
        return 0.0
    words = plain(name).split()
    options = {" ".join(words[:k]) for k in range(1, len(words) + 1)}
    return max((SequenceMatcher(None, a, sound_key(o)).ratio() for o in options if sound_key(o)), default=0.0)
