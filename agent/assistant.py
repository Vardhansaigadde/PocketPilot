"""Glue: text or audio in → Command → Executor → messages for the phone.

Runs in a worker thread (it can be slow: speech-to-text, the AI model, web
requests), so the touchpad keeps working meanwhile. Only one voice command runs
at a time.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Protocol

from .commands import Command, GoToCmd, OpenAppCmd, ScreenCmd, SearchCmd, TaskCmd, UnknownCmd
from .executor import Executor, Outcome
from .memory import Memory
from .router import fast_path, split_steps

log = logging.getLogger("pocketpilot.assistant")

DIDNT_UNDERSTAND = "Sorry, I didn't understand. Try: open notepad, scroll down, weather."

# Pause after a step that opens a window, so the next step (e.g. typing) lands in it.
WAIT_AFTER_OPEN_S = 2.0
WAIT_BETWEEN_S = 0.4


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
        sleep: Callable[[float], None] = time.sleep,
        notify: Callable[[list[dict]], None] | None = None,
        memory: Memory | None = None,
        agent: Any = None,
    ) -> None:
        self.executor = executor
        self.planner = planner
        self.transcriber = transcriber
        self.sleep = sleep
        self.notify = notify   # send a message to the phone straight away (slow commands)
        self.memory = memory   # local history log (data/history.db)
        self.agent = agent     # task_agent.TaskAgent for multi-step requests
        self._busy = threading.Lock()

    # -- entry points (called from a worker thread) ---------------------------
    def handle_text(self, text: str, source: str = "typed") -> list[dict]:
        if not self._busy.acquire(blocking=False):
            return [reply("Still working on the last one…", ok=False)]
        try:
            return self._handle_text(text, source)
        finally:
            self._busy.release()

    def handle_audio(self, audio: Any, source: str = "phone mic") -> list[dict]:
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
            return [{"t": "heard", "text": text}, *self._handle_text(text, source)]
        finally:
            self._busy.release()

    def approve(self, approval_id: str, ok: bool) -> list[dict]:
        return [reply(self.executor.approvals.resolve(approval_id, ok))]

    def stop(self) -> list[dict]:
        """Kill switch. Never waits for the busy lock; also ends a running task."""
        if self.agent is not None:
            self.agent.cancel()
        return [reply(self.executor.stop().say)]

    # -- internals -------------------------------------------------------------
    def to_command(self, text: str) -> Command:
        cmd = fast_path(text)
        if cmd is not None:
            return cmd
        if self.planner is None:
            return UnknownCmd(action="unknown", say=DIDNT_UNDERSTAND)
        return self.planner.to_command(text)

    def _handle_text(self, text: str, source: str = "typed") -> list[dict]:
        steps = split_steps(text)
        if len(steps) > 1:
            return self._handle_steps(steps, source)
        try:
            cmd = self.to_command(text)
        except PlannerError as exc:
            return [reply(str(exc), ok=False)]
        log.info("%r -> %r", text, cmd)
        return _outcome_messages(self._run(cmd, text, source))

    def _run(self, cmd: Command, said: str, source: str) -> Outcome:
        """Run one command and write it to the history log."""
        self._say_wait(cmd)
        if isinstance(cmd, TaskCmd) and self.agent is not None:
            out = self._task(cmd)
        else:
            out = self.executor.run(cmd)
        if self.memory is not None:
            try:
                self.memory.log(source, said, cmd.model_dump(), out.ok, out.say)
            except Exception:  # history must never break a command
                log.exception("could not write history")
        return out

    def _task(self, cmd: TaskCmd) -> Outcome:
        if self.notify is not None:
            self.notify([reply(f"Planning the steps for: {cmd.goal}")])
        say, ok, approval = self.agent.run(cmd.goal)
        return Outcome(say, ok=ok, approval=approval)

    def act(self, cmd: Command, said: str) -> Outcome:
        """One task-agent step: run it and log it (source "task")."""
        return self._run(cmd, said, "task")

    def _say_wait(self, cmd: Command) -> None:
        """Looking at the screen takes 20-40 s on a CPU: tell the user right away."""
        if isinstance(cmd, ScreenCmd) and cmd.mode != "read" and self.notify is not None:
            secs = "40" if cmd.mode == "describe" else "30"
            self.notify([reply(f"Looking at your screen… this takes about {secs} seconds.")])

    def _handle_steps(self, steps: list[str], source: str = "typed") -> list[dict]:
        """Run "open edge then type github.com then press enter" one step at a time.

        Stops at the first step that fails or needs Approve on the phone.
        """
        said: list[str] = []
        for i, step in enumerate(steps, 1):
            try:
                cmd = self.to_command(step)
            except PlannerError as exc:
                return [reply(f"Step {i} ({step}): {exc}", ok=False)]
            log.info("step %d %r -> %r", i, step, cmd)
            out = self._run(cmd, step, source)
            if not out.ok:
                done = " ".join(said)
                return [reply(f"{done} Stopped at step {i} ({step}): {out.say}".strip(), ok=False)]
            said.append(out.say)
            if out.approval is not None:      # e.g. close window: wait for the phone
                return [reply(" ".join(said)), *_outcome_messages(out)[1:]]
            if i < len(steps):
                opens = isinstance(cmd, (OpenAppCmd, GoToCmd, SearchCmd))
                self.sleep(WAIT_AFTER_OPEN_S if opens else WAIT_BETWEEN_S)
        return [reply(" ".join(said))]
