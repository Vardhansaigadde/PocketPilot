"""Live cricket scores (CricketData.org, free key; set POCKETPILOT_CRICKET_KEY in .env)."""

from __future__ import annotations

import httpx

from .common import SkillError

DESCRIPTION = "Live and recent cricket match scores."
URL = "https://api.cricapi.com/v1/currentMatches"
NEEDS_KEY = ("Cricket scores need a free key: sign up at cricketdata.org, then put it in .env as "
             "POCKETPILOT_CRICKET_KEY=your-key and restart PocketPilot.")


def _innings(s: dict) -> str:
    return f"{s.get('inning', '').replace(' Inning 1', '').replace(' Inning 2', '')} {s.get('r', 0)}/{s.get('w', 0)} ({s.get('o', 0)} ov)"


def scores(client: httpx.Client, key: str | None) -> str:
    if not key:
        raise SkillError(NEEDS_KEY)
    r = client.get(URL, params={"apikey": key, "offset": 0})
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "success":
        reason = str(data.get("reason", "")).lower()
        if "key" in reason or "apikey" in reason:
            raise SkillError("The cricket key didn't work. Check POCKETPILOT_CRICKET_KEY in .env.")
        raise SkillError("Cricket scores aren't available right now.")
    matches = data.get("data") or []
    live = [m for m in matches if m.get("matchStarted") and not m.get("matchEnded")]
    picked = (live or matches)[:3]
    if not picked:
        return "No cricket matches right now."
    parts = []
    for m in picked:
        score = "; ".join(_innings(s) for s in (m.get("score") or [])[-2:])
        line = m.get("name", "A match").split(",")[0]
        parts.append(f"{line}: {score + '. ' if score else ''}{m.get('status', '').strip()}".strip())
    return ("Live: " if live else "Recent: ") + " | ".join(parts)
