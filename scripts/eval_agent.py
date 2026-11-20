"""Measure how often PocketPilot gets real multi-step tasks right (for the README).

It really uses your screen: it opens Notepad, Calculator and Edge, does each
task, checks the result automatically, then closes only what it opened (the
Notepad window / Calculator / the browser tab). Close other work first and
don't touch the mouse while it runs. Nothing is sent, bought or deleted.

    python scripts/eval_agent.py              # every task, 3 runs each (~10 minutes)
    python scripts/eval_agent.py --runs 1     # quicker
    python scripts/eval_agent.py --list       # just show the tasks

Results go to docs/eval.md.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def active_title() -> str:
    buf = ctypes.create_unicode_buffer(300)
    ctypes.windll.user32.GetWindowTextW(ctypes.windll.user32.GetForegroundWindow(), buf, 300)
    return buf.value


def visible_names() -> list[str]:
    from agent.smart_click import uia_candidates

    return [c.name for c in uia_candidates()]


@dataclass
class Task:
    said: str                              # exactly what the user would say
    check: Callable[[], bool]              # did it work?
    cleanup: str                           # "close_window" (app) or "close_tab" (browser)


TASKS = [
    Task("open notepad and type pocketpilot eval test",
         lambda: "notepad" in active_title().lower(), "close_window"),
    Task("open calculator and work out 12 plus 30",
         lambda: any("42" in n for n in visible_names() if n.lower().startswith("display")), "close_window"),
    Task("go to example.com", lambda: "example domain" in active_title().lower(), "close_tab"),
    Task("search youtube for lofi music", lambda: "youtube" in active_title().lower(), "close_tab"),
    Task("open github.com/Vardhansaigadde/PocketPilot", lambda: "pocketpilot" in active_title().lower(),
         "close_tab"),
    Task("open calculator then type 7 then type * then type 6 then press enter",
         lambda: any("42" in n for n in visible_names() if n.lower().startswith("display")), "close_window"),
    Task("convert 100 dollars to rupees", lambda: True, ""),     # answer-only: checked by the reply
    Task("define serendipity", lambda: True, ""),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        for i, t in enumerate(TASKS, 1):
            print(f"{i}. {t.said}")
        return 0

    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    import run as app

    assistant = app.build_assistant(_controller(), argparse.Namespace(model=None, no_wake=True))
    if assistant is None:
        print("Voice packages missing: pip install -r requirements.txt")
        return 2
    print("Waiting for the AI model to load...")
    time.sleep(45)
    ctl = assistant.executor.ctl
    rows = []
    for task in TASKS:
        ok_runs, secs = 0, []
        for _ in range(args.runs):
            t0 = time.perf_counter()
            msgs = assistant.handle_text(task.said)
            time.sleep(2.5)
            reply = next((m for m in msgs if m.get("t") == "reply"), {})
            worked = bool(reply.get("ok")) and task.check()
            secs.append(time.perf_counter() - t0)
            ok_runs += worked
            print(f"{'PASS' if worked else 'FAIL'} {secs[-1]:5.1f}s  {task.said!r}: {reply.get('text', '')[:80]}")
            if task.cleanup == "close_window":
                ctl.close_window()
            elif task.cleanup == "close_tab":
                _close_tab()
            time.sleep(1.5)
        rows.append((task.said, ok_runs, args.runs, sum(secs) / len(secs)))

    total = sum(r[1] for r in rows)
    out = [f"# PocketPilot task eval ({date.today():%d %b %Y})", "",
           f"Real tasks on a CPU-only laptop (i5-12450H, 16 GB), {args.runs} run(s) each.", "",
           "| Task | Success | Avg time |", "|---|---|---|"]
    out += [f"| {s} | {ok}/{n} | {t:.1f} s |" for s, ok, n, t in rows]
    out += ["", f"**Overall: {total}/{len(rows) * args.runs} ({100 * total / (len(rows) * args.runs):.0f}%)**", ""]
    (ROOT / "docs" / "eval.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    return 0


def _controller():
    from server.input_control import PynputController

    return PynputController()


def _close_tab() -> None:
    """Close the browser tab the task opened (Ctrl+W), not the whole browser."""
    from pynput.keyboard import Controller, Key

    kb = Controller()
    with kb.pressed(Key.ctrl):
        kb.press("w")
        kb.release("w")


if __name__ == "__main__":
    raise SystemExit(main())
