"""Risky actions wait here until the user taps Approve on the phone.

Each request gets a random id and expires after a short time. Nothing happens
unless the matching id is approved before it expires; Stop cancels them all.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

DEFAULT_SECONDS = 30


@dataclass
class Pending:
    id: str
    text: str                      # shown on the phone, e.g. "Close the active window?"
    action: Callable[[], str]      # runs only after Approve; returns what to say
    expires: float
    seconds: int = DEFAULT_SECONDS
    done: bool = field(default=False)


class Approvals:
    def __init__(self, seconds: int = DEFAULT_SECONDS, clock: Callable[[], float] = time.monotonic):
        self._seconds = seconds
        self._clock = clock
        self._pending: dict[str, Pending] = {}
        self._lock = threading.Lock()

    def request(self, text: str, action: Callable[[], str]) -> Pending:
        p = Pending(
            id=secrets.token_hex(6), text=text, action=action,
            expires=self._clock() + self._seconds, seconds=self._seconds,
        )
        with self._lock:
            self._drop_expired()
            self._pending[p.id] = p
        return p

    def resolve(self, approval_id: str, ok: bool) -> str:
        """Approve or cancel one request. Returns what to tell the user."""
        with self._lock:
            self._drop_expired()
            p = self._pending.pop(approval_id, None)
        if p is None:
            return "That request expired. Ask again if you still want it."
        if not ok:
            return "Cancelled."
        p.done = True
        return p.action()

    def cancel_all(self) -> int:
        with self._lock:
            n = len(self._pending)
            self._pending.clear()
        return n

    def count(self) -> int:
        with self._lock:
            self._drop_expired()
            return len(self._pending)

    def _drop_expired(self) -> None:
        now = self._clock()
        for k in [k for k, p in self._pending.items() if p.expires <= now]:
            del self._pending[k]
