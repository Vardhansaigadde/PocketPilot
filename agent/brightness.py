"""Laptop screen brightness: "brightness up", "brightness 50", the ☀ buttons on the phone.

Uses Windows' own WMI brightness control (the same one the Windows brightness slider
uses). It works for the laptop's built-in screen; most external monitors don't offer it.
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("pocketpilot.brightness")

STEP = 10          # "brightness up" = +10 %
MIN_LEVEL = 5      # never all the way to 0: some screens go black, and you couldn't see to fix it


class Screen(Protocol):
    def get(self) -> int | None: ...
    def set(self, level: int) -> bool: ...


class BrightnessError(RuntimeError):
    """Brightness can't be changed here (no built-in screen, or Windows refused)."""


def clamp(level: int) -> int:
    return max(MIN_LEVEL, min(100, int(level)))


def target(current: int, change: str, level: int | None = None) -> int:
    """The new level for "up" / "down" / "set" (with `level`)."""
    if change == "set":
        if level is None:
            raise ValueError("set needs a level")
        return clamp(level)
    return clamp(current + (STEP if change == "up" else -STEP))


class WindowsScreen:
    """The laptop's built-in screen, through WMI (root\\WMI)."""

    def _wmi(self):  # noqa: ANN202
        import win32com.client

        return win32com.client.GetObject(r"winmgmts:\\.\root\WMI")

    def get(self) -> int | None:
        try:
            for m in self._wmi().ExecQuery("SELECT CurrentBrightness FROM WmiMonitorBrightness"):
                return int(m.CurrentBrightness)
        except Exception:
            log.debug("could not read brightness", exc_info=True)
        return None

    def set(self, level: int) -> bool:
        try:
            methods = list(self._wmi().ExecQuery("SELECT * FROM WmiMonitorBrightnessMethods"))
            if not methods:
                return False
            for m in methods:
                # Named parameters: calling m.WmiSetBrightness(0, level) directly passes them in
                # the wrong order on some systems ("Invalid parameter").
                params = m.Methods_("WmiSetBrightness").InParameters.SpawnInstance_()
                params.Timeout = 0                     # 0 = change it now
                params.Brightness = clamp(level)
                m.ExecMethod_("WmiSetBrightness", params)
            return True
        except Exception:
            log.debug("could not set brightness", exc_info=True)
            return False


class Brightness:
    def __init__(self, screen: Screen | None = None) -> None:
        self.screen = screen or WindowsScreen()

    def change(self, change: str, level: int | None = None) -> int:
        """Apply it and return the new level. Raises BrightnessError if it can't."""
        current = self.screen.get()
        if current is None:
            raise BrightnessError("I can't change the brightness here: it works on the laptop's own screen, "
                                  "not on most external monitors.")
        new = target(current, change, level)
        if not self.screen.set(new):
            raise BrightnessError("Windows didn't let me change the brightness.")
        return new
