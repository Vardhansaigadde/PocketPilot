"""Risky actions wait here until the user taps Approve on the phone.

Each request gets a random id and expires after a short time. Nothing happens
unless the matching id is approved before it expires; Stop cancels them all.
A request can also say what to undo when it is cancelled or expires (e.g. wipe
a WhatsApp draft that was typed but never sent).
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger("pocketpilot.approvals")

DEFAULT_SECONDS = 30


@dataclass
class Pending:
    id: str
    text: str                      # shown on the phone, e.g. "Close the active window?"
    action: Callable[[], str]      # runs only after Approve; returns what to say
    expires: float
    seconds: int = DEFAULT_SECONDS
    on_cancel: Callable[[], None] | None = None   # undo when cancelled / expired / stopped
    done: bool = field(default=False)


def _undo(p: Pending) -> None:
    if p.on_cancel is None:
        return
    try:
        p.on_cancel()
    except Exception:  # undo is best effort; never crash the caller
        log.exception("could not undo %r", p.text)


class Approvals:
    def __init__(self, seconds: int = DEFAULT_SECONDS, clock: Callable[[], float] = time.monotonic):
        self._seconds = seconds
        self._clock = clock
        self._pending: dict[str, Pending] = {}
        self._lock = threading.Lock()

    def request(self, text: str, action: Callable[[], str],
                on_cancel: Callable[[], None] | None = None) -> Pending:
        p = Pending(
            id=secrets.token_hex(6), text=text, action=action,
            expires=self._clock() + self._seconds, seconds=self._seconds, on_cancel=on_cancel,
        )
        with self._lock:
            expired = self._drop_expired()
            self._pending[p.id] = p
        for old in expired:
            _undo(old)
        return p

    def resolve(self, approval_id: str, ok: bool) -> str:
        """Approve or cancel one request. Returns what to tell the user."""
        with self._lock:
            expired = self._drop_expired()
            p = self._pending.pop(approval_id, None)
        for old in expired:
            _undo(old)
        if p is None:
            return "That request expired. Ask again if you still want it."
        if not ok:
            _undo(p)
            return "Cancelled."
        p.done = True
        return p.action()

    def cancel_all(self) -> int:
        with self._lock:
            gone = list(self._pending.values())
            self._pending.clear()
        for p in gone:
            _undo(p)
        return len(gone)

    def count(self) -> int:
        with self._lock:
            expired = self._drop_expired()
            n = len(self._pending)
        for old in expired:
            _undo(old)
        return n

    def _drop_expired(self) -> list[Pending]:
        now = self._clock()
        gone = [p for p in self._pending.values() if p.expires <= now]
        for p in gone:
            del self._pending[p.id]
        return gone
