"""Carries out a validated Command and says what happened.

The executor only ever calls fixed functions: the mouse/keyboard controller,
the app launcher with a known target, the skills, and the grid. It never runs
shell commands or code.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from server.input_control import Controller

from . import apps
from .approvals import Approvals, Pending
from .memory import Memory, describe
from .smart_click import is_risky
from .commands import (
    GRID_CELLS, AirQualityCmd, ClickCmd, CricketCmd, CurrencyCmd, DefineCmd, NewsCmd, CloseWindowCmd, Command, GoToCmd, GridClickCmd, GridCmd,
    ForgetCmd, GridZoomCmd, KeepAwakeCmd, MemoryCmd, TaskCmd, WakeScreenCmd, WhatsAppCmd,
    ScreenCmd, SmartClickCmd,
    HotkeyCmd, KeyCmd, MediaCmd, OpenAppCmd, ScrollCmd, SearchCmd, StopCmd, TypeCmd,
    UnknownCmd, WeatherCmd, WikiCmd,
)

log = logging.getLogger("pocketpilot.executor")

SCROLL_SIGN = {"up": 1, "down": -1}   # Windows: positive wheel = up


class Skills(Protocol):
    def weather(self, place: str | None) -> str: ...
    def air_quality(self, place: str | None) -> str: ...
    def wiki(self, topic: str) -> str: ...
    def search(self, site: str, query: str) -> str: ...
    def open_site(self, site: str) -> str: ...
    def currency(self, amount: float, from_cur: str, to_cur: str) -> str: ...
    def define(self, word: str) -> str: ...
    def news(self, topic: str | None) -> str: ...
    def cricket(self) -> str: ...


class Clicker(Protocol):
    def find(self, target: str) -> Any: ...   # a smart_click.Candidate or None


class Screen(Protocol):
    def look(self, mode: str) -> str: ...      # describe / summarize / explain_error / read


class Messenger(Protocol):
    def open_chat(self, contact: str) -> str: ...
    def prepare_message(self, contact: str, text: str) -> Any: ...   # whatsapp.Prepared
    def prepare_call(self, contact: str, video: bool = False) -> Any: ...


class Grid(Protocol):
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def cell_center(self, cell: int) -> tuple[int, int]: ...
    def zoom(self, cell: int) -> None: ...
    def reset(self) -> None: ...
    @property
    def cells(self) -> int: ...


@dataclass
class Outcome:
    say: str                       # short reply for the user
    ok: bool = True
    approval: Pending | None = None
    choices: list[str] | None = None   # "which one?" options shown as buttons on the phone


CHOICE_SECONDS = 90
_ORDINALS = {"first": 1, "one": 1, "1st": 1, "second": 2, "two": 2, "2nd": 2, "third": 3, "three": 3,
             "3rd": 3, "fourth": 4, "four": 4, "4th": 4, "fifth": 5, "five": 5, "5th": 5, "sixth": 6,
             "six": 6, "6th": 6, "last": -1}


@dataclass
class Choice:
    """A pending "which one?" question: the command waiting for a contact, and the options."""
    cmd: Any
    options: list[str]
    expires: float

    def pick(self, said: str) -> str | None:
        """The option the user meant ("2", "second", "the first one", "Sharmila"), "cancel", or None."""
        from .smart_click import best_match as _best, Candidate as _C

        t = " ".join(said.lower().strip(" .!?").split())
        t = re.sub(r"^(?:the |number |option )", "", t)
        if t not in _ORDINALS:
            t = re.sub(r" (?:one|please)$", "", t)          # "the second one" -> "second"
        if t in ("cancel", "none", "no", "never mind", "nevermind", "stop", "neither"):
            return "cancel"
        n = int(t) if t.isdigit() else _ORDINALS.get(t)
        if n is not None:
            idx = n - 1 if n > 0 else len(self.options) - 1
            return self.options[idx] if 0 <= idx < len(self.options) else None
        hit = _best(said, [_C(o, "ListItem", (0, i * 10, 10, i * 10 + 5)) for i, o in enumerate(self.options)])
        return hit.name if hit is not None else None


_SAY_MEDIA = {
    "volume_up": "Volume up.", "volume_down": "Volume down.", "mute": "Toggled mute.",
    "play_pause": "Play / pause.", "next": "Next track.", "prev": "Previous track.",
}
_SAY_HOTKEY = {
    "app_next": "Switched app.", "app_prev": "Switched back.", "task_view": "Showing all windows.",
    "show_desktop": "Showing the desktop.", "copy": "Copied.", "paste": "Pasted.", "cut": "Cut.",
    "undo": "Undone.", "select_all": "Selected all.",
    "new_tab": "New tab.", "next_tab": "Next tab.", "prev_tab": "Previous tab.",
    "back": "Going back.", "forward": "Going forward.", "refresh": "Refreshing.",
    "address_bar": "Address bar. Say type and the address.",
}


def start_app(target: str) -> None:
    """Start a known app target with Windows (only ever called with targets from apps.APPS)."""
    os.startfile(target)  # type: ignore[attr-defined]  # Windows only


class Executor:
    def __init__(
        self,
        controller: Controller,
        approvals: Approvals,
        skills: Skills | None = None,
        grid: Grid | None = None,
        launcher: Callable[[str], None] = start_app,
        app_available: Callable[[str], bool] = apps.is_available,
        clicker: Clicker | None = None,
        screen: Screen | None = None,
        memory: Memory | None = None,
        summarize: Callable[[str], str] | None = None,
        whatsapp: Messenger | None = None,
        awake: Any = None,
        locked: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ctl = controller
        self.approvals = approvals
        self.skills = skills
        self.grid = grid
        self.launch = launcher
        self.app_available = app_available
        self.clicker = clicker
        self.screen = screen
        self.memory = memory
        self.summarize = summarize   # text model, for long histories
        self.whatsapp = whatsapp
        self.awake = awake       # keep_awake.KeepAwake
        self.locked = locked     # is the Windows lock screen showing?
        self.clock = clock
        self.choice: Choice | None = None   # a pending "which one?" question

    def run(self, cmd: Command) -> Outcome:
        try:
            return self._run(cmd)
        except Exception:
            log.exception("command failed: %r", cmd)
            return Outcome("Sorry, that didn't work.", ok=False)

    def _run(self, cmd: Command) -> Outcome:  # noqa: C901 - one branch per command is clearest
        if isinstance(cmd, StopCmd):
            return self.stop()
        if isinstance(cmd, ScrollCmd):
            self.ctl.scroll(0, SCROLL_SIGN[cmd.direction] * cmd.amount)
            return Outcome(f"Scrolled {cmd.direction}.")
        if isinstance(cmd, ClickCmd):
            self.ctl.click(cmd.button, cmd.count)
            return Outcome("Double-clicked." if cmd.count == 2 else f"{cmd.button.capitalize()} click.")
        if isinstance(cmd, TypeCmd):
            self.ctl.type_text(cmd.text)
            return Outcome("Typed it.")
        if isinstance(cmd, KeyCmd):
            self.ctl.key(cmd.key)
            return Outcome(f"Pressed {cmd.key.replace('_', ' ')}.")
        if isinstance(cmd, MediaCmd):
            self.ctl.media(cmd.key)
            return Outcome(_SAY_MEDIA[cmd.key])
        if isinstance(cmd, HotkeyCmd):
            self.ctl.hotkey(cmd.combo)
            return Outcome(_SAY_HOTKEY[cmd.combo])
        if isinstance(cmd, OpenAppCmd):
            target, label = apps.app_target(cmd.app), apps.app_label(cmd.app)
            web = apps.WEB_FALLBACK.get(cmd.app)
            if web and self.skills is not None and not self.app_available(target):
                self.skills.open_site(web)
                return Outcome(f"The {label} app isn't installed, so I opened {label} on the web.")
            self.launch(target)
            return Outcome(f"Opening {label}.")
        if isinstance(cmd, CloseWindowCmd):
            def close() -> str:
                self.ctl.close_window()
                return "Closed the window."
            pending = self.approvals.request("Close the active window?", close)
            return Outcome("Approve on your phone to close the window.", approval=pending)
        if isinstance(cmd, (GridCmd, GridZoomCmd, GridClickCmd)):
            return self._grid(cmd)
        if isinstance(cmd, SmartClickCmd):
            return self._smart_click(cmd)
        if isinstance(cmd, TaskCmd):     # the assistant hands tasks to the task agent
            return Outcome("Multi-step tasks aren't available.", ok=False)
        if isinstance(cmd, WhatsAppCmd):
            return self._whatsapp(cmd)
        if isinstance(cmd, WakeScreenCmd):
            self.ctl.wake_screen()
            if self.locked():
                return Outcome("Screen is on. It's locked: unlock it with your face, fingerprint or PIN.")
            return Outcome("Screen is on.")
        if isinstance(cmd, KeepAwakeCmd):
            if self.awake is None:
                return Outcome("Keep-awake isn't available.", ok=False)
            return Outcome(self.awake.set_mode(cmd.mode))
        if isinstance(cmd, (MemoryCmd, ForgetCmd)):
            return self._memory(cmd)
        if isinstance(cmd, ScreenCmd):
            if self.screen is None:
                return Outcome("Screen reading isn't available.", ok=False)
            return Outcome(self.screen.look(cmd.mode))
        if isinstance(cmd, (WeatherCmd, AirQualityCmd, WikiCmd, SearchCmd, GoToCmd, CurrencyCmd, DefineCmd,
                            NewsCmd, CricketCmd)):
            if self.skills is None:
                return Outcome("That skill isn't available.", ok=False)
            if isinstance(cmd, WeatherCmd):
                return Outcome(self.skills.weather(cmd.place))
            if isinstance(cmd, AirQualityCmd):
                return Outcome(self.skills.air_quality(cmd.place))
            if isinstance(cmd, WikiCmd):
                return Outcome(self.skills.wiki(cmd.topic))
            if isinstance(cmd, GoToCmd):
                return Outcome(self.skills.open_site(cmd.site))
            if isinstance(cmd, CurrencyCmd):
                return Outcome(self.skills.currency(cmd.amount, cmd.from_cur, cmd.to_cur))
            if isinstance(cmd, DefineCmd):
                return Outcome(self.skills.define(cmd.word))
            if isinstance(cmd, NewsCmd):
                return Outcome(self.skills.news(cmd.topic))
            if isinstance(cmd, CricketCmd):
                return Outcome(self.skills.cricket())
            return Outcome(self.skills.search(cmd.site, cmd.query))
        if isinstance(cmd, UnknownCmd):
            return Outcome(cmd.say, ok=False)
        return Outcome("Sorry, I can't do that yet.", ok=False)  # pragma: no cover

    def _grid(self, cmd: GridCmd | GridZoomCmd | GridClickCmd) -> Outcome:
        if self.grid is None:
            return Outcome("The grid isn't available.", ok=False)
        g = self.grid
        if isinstance(cmd, GridCmd):
            if cmd.show:
                g.show()
                return Outcome(f"Grid on. Say click and a number from 1 to {g.cells}, "
                               "or zoom and a number for smaller boxes.")
            g.hide()
            g.reset()
            return Outcome("Grid off.")
        if not 1 <= cmd.cell <= g.cells:
            return Outcome(f"Say a number from 1 to {g.cells}.", ok=False)
        if isinstance(cmd, GridZoomCmd):
            g.zoom(cmd.cell)
            return Outcome(f"Zoomed into box {cmd.cell}. Say click and a number from 1 to {g.cells}.")
        x, y = g.cell_center(cmd.cell)
        g.hide()
        g.reset()
        self.ctl.move_to(x, y)
        self.ctl.click(cmd.button, cmd.count)
        return Outcome(f"Clicked {cmd.cell}.")

    def _whatsapp(self, cmd: WhatsAppCmd) -> Outcome:
        """Get the chat ready, then wait for Approve before anything is sent or dialled."""
        if self.whatsapp is None:
            return Outcome("WhatsApp control isn't available.", ok=False)
        from .whatsapp import AmbiguousContact, WhatsAppError

        try:
            if cmd.kind == "open":
                return Outcome(f"Opened your chat with {self.whatsapp.open_chat(cmd.contact)}.")
            if cmd.kind == "message":
                if not cmd.text:
                    return Outcome(f"What should I say to {cmd.contact}?", ok=False)
                ready = self.whatsapp.prepare_message(cmd.contact, cmd.text)
                question = f'Send to {ready.chat} on WhatsApp: "{cmd.text}"?'
                say = f"Message to {ready.chat} is ready. Approve on your phone to send it."
            else:
                video = cmd.kind == "video_call"
                ready = self.whatsapp.prepare_call(cmd.contact, video=video)
                kind = "video" if video else "voice"
                if getattr(ready, "group", False):
                    question = f"Group {kind} call {ready.chat} on WhatsApp? (rings everyone in the group)"
                else:
                    question = f"{kind.capitalize()} call {ready.chat} on WhatsApp?"
                say = f"Approve on your phone to call {ready.chat}."
        except AmbiguousContact as exc:
            self.choice = Choice(cmd, exc.names, self.clock() + CHOICE_SECONDS)
            return Outcome(str(exc), choices=exc.names)
        except WhatsAppError as exc:
            return Outcome(str(exc), ok=False)

        def go() -> str:
            try:
                return ready.go()
            except WhatsAppError as exc:
                return str(exc)

        pending = self.approvals.request(question, go, on_cancel=ready.undo)
        return Outcome(say, approval=pending)

    def answer_choice(self, said: str) -> Outcome | None:
        """If a "which one?" question is waiting and `said` answers it, finish the original
        command with that contact. Returns None if `said` isn't an answer (the question is
        then dropped, because the user moved on)."""
        choice, self.choice = self.choice, None
        if choice is None or choice.expires < self.clock():
            return None
        picked = choice.pick(said)
        if picked is None:
            return None
        if picked == "cancel":
            return Outcome("OK, cancelled.")
        return self.run(choice.cmd.model_copy(update={"contact": f"just {picked}"[:60]}))

    def _memory(self, cmd: MemoryCmd | ForgetCmd) -> Outcome:
        if self.memory is None:
            return Outcome("History isn't turned on.", ok=False)
        memory = self.memory
        if isinstance(cmd, ForgetCmd):
            def forget() -> str:
                return f"Deleted {memory.clear()} history entries."
            pending = self.approvals.request("Delete all of PocketPilot's history?", forget)
            return Outcome("Approve on your phone to delete your history.", approval=pending)
        entries = memory.recall(cmd.period)
        if len(entries) > 8 and self.summarize is not None:
            lines = "\n".join(f"{e.at:%a %H:%M} {e.said} -> {e.reply}" for e in entries[-80:])
            return Outcome(self.summarize(lines))
        return Outcome(describe(entries[-8:], cmd.period))

    def _smart_click(self, cmd: SmartClickCmd) -> Outcome:
        if self.clicker is None:
            return Outcome("Smart click isn't available. Say show grid instead.", ok=False)
        hit = self.clicker.find(cmd.target)
        if hit is None:
            return Outcome(f"I couldn't find {cmd.target} on the screen. Say show grid to pick it by number.",
                           ok=False)
        name = hit.name if len(hit.name) <= 40 else hit.name[:37] + "..."
        closest = " (closest match)" if getattr(hit, "score", 1.0) < 0.95 else ""

        def click() -> str:
            self.ctl.move_to(*hit.center)
            self.ctl.click(cmd.button, cmd.count)
            return f"Clicked {name}{closest}."

        if is_risky(hit.name) or is_risky(cmd.target):
            pending = self.approvals.request(f'Click "{name}"?', click)
            return Outcome(f"Approve on your phone to click {name}.", approval=pending)
        return Outcome(click())

    def stop(self) -> Outcome:
        """Kill switch: cancel approvals, hide the grid, let go of the mouse."""
        self.approvals.cancel_all()
        if self.grid is not None:
            try:
                self.grid.hide()
            except Exception:  # pragma: no cover - best effort
                log.exception("could not hide grid")
        self.ctl.release_all()
        return Outcome("Stopped.")
