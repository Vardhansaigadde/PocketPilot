"""Task agent: turn a multi-step request into simple commands, then run them in order.

"open notepad and type hello from pocketpilot"
   plan : the local AI writes a short list of plain commands PocketPilot already
          understands, once:  ["open notepad", "type hello from pocketpilot"]
   run  : each command goes through the normal path (instant phrases first, the
          AI only if needed) and the normal executor, so the allow-list, blocked
          apps and Approve all still apply.

Why not "look, decide, act" in a loop? On a CPU a 4B model takes ~15 s per
decision and loses track of what it already did (tested: it repeated steps and
clicked "Close" buttons). Planning once is faster and far more predictable.

It stops at the first step that fails or isn't understood, on Stop, or at an
Approve request (the user decides). At most 8 steps. Every step shows on the
phone and goes into the history log.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from .commands import Command, GoToCmd, OpenAppCmd, SearchCmd, TaskCmd, UnknownCmd

log = logging.getLogger("pocketpilot.task")

MAX_STEPS = 8
WAIT_AFTER_OPEN_S = 2.0
WAIT_BETWEEN_S = 0.6


class TaskAgent:
    def __init__(
        self,
        plan: Callable[[str], list[str]],                  # the AI: goal -> simple commands
        to_command: Callable[[str], Command],              # "open notepad" -> Command
        act: Callable[[Command, str], Any],                # runs a command, returns an Outcome
        notify: Callable[[list[dict]], None] | None = None,
        max_steps: int = MAX_STEPS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.plan = plan
        self.to_command = to_command
        self.act = act
        self.notify = notify
        self.max_steps = max_steps
        self.sleep = sleep
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Stop button / "stop": the task ends before its next step."""
        self._cancel.set()

    def run(self, goal: str) -> tuple[str, bool, Any]:
        """Returns (what to say, ok, a pending approval or None)."""
        self._cancel.clear()
        steps = [s.strip() for s in self.plan(goal) if s and s.strip()][: self.max_steps]
        if not steps:
            return "I couldn't work out the steps for that. Try saying them one by one.", False, None
        self._tell("Plan: " + "; ".join(f"{i}) {s}" for i, s in enumerate(steps, 1)))
        said: list[str] = []
        for i, step in enumerate(steps, 1):
            if self._cancel.is_set():
                return self._end(said, "Stopped."), False, None
            cmd = self.to_command(step)
            if isinstance(cmd, (TaskCmd, UnknownCmd)):
                return self._end(said, f"I didn't understand step {i} ({step})."), False, None
            out = self.act(cmd, f"[task] {step}")
            self._tell(f"Step {i}: {out.say}")
            if out.approval is not None:
                return out.say, True, out.approval            # the user decides on the phone
            if not out.ok:
                return self._end(said, f"Step {i} ({step}) didn't work: {out.say}"), False, None
            said.append(out.say)
            if i < len(steps):
                opens = isinstance(cmd, (OpenAppCmd, GoToCmd, SearchCmd))
                self.sleep(WAIT_AFTER_OPEN_S if opens else WAIT_BETWEEN_S)
        return "Done: " + " ".join(said), True, None

    def _tell(self, text: str) -> None:
        if self.notify is not None:
            self.notify([{"t": "reply", "text": text, "ok": True}])

    @staticmethod
    def _end(said: list[str], why: str) -> str:
        return f"{' '.join(said)} {why}".strip()
