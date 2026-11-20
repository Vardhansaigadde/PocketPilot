"""WhatsApp Desktop: open a chat, draft a message, or prepare a call, by voice.

Nothing is ever sent or dialled here. This module only gets things ready:
  - message: opens the chat and types the draft (Enter is NOT pressed)
  - call:    opens the chat
and returns what to do once the user taps Approve on the phone (press Enter /
click "Voice call"), plus how to undo a draft if they tap Cancel.

It works through WhatsApp's own control names (UI Automation), found on its
inner window, which answers in about 0.1 s:
  "Search or start a new chat", "Contact info <name>", "Voice call",
  "Video call", "Type a message to <name>".
"""

from __future__ import annotations

import ctypes
import logging
import re
import time
from dataclasses import dataclass
from typing import Callable

from server.input_control import Controller

from .smart_click import Candidate, best_match, score, uia_candidates

log = logging.getLogger("pocketpilot.whatsapp")

TITLE = re.compile(r"^(?:\(\d+\) )?WhatsApp$")
CHAT_ROWS = ("DataItem", "ListItem", "TreeItem")
MATCH = 0.85                 # how sure we must be that the open chat is the right person


class WhatsAppError(Exception):
    """Something to tell the user, e.g. "I couldn't find Amma in WhatsApp"."""


@dataclass
class Prepared:
    chat: str                          # the chat that is open, e.g. "Amma"
    go: Callable[[], str]              # runs after Approve: send / call
    undo: Callable[[], None] | None    # runs after Cancel: wipe the draft


def _title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def _class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(128)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 128)
    return buf.value


def find_window() -> int | None:
    """WhatsApp's inner (fast) window: class Chrome_WidgetWin_1, title "WhatsApp" / "(3) WhatsApp"."""
    found: list[int] = []
    user32 = ctypes.windll.user32
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd, _):  # noqa: ANN001 - Windows callback
        if user32.IsWindowVisible(hwnd) and _class(hwnd) == "Chrome_WidgetWin_1" and TITLE.match(_title(hwnd)):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(proc(visit), 0)
    return found[0] if found else None


def focus(hwnd: int) -> None:
    from pywinauto.controls.hwndwrapper import HwndWrapper

    HwndWrapper(hwnd).set_focus()      # restores it if minimised and brings it to the front


def launch() -> None:
    import os

    os.startfile("whatsapp:")  # type: ignore[attr-defined]


class WhatsApp:
    """Drives WhatsApp Desktop. Every outside thing is passed in, so tests use fakes."""

    def __init__(
        self,
        controller: Controller,
        controls: Callable[[int], list[Candidate]] = uia_candidates,
        window: Callable[[], int | None] = find_window,
        bring_front: Callable[[int], None] = focus,
        start: Callable[[], None] = launch,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.ctl = controller
        self.controls = controls
        self.window = window
        self.bring_front = bring_front
        self.start = start
        self.sleep = sleep

    # -- public -------------------------------------------------------------------------
    def open_chat(self, contact: str) -> str:
        """Open the chat with `contact` and return its real name (e.g. "Kidduuu")."""
        hwnd = self._window()
        search = self._find(hwnd, lambda c: c.kind == "Edit" and c.name.lower().startswith("search"))
        if search is None:
            raise WhatsAppError("I can't find WhatsApp's search box. Is WhatsApp open and signed in?")
        self._click(search)
        self.ctl.hotkey("select_all")
        self.ctl.key("backspace")
        self.ctl.type_text(contact)
        self.sleep(1.2)                                   # results appear as you type
        rows = [c for c in self.controls(hwnd) if c.kind in CHAT_ROWS]
        row = best_match(contact, rows)
        if row is None:
            self.ctl.key("esc")
            raise WhatsAppError(f"I couldn't find {contact} in WhatsApp.")
        self._click(row)
        self.sleep(0.8)
        chat = self.current_chat(hwnd)
        if chat is None or score(contact, chat) < MATCH:
            raise WhatsAppError(f"I opened {chat or 'a chat'}, not {contact}, so I stopped.")
        return chat

    def current_chat(self, hwnd: int | None = None) -> str | None:
        """Name of the open chat, from the header button "Contact info <name>"."""
        hwnd = hwnd or self._window(launch=False)
        header = self._find(hwnd, lambda c: c.kind == "Button" and c.name.lower().startswith("contact info "))
        if header is None:
            return None
        return re.sub(r"[^\w\s.'-]", "", header.name[len("Contact info "):]).strip() or None

    def prepare_message(self, contact: str, text: str) -> Prepared:
        chat = self.open_chat(contact)
        hwnd = self._window(launch=False)
        box = self._message_box(hwnd)
        self._click(box)
        self.ctl.type_text(text)                          # typed, NOT sent

        def send() -> str:
            self._check_still(chat)
            self._click(self._message_box(self._window(launch=False)))
            self.ctl.key("enter")
            return f"Sent to {chat}."

        def wipe() -> None:
            hwnd2 = self._window(launch=False)
            if self.current_chat(hwnd2) == chat:
                self._click(self._message_box(hwnd2))
                self.ctl.hotkey("select_all")
                self.ctl.key("backspace")

        return Prepared(chat, send, wipe)

    def prepare_call(self, contact: str, video: bool = False) -> Prepared:
        chat = self.open_chat(contact)
        label = "video call" if video else "voice call"

        def call() -> str:
            hwnd = self._check_still(chat)
            button = self._find(hwnd, lambda c: c.kind == "Button" and c.name.lower() == label)
            if button is None:
                raise WhatsAppError(f"I can't find the {label} button in WhatsApp.")
            self._click(button)
            return f"Calling {chat} ({label})."

        return Prepared(chat, call, None)

    # -- helpers ------------------------------------------------------------------------
    def _window(self, launch: bool = True) -> int:
        hwnd = self.window()
        if hwnd is None and launch:
            self.start()
            for _ in range(20):                           # up to ~10 s for WhatsApp to start
                self.sleep(0.5)
                hwnd = self.window()
                if hwnd is not None:
                    self.sleep(1.5)                       # let it finish loading the chat list
                    break
        if hwnd is None:
            raise WhatsAppError("WhatsApp isn't open. Install WhatsApp Desktop or open it first.")
        self.bring_front(hwnd)
        return hwnd

    def _find(self, hwnd: int, test: Callable[[Candidate], bool]) -> Candidate | None:
        return next((c for c in self.controls(hwnd) if test(c)), None)

    def _message_box(self, hwnd: int) -> Candidate:
        box = self._find(hwnd, lambda c: c.kind == "Edit" and c.name.lower().startswith("type a message"))
        if box is None:
            raise WhatsAppError("I can't find the message box in WhatsApp.")
        return box

    def _check_still(self, chat: str) -> int:
        """Right before sending/calling: make sure the same chat is still open."""
        hwnd = self._window(launch=False)
        now = self.current_chat(hwnd)
        if now != chat:
            raise WhatsAppError(f"The open chat changed to {now or 'nothing'}, so I didn't do it.")
        return hwnd

    def _click(self, c: Candidate) -> None:
        self.ctl.move_to(*c.center)
        self.ctl.click("left", 1)
