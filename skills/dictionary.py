"""Word meanings (Free Dictionary API, dictionaryapi.dev, free, no key)."""

from __future__ import annotations

from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from .common import SkillError

DESCRIPTION = "The meaning of an English word, with an example."
URL = "https://api.dictionaryapi.dev/api/v2/entries/en/"


class DefineInput(BaseModel):
    word: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z][A-Za-z' -]*$")


def define(client: httpx.Client, word: str) -> str:
    q = DefineInput(word=word.strip())
    r = client.get(URL + quote(q.word.lower()))
    if r.status_code == 404:
        raise SkillError(f"I couldn't find {q.word} in the dictionary.")
    r.raise_for_status()
    entries = r.json()
    if not isinstance(entries, list) or not entries:
        raise SkillError(f"I couldn't find {q.word} in the dictionary.")
    meanings = entries[0].get("meanings") or []
    if not meanings or not meanings[0].get("definitions"):
        raise SkillError(f"The dictionary has {q.word} but no meaning for it.")
    first = meanings[0]
    d = first["definitions"][0]
    text = f"{q.word} ({first.get('partOfSpeech', 'word')}): {d.get('definition', '').strip()}"
    if d.get("example"):
        text += f' For example: "{d["example"].strip()}"'
    return text
