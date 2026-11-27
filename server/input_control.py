"""Moves the real mouse and presses real keys.

`dispatch()` maps each validated message to one method on a controller. The
real controller uses pynput; tests pass in a fake one, so the logic can be
checked on any machine without moving anybody's mouse.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

from .protocol import Button, Click, Hotkey, Key, Media, Message, Move, Ping, Scroll, Text, Zoom

log = logging.getLogger("pocketpilot.input")


class Controller(Protocol):
    def move(self, dx: float, dy: float) -> None: ...
    def click(self, button: str, count: int) -> None: ...
    def button(self, button: str, down: bool) -> None: ...
    def scroll(self, dx: float, dy: float) -> None: ...
    def zoom(self, steps: int) -> None: ...
    def key(self, name: str) -> None: ...
    def type_text(self, text: str) -> None: ...
    def hotkey(self, combo: str) -> None: ...
    def media(self, name: str) -> None: ...
    def release_all(self) -> None: ...
    # Used only by the voice assistant (never reachable from a phone message):
    def move_to(self, x: int, y: int) -> None: ...
    def wake_screen(self) -> None: ...
    def close_window(self) -> None: ...


def dispatch(msg: Message, ctl: Controller) -> dict | None:
    """Perform one message. Returns a reply for the phone, or None."""
    if isinstance(msg, Move):
        ctl.move(msg.dx, msg.dy)
    elif isinstance(msg, Click):
        ctl.click(msg.button, msg.count)
    elif isinstance(msg, Button):
        ctl.button(msg.button, msg.action == "down")
    elif isinstance(msg, Scroll):
        ctl.scroll(msg.dx, msg.dy)
    elif isinstance(msg, Zoom):
        ctl.zoom(msg.steps)
    elif isinstance(msg, Key):
        ctl.key(msg.key)
    elif isinstance(msg, Text):
        ctl.type_text(msg.text)
    elif isinstance(msg, Hotkey):
        ctl.hotkey(msg.combo)
    elif isinstance(msg, Media):
        ctl.media(msg.key)
    elif isinstance(msg, Ping):
        return {"t": "pong", "sent": msg.sent, "server": time.time() * 1000}
    return None


WHEEL_UNITS = 120   # Windows: one wheel notch = 120 units; smaller amounts scroll smoothly


def fine_wheel_units(notches: float) -> int:
    """Whole 1/120th-notch units in an amount of scrolling (towards zero)."""
    return int(notches * WHEEL_UNITS)


def _to_notches(units: int) -> float:
    """Units -> the notches value pynput expects. pynput does int(value * 120), which can turn
    5/120 into 4.999 -> 4, so add half a unit in the direction of travel."""
    if not units:
        return 0
    return (units + (0.5 if units > 0 else -0.5)) / WHEEL_UNITS


class PynputController:
    """The real thing: drives the Windows (or macOS/Linux) mouse and keyboard."""

    def __init__(self) -> None:
        # Imported here so tests and CI never need a display or pynput.
        from pynput import keyboard, mouse

        self._kb = keyboard
        self._mouse = mouse.Controller()
        self._keys = keyboard.Controller()
        self._buttons = {
            "left": mouse.Button.left,
            "right": mouse.Button.right,
            "middle": mouse.Button.middle,
        }
        K = keyboard.Key
        self._named = {
            "enter": K.enter, "backspace": K.backspace, "delete": K.delete,
            "tab": K.tab, "esc": K.esc, "space": K.space,
            "up": K.up, "down": K.down, "left": K.left, "right": K.right,
            "home": K.home, "end": K.end, "page_up": K.page_up, "page_down": K.page_down,
        }
        self._media = {
            "volume_up": K.media_volume_up, "volume_down": K.media_volume_down,
            "mute": K.media_volume_mute, "play_pause": K.media_play_pause,
            "next": K.media_next, "prev": K.media_previous,
        }
        cmd = K.cmd  # the Windows key on Windows
        self._combos = {
            "app_next": [K.alt, K.tab],
            "app_prev": [K.alt, K.shift, K.tab],
            "task_view": [cmd, K.tab],
            "show_desktop": [cmd, "d"],
            "copy": [K.ctrl, "c"],
            "paste": [K.ctrl, "v"],
            "cut": [K.ctrl, "x"],
            "undo": [K.ctrl, "z"],
            "select_all": [K.ctrl, "a"],
            "new_tab": [K.ctrl, "t"],
            "next_tab": [K.ctrl, K.tab],
            "prev_tab": [K.ctrl, K.shift, K.tab],
            "close_tab": [K.ctrl, "w"],
            "reopen_tab": [K.ctrl, K.shift, "t"],
            "back": [K.alt, K.left],
            "forward": [K.alt, K.right],
            "refresh": [K.f5],
            "address_bar": [K.ctrl, "l"],
        }
        self._held: set = set()
        self._scroll_rest = [0.0, 0.0]  # leftover fractions of a wheel step

    def move(self, dx: float, dy: float) -> None:
        self._mouse.move(round(dx), round(dy))

    def click(self, button: str, count: int) -> None:
        self._mouse.click(self._buttons[button], count)

    def button(self, button: str, down: bool) -> None:
        b = self._buttons[button]
        if down:
            self._mouse.press(b)
            self._held.add(b)
        else:
            self._mouse.release(b)
            self._held.discard(b)

    def scroll(self, dx: float, dy: float) -> None:
        # Smooth scrolling: Windows takes wheel movement in 1/120ths of a notch (like a
        # laptop touchpad), so send every 1/120th straight away instead of waiting for a
        # whole notch (that made the page stand still, then jump 3 lines at once).
        self._scroll_rest[0] += dx
        self._scroll_rest[1] += dy
        ux, uy = fine_wheel_units(self._scroll_rest[0]), fine_wheel_units(self._scroll_rest[1])
        if ux or uy:
            self._scroll_rest[0] -= ux / WHEEL_UNITS
            self._scroll_rest[1] -= uy / WHEEL_UNITS
            # pynput multiplies by 120 and truncates: the half unit keeps e.g. 5 from becoming 4
            self._mouse.scroll(_to_notches(ux), _to_notches(uy))

    def zoom(self, steps: int) -> None:
        with self._keys.pressed(self._kb.Key.ctrl):
            self._mouse.scroll(0, steps)

    def key(self, name: str) -> None:
        k = self._named[name]
        self._keys.press(k)
        self._keys.release(k)

    def type_text(self, text: str) -> None:
        self._keys.type(text)

    def hotkey(self, combo: str) -> None:
        keys = self._combos[combo]
        for k in keys:
            self._keys.press(k)
        for k in reversed(keys):
            self._keys.release(k)

    def media(self, name: str) -> None:
        k = self._media[name]
        self._keys.press(k)
        self._keys.release(k)

    def move_to(self, x: int, y: int) -> None:
        self._mouse.position = (int(x), int(y))

    def wake_screen(self) -> None:
        """Turn the display back on: a tiny mouse nudge, plus telling Windows the display is needed."""
        import ctypes

        self._mouse.move(1, 0)
        self._mouse.move(-1, 0)
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(0x00000002))  # ES_DISPLAY_REQUIRED
        except (AttributeError, OSError):  # pragma: no cover - not Windows
            pass

    def close_window(self) -> None:
        """Alt+F4. Only the assistant calls this, and only after Approve on the phone."""
        K = self._kb.Key
        with self._keys.pressed(K.alt):
            self._keys.press(K.f4)
            self._keys.release(K.f4)

    def release_all(self) -> None:
        """Called when the phone disconnects, so a drag never gets stuck."""
        for b in list(self._held):
            try:
                self._mouse.release(b)
            except Exception:  # pragma: no cover - best effort cleanup
                log.exception("could not release %s", b)
        self._held.clear()
