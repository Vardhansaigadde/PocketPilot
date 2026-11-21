"""Find a window by its title and bring it to the front.

Windows won't let a background program (PocketPilot) put a newly opened window
in front, so an app or web page opened from the phone could appear *behind*
whatever is on screen. After opening something we look for its window and
bring it forward with the usual workaround (a tap of Alt, then
SetForegroundWindow), and check that it worked.
"""

from __future__ import annotations

import ctypes
import logging
import time
from typing import Callable

log = logging.getLogger("pocketpilot.windows")


def title_of(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(300)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 300)
    return buf.value


def front_title() -> str:
    return title_of(ctypes.windll.user32.GetForegroundWindow())


def find(match: Callable[[str], bool]) -> int | None:
    """The first visible top-level window whose title matches (top of the stack first)."""
    found: list[int] = []
    user32 = ctypes.windll.user32
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd, _):  # noqa: ANN001 - Windows callback
        if user32.IsWindowVisible(hwnd):
            t = title_of(hwnd)
            if t and match(t):
                found.append(int(hwnd))
                return False
        return True

    user32.EnumWindows(proc(visit), 0)
    return found[0] if found else None


def raise_window(hwnd: int) -> bool:
    """Bring one window to the front. Returns whether it worked."""
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)                       # SW_RESTORE
    for _ in range(3):
        if user32.GetForegroundWindow() == hwnd:
            return True
        user32.keybd_event(0x12, 0, 0, 0)                # tap Alt: lets us take the foreground
        user32.keybd_event(0x12, 0, 0x0002, 0)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        time.sleep(0.2)
    return user32.GetForegroundWindow() == hwnd


def bring_front(match: Callable[[str], bool], wait_s: float = 4.0,
                sleep: Callable[[float], None] = time.sleep) -> bool:
    """Wait for a window whose title matches, then bring it to the front."""
    deadline = time.monotonic() + wait_s
    while True:
        hwnd = find(match)
        if hwnd is not None:
            ok = raise_window(hwnd)
            if not ok:
                log.info("couldn't bring %r to the front", title_of(hwnd))
            return ok
        if time.monotonic() >= deadline:
            return False
        sleep(0.25)


_BROWSERS = ("microsoft edge", "google chrome", "mozilla firefox", "brave", "opera", "vivaldi")
# Apps where Ctrl+W closes a tab (and asks to save first), not the whole window
_TABBED = (*_BROWSERS, "notepad", "visual studio code")


def _plain(title: str) -> str:
    return title.replace("\u200b", "").strip().lower()      # Edge puts a zero-width space in its name


def is_browser(title: str) -> bool:
    """'kesariya - YouTube - Personal - Microsoft Edge' -> True."""
    return _plain(title).endswith(_BROWSERS)


def has_tabs(title: str) -> bool:
    return _plain(title).endswith(_TABBED)


def unsaved(title: str) -> bool:
    """Notepad shows '*notes - Notepad', VS Code '● notes.py - Visual Studio Code' for unsaved work."""
    t = title.strip()
    return not is_browser(t) and (t.startswith("*") or t.startswith("●"))


def is_edge(title: str) -> bool:
    t = title.replace("​", "").lower()             # Edge puts a zero-width space in its name
    return t.endswith("microsoft edge")
