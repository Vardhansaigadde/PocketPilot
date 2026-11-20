"""Numbered grid over the screen for clicking anything by number.

"show grid"  -> 12 × 8 = 96 numbered boxes over the whole screen
"click 14"   -> clicks the centre of box 14
"zoom 14"    -> box 14 is split into 3 × 3 smaller boxes (1-9); then "click 5"

Each box shows its number in the top-left corner and a small dot where the
click will land, so the number doesn't cover what you want to click.
A see-through, always-on-top tkinter window draws it. Tk must only be touched
from its own thread, so requests go through a queue the Tk thread checks
every 30 ms.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass

from .commands import GRID_COLS, GRID_ROWS

log = logging.getLogger("pocketpilot.grid")

ZOOM_COLS = 3
ZOOM_ROWS = 3

KEY_COLOR = "#ff00fe"      # painted pixels of this colour are fully transparent
LINE_COLOR = "#ffd23f"
SHADOW = "#111111"
TEXT_COLOR = "#ffffff"
LABEL_BG = "#1b2027"


@dataclass(frozen=True)
class Layout:
    """Which part of the screen the grid covers and how it is divided."""
    x: int
    y: int
    w: int
    h: int
    cols: int = GRID_COLS
    rows: int = GRID_ROWS

    @property
    def cells(self) -> int:
        return self.cols * self.rows

    def cell_rect(self, cell: int) -> tuple[int, int, int, int]:
        """(left, top, width, height) of a numbered box (1 = top-left, row by row)."""
        if not 1 <= cell <= self.cells:
            raise ValueError(f"cell must be 1..{self.cells}")
        i = cell - 1
        col, row = i % self.cols, i // self.cols
        left = self.x + col * self.w / self.cols
        top = self.y + row * self.h / self.rows
        return int(left), int(top), int(self.w / self.cols), int(self.h / self.rows)

    def cell_center(self, cell: int) -> tuple[int, int]:
        self.cell_rect(cell)                     # checks the number
        i = cell - 1
        col, row = i % self.cols, i // self.cols
        return (round(self.x + (col + 0.5) * self.w / self.cols),
                round(self.y + (row + 0.5) * self.h / self.rows))

    def zoom(self, cell: int) -> Layout:
        """The same box, divided again into ZOOM_COLS × ZOOM_ROWS smaller boxes."""
        left, top, w, h = self.cell_rect(cell)
        return Layout(left, top, w, h, ZOOM_COLS, ZOOM_ROWS)


def full_screen(width: int, height: int) -> Layout:
    return Layout(0, 0, width, height)


class TkGrid:
    def __init__(self) -> None:
        self._jobs: queue.Queue[tuple[str, Layout | None, threading.Event]] = queue.Queue()
        self._ready = threading.Event()
        self.size = (1920, 1080)
        self.layout = full_screen(*self.size)
        self._thread = threading.Thread(target=self._run, name="grid", daemon=True)
        self._thread.start()
        self._ready.wait(5)

    # -- called from any thread ---------------------------------------------------
    @property
    def cells(self) -> int:
        return self.layout.cells

    def show(self) -> None:
        self.layout = full_screen(*self.size)
        self._do("show", self.layout)

    def zoom(self, cell: int) -> None:
        self.layout = self.layout.zoom(cell)
        self._do("show", self.layout)

    def hide(self) -> None:
        self._do("hide", None)

    def cell_center(self, cell: int) -> tuple[int, int]:
        return self.layout.cell_center(cell)

    def reset(self) -> None:
        """Back to the full-screen grid (after a click or when hidden)."""
        self.layout = full_screen(*self.size)

    def _do(self, what: str, layout: Layout | None) -> None:
        done = threading.Event()
        self._jobs.put((what, layout, done))
        done.wait(2)   # wait until the window really changed (so a click lands on the app)

    # -- Tk thread only -----------------------------------------------------------------
    def _run(self) -> None:
        try:
            import tkinter as tk
        except ImportError:  # pragma: no cover
            log.error("tkinter is missing; the grid won't work")
            self._ready.set()
            return
        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", KEY_COLOR)   # Windows only
        except tk.TclError:  # pragma: no cover
            root.attributes("-alpha", 0.35)
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        self.size = (w, h)
        self.layout = full_screen(w, h)
        root.geometry(f"{w}x{h}+0+0")
        canvas = tk.Canvas(root, width=w, height=h, bg=KEY_COLOR, highlightthickness=0)
        canvas.pack()
        self._ready.set()

        def poll() -> None:
            try:
                while True:
                    what, layout, done = self._jobs.get_nowait()
                    if what == "show" and layout is not None:
                        canvas.delete("all")
                        draw(canvas, layout)
                        root.deiconify()
                        root.lift()
                        root.attributes("-topmost", True)
                    else:
                        root.withdraw()
                    root.update_idletasks()
                    root.update()
                    done.set()
            except queue.Empty:
                pass
            root.after(30, poll)

        root.after(30, poll)
        root.mainloop()


def draw(canvas, layout: Layout) -> None:  # noqa: ANN001 - tkinter Canvas
    """Lines (dark shadow + yellow so they show on light and dark apps), corner numbers, centre dots."""
    x0, y0, x1, y1 = layout.x, layout.y, layout.x + layout.w, layout.y + layout.h
    for c in range(layout.cols + 1):
        x = x0 + c * layout.w / layout.cols
        canvas.create_line(x, y0, x, y1, fill=SHADOW, width=3)
        canvas.create_line(x, y0, x, y1, fill=LINE_COLOR, width=1)
    for r in range(layout.rows + 1):
        y = y0 + r * layout.h / layout.rows
        canvas.create_line(x0, y, x1, y, fill=SHADOW, width=3)
        canvas.create_line(x0, y, x1, y, fill=LINE_COLOR, width=1)
    cell_w, cell_h = layout.w / layout.cols, layout.h / layout.rows
    font = max(10, min(18, int(min(cell_w, cell_h) / 6)))
    for n in range(1, layout.cells + 1):
        left, top, _, _ = layout.cell_rect(n)
        cx, cy = layout.cell_center(n)
        label_w = font * (0.75 * len(str(n)) + 0.9)
        canvas.create_rectangle(left + 3, top + 3, left + 3 + label_w, top + 3 + font * 1.6,
                                fill=LABEL_BG, outline=LINE_COLOR)
        canvas.create_text(left + 3 + label_w / 2, top + 3 + font * 0.8, text=str(n),
                           fill=TEXT_COLOR, font=("Segoe UI", font, "bold"))
        canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=LINE_COLOR, outline=SHADOW)
