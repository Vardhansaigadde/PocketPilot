"""Glue: text or audio in → Command → Executor → messages for the phone.

Runs in a worker thread (it can be slow: speech-to-text, the AI model, web
requests), so the touchpad keeps working meanwhile. Only one voice command runs
at a time.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

from .commands import Command, UnknownCmd
from .executor import Executor, Outcome
from .router import fast_path

log = logging.getLogger("pocketpilot.assistant")

DIDNT_UNDERSTAND = "Sorry, I didn't understand. Try: open notepad, scroll down, weather."


class Planner(Protocol):
    """Turns an open-ended request into a Command (the AI model)."""
    def to_command(self, text: str) -> Command: ...


class Transcriber(Protocol):
    def transcribe(self, audio: Any) -> str: ...   # file bytes or a 16 kHz numpy array


class PlannerError(RuntimeError):
    """The AI model couldn't be reached or gave an unusable answer."""


def reply(text: str, ok: bool = True) -> dict:
    return {"t": "reply", "text": text, "ok": ok}


def _outcome_messages(out: Outcome) -> list[dict]:
    msgs = [reply(out.say, out.ok)]
    if out.approval is not None:
        p = out.approval
        msgs.append({"t": "approve_request", "id": p.id, "text": p.text, "seconds": p.seconds})
    return msgs


class Assistant:
    def __init__(
        self,
        executor: Executor,
        planner: Planner | None = None,
        transcriber: Transcriber | None = None,
    ) -> None:
        self.executor = executor
        self.planner = planner
        self.transcriber = transcriber
        self._busy = threading.Lock()

    # -- entry points (called from a worker thread) ---------------------------
    def handle_text(self, text: str) -> list[dict]:
        if not self._busy.acquire(blocking=False):
            return [reply("Still working on the last one…", ok=False)]
        try:
            return self._handle_text(text)
        finally:
            self._busy.release()

    def handle_audio(self, audio: Any) -> list[dict]:
        if self.transcriber is None:
            return [reply("Voice isn't set up on the laptop.", ok=False)]
        if not self._busy.acquire(blocking=False):
            return [reply("Still working on the last one…", ok=False)]
        try:
            try:
                text = self.transcriber.transcribe(audio).strip()
            except Exception:
                log.exception("speech-to-text failed")
                return [reply("Sorry, I couldn't process that audio.", ok=False)]
            if not text:
                return [reply("I didn't catch that. Try again?", ok=False)]
            return [{"t": "heard", "text": text}, *self._handle_text(text)]
        finally:
            self._busy.release()

    def approve(self, approval_id: str, ok: bool) -> list[dict]:
        return [reply(self.executor.approvals.resolve(approval_id, ok))]

    def stop(self) -> list[dict]:
        """Kill switch. Never waits for the busy lock."""
        return [reply(self.executor.stop().say)]

    # -- internals -------------------------------------------------------------
    def to_command(self, text: str) -> Command:
        cmd = fast_path(text)
        if cmd is not None:
            return cmd
        if self.planner is None:
            return UnknownCmd(action="unknown", say=DIDNT_UNDERSTAND)
        return self.planner.to_command(text)

    def _handle_text(self, text: str) -> list[dict]:
        try:
            cmd = self.to_command(text)
        except PlannerError as exc:
            return [reply(str(exc), ok=False)]
        log.info("%r -> %r", text, cmd)
        return _outcome_messages(self.executor.run(cmd))
