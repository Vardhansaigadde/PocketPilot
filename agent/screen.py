"""See the screen: capture the active window and read its text with Windows' own OCR.

Windows has a built-in, offline text reader (Windows.Media.Ocr). It is small and
fast, so we don't need a big OCR model. Screenshots only ever live in memory:
they are never written to disk and never leave the laptop.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("pocketpilot.screen")


@dataclass(frozen=True)
class Shot:
    """A screenshot plus where it sits on the screen (to turn image positions into clicks)."""
    image: Any          # PIL.Image
    left: int
    top: int


@dataclass(frozen=True)
class TextBox:
    """One line or word of text found on screen, in screen pixels."""
    text: str
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


def foreground_rect() -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the active window, without its invisible shadow border."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    r = RECT()
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) == 0
    if not ok and not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    if r.right - r.left < 50 or r.bottom - r.top < 50:
        return None
    return r.left, r.top, r.right, r.bottom


def capture(window: bool = True) -> Shot:
    """Screenshot of the active window (or the whole screen)."""
    from PIL import ImageGrab

    rect = foreground_rect() if window else None
    if rect is None:
        img = ImageGrab.grab()
        return Shot(img, 0, 0)
    img = ImageGrab.grab(bbox=rect, all_screens=True)
    return Shot(img, rect[0], rect[1])


# ---- OCR ------------------------------------------------------------------------------

class OcrUnavailable(RuntimeError):
    """Windows OCR isn't installed or has no language pack."""


def _bitmap(image: Any) -> Any:
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    rgba = image.convert("RGBA")
    writer = DataWriter()
    writer.write_bytes(rgba.tobytes("raw", "BGRA"))
    return SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, rgba.width, rgba.height)


async def _recognize(image: Any) -> Any:
    from winrt.windows.media.ocr import OcrEngine

    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrUnavailable("Windows OCR has no language installed")
    return await engine.recognize_async(_bitmap(image))


def ocr(shot: Shot, words: bool = False) -> list[TextBox]:
    """Text on the screenshot as lines (or single words), with screen positions."""
    try:
        result = asyncio.run(_recognize(shot.image))
    except ImportError as exc:
        raise OcrUnavailable("Windows OCR packages missing (pip install -r requirements.txt)") from exc
    boxes: list[TextBox] = []
    for line in result.lines:
        rects = [w.bounding_rect for w in line.words]
        if not rects:
            continue
        if words:
            for w in line.words:
                r = w.bounding_rect
                boxes.append(TextBox(w.text, shot.left + int(r.x), shot.top + int(r.y),
                                     int(r.width), int(r.height)))
            continue
        x0 = min(r.x for r in rects)
        y0 = min(r.y for r in rects)
        x1 = max(r.x + r.width for r in rects)
        y1 = max(r.y + r.height for r in rects)
        boxes.append(TextBox(line.text, shot.left + int(x0), shot.top + int(y0),
                             int(x1 - x0), int(y1 - y0)))
    return boxes


def page_text(shot: Shot, max_chars: int = 6000) -> str:
    """All readable text of the screenshot as one string, in reading order.

    Windows OCR already returns lines column by column, so we keep its order
    (sorting by position would mix side-by-side panels together).
    """
    return "\n".join(b.text for b in ocr(shot))[:max_chars]
