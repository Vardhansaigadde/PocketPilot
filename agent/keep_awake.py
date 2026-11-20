"""Keep the laptop awake while PocketPilot runs, so the phone can always reach it.

While the laptop sleeps, Windows pauses PocketPilot too, and the phone can't
wake it (browsers can't send Wake-on-LAN packets). So instead PocketPilot asks
Windows not to sleep while it's running:

  mode "charging" (default): only while plugged in, so the battery isn't drained
  mode "always"            : also on battery
  mode "off"               : normal sleep

The screen can still turn off to save power; "wake up" / "open my laptop" turns
it back on. Nothing in Windows' settings is changed: the request ends when
PocketPilot stops (or the mode changes).
"""

from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable

log = logging.getLogger("pocketpilot.awake")

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
MODES = ("charging", "always", "off")
CHECK_EVERY_S = 30.0


class _PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def plugged_in() -> bool:
    status = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return True                     # can't tell: assume plugged in (desktop PCs)
    return status.ACLineStatus != 0     # 1 = on charger, 255 = unknown


def set_state(flags: int) -> None:
    ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))


def screen_locked() -> bool:
    """True while the Windows lock screen is showing (programs can't type there)."""
    user32 = ctypes.windll.user32
    DESKTOP_SWITCHDESKTOP = 0x0100
    desk = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not desk:
        return True
    try:
        return not user32.SwitchDesktop(desk)
    finally:
        user32.CloseDesktop(desk)


class KeepAwake:
    """Holds the "don't sleep" request from its own thread (Windows ties it to a thread)."""

    def __init__(
        self,
        mode: str = "charging",
        power: Callable[[], bool] = plugged_in,
        apply: Callable[[int], None] = set_state,
        every_s: float = CHECK_EVERY_S,
    ) -> None:
        self.mode = mode if mode in MODES else "charging"
        self.power = power
        self.apply = apply
        self.every_s = every_s
        self.holding = False
        self._changed = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="keep-awake", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._changed.set()

    def set_mode(self, mode: str) -> str:
        """Change the mode now; returns what to tell the user."""
        self.mode = mode if mode in MODES else "charging"
        self._changed.set()
        return {"always": "I'll keep the laptop awake, even on battery, while PocketPilot runs.",
                "charging": "I'll keep the laptop awake only while it's charging.",
                "off": "OK, the laptop can sleep normally now."}[self.mode]

    def tick(self) -> bool:
        """Apply the current mode once. Returns whether sleep is being blocked."""
        want = self.mode == "always" or (self.mode == "charging" and self.power())
        if want:
            self.apply(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)   # system on; screen may still turn off
        elif self.holding:
            self.apply(ES_CONTINUOUS)                        # give the normal sleep back
        if want != self.holding:
            log.info("keep awake: %s", "on" if want else "off")
        self.holding = want
        return want

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self.tick()
                self._changed.wait(self.every_s)
                self._changed.clear()
        finally:
            self.apply(ES_CONTINUOUS)                        # always release on exit
            self.holding = False
