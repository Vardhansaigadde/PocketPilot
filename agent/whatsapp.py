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
from dataclasses import dataclass, replace
from typing import Callable

from server.input_control import Controller

from .smart_click import (
    EMOJI_WORD_SET, Candidate, best_match, emoji_to_words, normalize, score, uia_candidates,
)

log = logging.getLogger("pocketpilot.whatsapp")

TITLE = re.compile(r"^(?:\(\d+\) )?WhatsApp$")
CHAT_ROWS = ("DataItem", "ListItem", "TreeItem")
MATCH = 0.85                 # how sure we must be that the open chat is the right person
TIE = 0.05                   # chats scoring this close to the best one count as "also a match"

# A chat row is "<name> <time or day> <last message>": the name ends where the time starts.
_ROW_END = re.compile(
    r"\s(?:\d{1,2}:\d{2}(?:\s?[ap]m)?|yesterday|today|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|\d{1,2}/\d{1,2}/\d{2,4}|typing|online|unread)\b",
    re.I,
)
_EXACT = re.compile(r"^(?:just|only|plain|normal)\s+", re.I)


# Bits WhatsApp puts BEFORE the name in a row's label when a chat has news, e.g.
# "1 unread message Akka 💝 🥰 Yesterday ...", "Pinned chat ...", "Muted ...".
_ROW_START = re.compile(
    r"^(?:\s*(?:\d+\s+unread\s+messages?|unread|pinned(?:\s+chat)?|muted(?:\s+chat)?|archived|new)\s*[,.:]?\s*)+",
    re.I,
)


def clean_row(row: str) -> str:
    """'1 unread message Akka 💝 🥰 Yesterday hi' -> 'Akka 💝 🥰 Yesterday hi'."""
    return _ROW_START.sub("", row).strip() or row


def name_part(row: str) -> str:
    """'Amma ❤️ Yesterday Ippude...' -> 'Amma ❤️' (also with "1 unread message" in front)."""
    row = clean_row(row)
    m = _ROW_END.search(row)
    return (row[: m.start()] if m else row).strip()


def search_text(contact: str) -> str:
    """What to type in WhatsApp's search: the name without emoji or emoji words
    ("amma heart" -> "amma"), because WhatsApp search doesn't know "heart"."""
    words = [w for w in normalize(contact).split() if w not in EMOJI_WORD_SET]
    return " ".join(words) or contact


def how_to_say(name: str) -> str:
    """How the user can pick this chat: 'amma heart' for "Amma ❤️", 'just amma' for "Amma"."""
    n = normalize(name)
    return n if any(w in EMOJI_WORD_SET for w in n.split()) else f"just {n}"


class WhatsAppError(Exception):
    """Something to tell the user, e.g. "I couldn't find Amma in WhatsApp"."""


class AmbiguousContact(WhatsAppError):
    """Several chats match ("Sharmila Akka", "Yamini Akka", ...): the user must pick one."""

    def __init__(self, contact: str, names: list[str]) -> None:
        self.contact = contact
        self.names = names
        listed = " ".join(f"{i}) {n}" for i, n in enumerate(names, 1))
        super().__init__(f"Which {contact}? {listed}. Say the name or the number.")


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


def find_windows() -> list[int]:
    """WhatsApp's inner (fast) windows: class Chrome_WidgetWin_1, title "WhatsApp" / "(3) WhatsApp".
    During a call there is a second one (the call window), so callers pick the one with a chat list."""
    found: list[int] = []
    user32 = ctypes.windll.user32
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd, _):  # noqa: ANN001 - Windows callback
        if user32.IsWindowVisible(hwnd) and _class(hwnd) == "Chrome_WidgetWin_1" and TITLE.match(_title(hwnd)):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(proc(visit), 0)
    return found


def find_outer() -> int | None:
    """The window you actually SEE. New WhatsApp draws in this WinUI window, while the
    fast Chrome_WidgetWin_1 window we read buttons from is an invisible input layer on top."""
    found: list[int] = []
    user32 = ctypes.windll.user32
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd, _):  # noqa: ANN001 - Windows callback
        if (user32.IsWindowVisible(hwnd) and _class(hwnd) == "WinUIDesktopWin32WindowClass"
                and TITLE.match(_title(hwnd))):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(proc(visit), 0)
    return found[0] if found else None


def _is_whatsapp(hwnd: int) -> bool:
    return bool(hwnd) and TITLE.match(_title(hwnd)) is not None and _class(hwnd) in (
        "Chrome_WidgetWin_1", "WinUIDesktopWin32WindowClass")


def is_front(hwnd: int) -> bool:
    """Is WhatsApp (this window, its visible WinUI window, or another window of it) in front?"""
    user32 = ctypes.windll.user32
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    if fg == hwnd or _is_whatsapp(fg):
        return True
    GA_ROOTOWNER = 3
    if user32.GetAncestor(fg, GA_ROOTOWNER) == user32.GetAncestor(hwnd, GA_ROOTOWNER):
        return True
    a, b = ctypes.c_ulong(), ctypes.c_ulong()
    user32.GetWindowThreadProcessId(fg, ctypes.byref(a))
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(b))
    return a.value == b.value


def _raise(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    try:
        from pywinauto.controls.hwndwrapper import HwndWrapper

        HwndWrapper(hwnd).set_focus()
    except Exception:
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 0x0002, 0)
        user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    time.sleep(0.2)


def focus(hwnd: int) -> None:
    """Bring WhatsApp to the front, or raise. Windows often refuses this for a program
    running in the background, so: restore if minimised, try pywinauto, then the
    usual Alt-key workaround, and check it really worked."""
    user32 = ctypes.windll.user32
    outer = find_outer()
    for h in (outer, hwnd):                         # the visible window first, then the input layer
        if h and user32.IsIconic(h):
            user32.ShowWindow(h, 9)                 # SW_RESTORE
    if outer:
        _raise(outer)
    for _ in range(3):
        try:
            from pywinauto.controls.hwndwrapper import HwndWrapper

            HwndWrapper(hwnd).set_focus()
        except Exception:
            pass
        if is_front(hwnd):
            return
        VK_MENU, KEYUP = 0x12, 0x0002               # a tap of Alt lets us take the foreground
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYUP, 0)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        time.sleep(0.25)
        if is_front(hwnd):
            return
    raise WhatsAppError("I couldn't bring WhatsApp to the front, so I didn't type anything. "
                        "Click WhatsApp once on the laptop and try again.")


def launch() -> None:
    import os

    os.startfile("whatsapp:")  # type: ignore[attr-defined]


class WhatsApp:
    """Drives WhatsApp Desktop. Every outside thing is passed in, so tests use fakes."""

    def __init__(
        self,
        controller: Controller,
        controls: Callable[[int], list[Candidate]] = uia_candidates,
        windows: Callable[[], list[int]] = find_windows,
        bring_front: Callable[[int], None] = focus,
        start: Callable[[], None] = launch,
        sleep: Callable[[float], None] = time.sleep,
        contacts: list[str] | None = None,
        front: Callable[[int], bool] = is_front,
    ) -> None:
        self.ctl = controller
        self.controls = controls
        self.windows = windows
        self.contacts = [c.strip() for c in (contacts or []) if c.strip()]
        self.front = front
        self._hwnd: int | None = None
        self.bring_front = bring_front
        self.start = start
        self.sleep = sleep

    # -- public -------------------------------------------------------------------------
    def resolve_contact(self, heard: str) -> str:
        """Clean up what speech-to-text heard, and snap it to a known contact if one is close
        ("Amah" -> "Amma"). Known contacts come from POCKETPILOT_CONTACTS in .env."""
        name = re.sub(r"[^\w\s.'-]", " ", emoji_to_words(heard))      # "❤️" -> "heart", drop punctuation
        name = re.sub(r"\b(?:on|in|via|over)?\s*(?:whatsapp|whats ?app|what'?s ?app|wats ?app|watsapp|whatsap)\b",
                      " ", name, flags=re.I)
        name = " ".join(name.split()).strip(" .,'-") or heard.strip()
        if self.contacts:
            best = max(self.contacts, key=lambda c: score(name, c))
            if score(name, best) >= 0.6:
                return best
        return name

    def open_chat(self, contact: str) -> str:
        """Open the chat with `contact` and return its real name (e.g. "Kidduuu 🎀").

        If two chats fit equally well ("Amma ❤️" and "Amma"), it doesn't guess: it asks
        the user to say "amma heart" or "just amma"."""
        exact = bool(_EXACT.match(contact.strip()))
        contact = self.resolve_contact(_EXACT.sub("", contact.strip()))
        hwnd = self._window()
        search = self._search_box(hwnd)
        if search is None:
            raise WhatsAppError("I can't find WhatsApp's search box. Is WhatsApp open and signed in?")
        self._click(search)
        self._select_all()
        self._key("backspace")
        self._type(search_text(contact))
        # match on the row without "1 unread message" etc. in front of the name
        rows = [replace(c, name=clean_row(c.name)) for c in self._settled_rows(hwnd)]
        if exact:                                         # "just amma": the name must be exactly that
            rows = [c for c in rows if normalize(name_part(c.name)) == normalize(contact)]
        row = best_match(contact, rows)
        if row is None:
            self._key("esc")
            raise WhatsAppError(f"I couldn't find {contact} in WhatsApp.")
        names = self._close_names(contact, rows, row.score)
        if len(names) > 1:
            self._key("esc")
            raise AmbiguousContact(contact, names[:6])
        self._click(row)
        chat = None
        for _ in range(10):                               # wait up to ~3 s for the chat to open
            self.sleep(0.3)
            chat = self.current_chat(hwnd)
            if chat is not None:
                break
        if chat is None or score(contact, chat) < MATCH or (exact and normalize(chat) != normalize(contact)):
            raise WhatsAppError(f"I opened {chat or 'a chat'}, not {contact}, so I stopped.")
        return chat

    def current_chat(self, hwnd: int | None = None) -> str | None:
        """Name of the open chat, from the header button "Contact info <name>"."""
        hwnd = hwnd or self._window(launch=False)
        header = self._find(hwnd, lambda c: c.kind == "Button" and c.name.lower().startswith("contact info "))
        if header is None:
            return None
        return header.name[len("Contact info "):].strip() or None   # keeps the emoji: "Amma ❤️"

    def prepare_message(self, contact: str, text: str) -> Prepared:
        chat = self.open_chat(contact)
        hwnd = self._window(launch=False)
        box = self._message_box(hwnd)
        self._click(box)
        self._type(text)                                  # typed, NOT sent

        def send() -> str:
            self._check_still(chat)
            self._click(self._message_box(self._window(launch=False)))
            self._key("enter")
            return f"Sent to {chat}."

        def wipe() -> None:
            hwnd2 = self._window(launch=False)
            if self.current_chat(hwnd2) == chat:
                self._click(self._message_box(hwnd2))
                self._select_all()
                self._key("backspace")

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
    def _main_window(self) -> int | None:
        """The WhatsApp window with the chat list (not a call window)."""
        wins = self.windows()
        for hwnd in wins:
            if self._find(hwnd, lambda c: c.kind == "Edit" and c.name.lower().startswith("search")):
                return hwnd
        return wins[0] if wins else None

    def _window(self, launch: bool = True) -> int:
        hwnd = self._main_window()
        if hwnd is None and launch:
            self.start()
            for _ in range(20):                           # up to ~10 s for WhatsApp to start
                self.sleep(0.5)
                hwnd = self._main_window()
                if hwnd is not None:
                    self.sleep(1.5)                       # let it finish loading the chat list
                    break
        if hwnd is None:
            raise WhatsAppError("WhatsApp isn't open. Install WhatsApp Desktop or open it first.")
        self.bring_front(hwnd)
        self._hwnd = hwnd
        return hwnd

    def _settled_rows(self, hwnd: int) -> list[Candidate]:
        """Search results, once they stop changing. WhatsApp shows matching chats first and
        contacts a moment later, so reading too early can miss a second "Amma"."""
        self.sleep(1.0)
        rows: list[Candidate] = [c for c in self.controls(hwnd) if c.kind in CHAT_ROWS]
        for _ in range(4):                                # up to ~2 s more
            self.sleep(0.5)
            again = [c for c in self.controls(hwnd) if c.kind in CHAT_ROWS]
            if [c.name for c in again] == [c.name for c in rows]:
                break
            rows = again
        return rows

    def _search_box(self, hwnd: int) -> Candidate | None:
        """WhatsApp's search box. While it still holds an old search it loses its
        "Search or start a new chat" label, so clear it first (the ✕ button, or Esc)."""
        def find() -> Candidate | None:
            return self._find(hwnd, lambda c: c.kind == "Edit" and c.name.lower().startswith("search"))

        box = find()
        if box is not None:
            return box
        for attempt in range(2):                          # 1st: the clear (x) button, 2nd: Esc
            clear = self._find(hwnd, lambda c: c.kind == "Button" and c.name.lower() in (
                "end icon button", "clear search", "cancel search", "close search"))
            if clear is not None and attempt == 0:
                self._click(clear)
            else:
                self._key("esc")
            for _ in range(4):                            # give WhatsApp a moment to reset the box
                self.sleep(0.25)
                box = find()
                if box is not None:
                    return box
        return None

    @staticmethod
    def _close_names(contact: str, rows: list[Candidate], best: float) -> list[str]:
        """Different chat names that match (almost) as well as the best one."""
        names: list[str] = []
        for c in rows:
            n = name_part(c.name)
            # judge the NAME, not the whole row ("1 unread message ... akka" is not an Akka)
            if score(contact, c.name) >= best - TIE and score(contact, n) >= 0.6 and re.search(r"[^\W\d_]", n):
                if normalize(n) not in [normalize(x) for x in names]:
                    names.append(n)
        return names

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

    def _guard(self) -> None:
        """Never click or type unless WhatsApp is really in front: otherwise the keys
        would land in whatever window is covering it."""
        if self._hwnd is not None and not self.front(self._hwnd):
            self.bring_front(self._hwnd)
            if not self.front(self._hwnd):
                raise WhatsAppError("WhatsApp went behind another window, so I stopped. Try again.")

    def _click(self, c: Candidate) -> None:
        self._guard()
        self.ctl.move_to(*c.center)
        self.ctl.click("left", 1)

    def _type(self, text: str) -> None:
        self._guard()
        self.ctl.type_text(text)

    def _key(self, name: str) -> None:
        self._guard()
        self.ctl.key(name)

    def _select_all(self) -> None:
        self._guard()
        self.ctl.hotkey("select_all")
