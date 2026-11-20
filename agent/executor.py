"""Carries out a validated Command and says what happened.

The executor only ever calls fixed functions: the mouse/keyboard controller,
the app launcher with a known target, the skills, and the grid. It never runs
shell commands or code.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable, Protocol

from server.input_control import Controller

from . import apps
from .approvals import Approvals, Pending
from .commands import (
    GRID_CELLS, AirQualityCmd, ClickCmd, CloseWindowCmd, Command, GridClickCmd, GridCmd,
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


class Grid(Protocol):
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def cell_center(self, cell: int) -> tuple[int, int]: ...


@dataclass
class Outcome:
    say: str                       # short reply for the user
    ok: bool = True
    approval: Pending | None = None


_SAY_MEDIA = {
    "volume_up": "Volume up.", "volume_down": "Volume down.", "mute": "Toggled mute.",
    "play_pause": "Play / pause.", "next": "Next track.", "prev": "Previous track.",
}
_SAY_HOTKEY = {
    "app_next": "Switched app.", "app_prev": "Switched back.", "task_view": "Showing all windows.",
    "show_desktop": "Showing the desktop.", "copy": "Copied.", "paste": "Pasted.", "cut": "Cut.",
    "undo": "Undone.", "select_all": "Selected all.",
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
    ) -> None:
        self.ctl = controller
        self.approvals = approvals
        self.skills = skills
        self.grid = grid
        self.launch = launcher

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
            self.launch(apps.app_target(cmd.app))
            return Outcome(f"Opening {apps.app_label(cmd.app)}.")
        if isinstance(cmd, CloseWindowCmd):
            def close() -> str:
                self.ctl.close_window()
                return "Closed the window."
            pending = self.approvals.request("Close the active window?", close)
            return Outcome("Approve on your phone to close the window.", approval=pending)
        if isinstance(cmd, GridCmd):
            if self.grid is None:
                return Outcome("The grid isn't available.", ok=False)
            if cmd.show:
                self.grid.show()
                return Outcome(f"Grid on. Say click and a number from 1 to {GRID_CELLS}.")
            self.grid.hide()
            return Outcome("Grid off.")
        if isinstance(cmd, GridClickCmd):
            if self.grid is None:
                return Outcome("The grid isn't available.", ok=False)
            x, y = self.grid.cell_center(cmd.cell)
            self.grid.hide()
            self.ctl.move_to(x, y)
            self.ctl.click(cmd.button, cmd.count)
            return Outcome(f"Clicked {cmd.cell}.")
        if isinstance(cmd, (WeatherCmd, AirQualityCmd, WikiCmd, SearchCmd)):
            if self.skills is None:
                return Outcome("That skill isn't available.", ok=False)
            if isinstance(cmd, WeatherCmd):
                return Outcome(self.skills.weather(cmd.place))
            if isinstance(cmd, AirQualityCmd):
                return Outcome(self.skills.air_quality(cmd.place))
            if isinstance(cmd, WikiCmd):
                return Outcome(self.skills.wiki(cmd.topic))
            return Outcome(self.skills.search(cmd.site, cmd.query))
        if isinstance(cmd, UnknownCmd):
            return Outcome(cmd.say, ok=False)
        return Outcome("Sorry, I can't do that yet.", ok=False)  # pragma: no cover

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
