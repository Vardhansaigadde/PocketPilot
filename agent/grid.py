"""Numbered grid over the screen: say "show grid", then "click 14".

A see-through, always-on-top tkinter window draws 8 × 5 numbered boxes. Tk
must only be touched from its own thread, so show/hide are sent through a
queue that the Tk thread checks every 30 ms.
"""

from __future__ import annotations

import logging
import queue
import threading

from .commands import GRID_COLS, GRID_ROWS

log = logging.getLogger("pocketpilot.grid")

KEY_COLOR = "#ff00fe"      # painted pixels of this colour are fully transparent
LINE_COLOR = "#ffd23f"
TEXT_COLOR = "#ffffff"
LABEL_BG = "#1b2027"


def cell_center(cell: int, width: int, height: int,
                cols: int = GRID_COLS, rows: int = GRID_ROWS) -> tuple[int, int]:
    """Centre of a numbered cell (1 = top-left, numbered row by row)."""
    if not 1 <= cell <= cols * rows:
        raise ValueError(f"cell must be 1..{cols * rows}")
    i = cell - 1
    col, row = i % cols, i // cols
    return int((col + 0.5) * width / cols), int((row + 0.5) * height / rows)


class TkGrid:
    def __init__(self) -> None:
        self._jobs: queue.Queue[tuple[str, threading.Event]] = queue.Queue()
        self._ready = threading.Event()
        self.size = (1920, 1080)
        self._thread = threading.Thread(target=self._run, name="grid", daemon=True)
        self._thread.start()
        self._ready.wait(5)

    # -- called from any thread ---------------------------------------------------
    def show(self) -> None:
        self._do("show")

    def hide(self) -> None:
        self._do("hide")

    def cell_center(self, cell: int) -> tuple[int, int]:
        return cell_center(cell, *self.size)

    def _do(self, what: str) -> None:
        done = threading.Event()
        self._jobs.put((what, done))
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
        root.geometry(f"{w}x{h}+0+0")
        canvas = tk.Canvas(root, width=w, height=h, bg=KEY_COLOR, highlightthickness=0)
        canvas.pack()
        self._draw(canvas, w, h)
        self._ready.set()

        def poll() -> None:
            try:
                while True:
                    what, done = self._jobs.get_nowait()
                    if what == "show":
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

    @staticmethod
    def _draw(canvas, w: int, h: int) -> None:  # noqa: ANN001 - tkinter Canvas
        for c in range(1, GRID_COLS):
            x = c * w / GRID_COLS
            canvas.create_line(x, 0, x, h, fill=LINE_COLOR, width=2)
        for r in range(1, GRID_ROWS):
            y = r * h / GRID_ROWS
            canvas.create_line(0, y, w, y, fill=LINE_COLOR, width=2)
        size = max(14, int(min(w / GRID_COLS, h / GRID_ROWS) / 6))
        for n in range(1, GRID_COLS * GRID_ROWS + 1):
            x, y = cell_center(n, w, h)
            canvas.create_oval(x - size * 1.1, y - size * 1.1, x + size * 1.1, y + size * 1.1,
                               fill=LABEL_BG, outline=LINE_COLOR, width=2)
            canvas.create_text(x, y, text=str(n), fill=TEXT_COLOR,
                               font=("Segoe UI", size, "bold"))
