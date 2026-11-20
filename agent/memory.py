"""Memory: a local log of every command, so you can ask "what was I working on yesterday?".

Stored in data/history.db (SQLite) on the laptop only; data/ is git-ignored and
nothing here is sent anywhere. "clear my history" deletes it (after Approve).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

PERIODS = ("today", "yesterday", "last_hour", "this_week")


@dataclass(frozen=True)
class Entry:
    at: datetime
    source: str       # "phone mic", "laptop mic", "typed", "task"
    said: str
    action: str       # e.g. "open_app", "search"
    ok: bool
    reply: str


class Memory:
    def __init__(self, path: Path | str = ":memory:", clock: Callable[[], datetime] = datetime.now) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        self.clock = clock
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS history ("
                " at TEXT NOT NULL, source TEXT, said TEXT, action TEXT, command TEXT, ok INTEGER, reply TEXT)")
            self._db.execute("CREATE INDEX IF NOT EXISTS history_at ON history(at)")
            self._db.commit()

    def log(self, source: str, said: str, command: dict | None, ok: bool, reply: str) -> None:
        action = (command or {}).get("action", "")
        with self._lock:
            self._db.execute(
                "INSERT INTO history VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.clock().isoformat(timespec="seconds"), source, said[:300], action,
                 json.dumps(command or {}, ensure_ascii=False)[:1000], int(ok), reply[:300]))
            self._db.commit()

    def between(self, start: datetime, end: datetime) -> list[Entry]:
        with self._lock:
            rows = self._db.execute(
                "SELECT at, source, said, action, ok, reply FROM history WHERE at >= ? AND at < ? ORDER BY at",
                (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"))).fetchall()
        return [Entry(datetime.fromisoformat(a), s, said, act, bool(ok), r) for a, s, said, act, ok, r in rows]

    def period(self, name: str) -> tuple[datetime, datetime]:
        now = self.clock()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if name == "yesterday":
            return midnight - timedelta(days=1), midnight
        if name == "last_hour":
            return now - timedelta(hours=1), now + timedelta(seconds=1)
        if name == "this_week":
            return midnight - timedelta(days=now.weekday()), now + timedelta(seconds=1)
        return midnight, now + timedelta(seconds=1)

    def recall(self, name: str) -> list[Entry]:
        """What happened in a period, without the memory questions themselves."""
        start, end = self.period(name)
        return [e for e in self.between(start, end) if e.action not in ("memory", "forget_history")]

    def clear(self) -> int:
        with self._lock:
            n = self._db.execute("DELETE FROM history").rowcount
            self._db.commit()
        return n


def describe(entries: list[Entry], period: str) -> str:
    """Short spoken list: 'Yesterday: 10:02 open notepad; 10:05 search youtube for lofi.'"""
    when = {"today": "Today", "yesterday": "Yesterday", "last_hour": "In the last hour",
            "this_week": "This week"}.get(period, "Today")
    if not entries:
        return f"{when}, I don't have anything recorded."
    fmt = "%a %H:%M" if period == "this_week" else "%H:%M"
    items = "; ".join(f"{e.at.strftime(fmt)} {e.said}" for e in entries)
    return f"{when}: {items}."
