"""Measure how often PocketPilot gets real multi-step tasks right (for the README).

It really uses your screen: it opens Notepad, Calculator, Edge and WhatsApp, does
each task, checks the result automatically, then closes only what it opened (the
Notepad window / Calculator / the browser tab). Close other work first and
don't touch the mouse while it runs. Nothing is sent, bought or deleted: every
WhatsApp message or call stops at the Approve card, which the eval cancels.

    python scripts/eval_agent.py              # every task, 3 runs each (~10 minutes)
    python scripts/eval_agent.py --runs 1     # quicker
    python scripts/eval_agent.py --list       # just show the tasks
    python scripts/eval_agent.py --only 2,3   # re-run some tasks (docs/eval.md is left alone)

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
    check: Callable[[], bool]              # did it work? (looks at the screen)
    cleanup: str                           # "close_window" (app) or "close_tab" (browser)
    group: str = "English"
    setup: tuple[str, ...] = ()            # said first (not timed), e.g. open a search page
    expect: Callable[[list[dict]], bool] | None = None   # did the reply say the right thing?


def approve_card(name: str) -> Callable[[list[dict]], bool]:
    """An Approve card for this contact came up (the eval then cancels it)."""
    return lambda msgs: any(m.get("t") == "approve_request" and name.lower() in m.get("text", "").lower()
                            for m in msgs)


def says(*words: str) -> Callable[[list[dict]], bool]:
    return lambda msgs: all(any(w.lower() in m.get("text", "").lower() for m in msgs) for w in words)


def on_a_video() -> bool:
    import re

    t = re.sub(r"^\(\d+\)\s*", "", active_title().lower())   # "(245) ..." = YouTube's notification count
    return "youtube" in t and not t.startswith("python tutorial - youtube")


def left_results_page() -> bool:
    t = active_title().replace("\u200b", "").lower()
    return t.endswith("microsoft edge") and "google search" not in t


UNTIL_TWO_VIDEOS = "<scroll until two videos are visible>"   # a setup step, not a phrase

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
    # v4: WhatsApp (stops at the Approve card; the eval cancels it)
    Task("message amma that pocketpilot eval test", lambda: True, "", "WhatsApp", expect=approve_card("amma")),
    Task("call amma", lambda: True, "", "WhatsApp", expect=approve_card("amma")),
    Task("message kitya hi", lambda: True, "", "WhatsApp", expect=says("did you mean", "kidduuu")),
    # v5: Telugu
    Task("నోట్‌ప్యాడ్ ఓపెన్ చెయ్యి", lambda: "notepad" in active_title().lower(), "close_window", "Telugu"),
    Task("యూట్యూబ్‌లో తెలుగు పాటలు పెట్టు", lambda: "youtube" in active_title().lower(), "close_tab", "Telugu"),
    Task("హైదరాబాద్‌లో వాతావరణం ఎలా ఉంది", lambda: True, "", "Telugu", expect=says("hyderabad", "°c")),
    Task("అమ్మకి కాల్ చెయ్యి", lambda: True, "", "Telugu", expect=approve_card("amma")),
    Task("ammaki hi ani message pampu", lambda: True, "", "Telugu", expect=approve_card("amma")),
    # results on screen and tabs
    # YouTube's "Videos" filter (sp=EgIQAQ%3D%3D) hides Mix/playlist/Shorts blocks. Ads still appear
    # between videos, so the setup scrolls like a person would until two videos are visible.
    Task("play the second video", on_a_video, "close_tab", "Screen",
         setup=("go to youtube.com/results?search_query=python+tutorial&sp=EgIQAQ%3D%3D", UNTIL_TWO_VIDEOS)),
    Task("open the first result", left_results_page, "close_tab", "Screen",
         setup=("search google for python tutorial",)),
    Task("close this tab", lambda: "cricket" not in active_title().lower(), "", "Screen",
         setup=("search for cricket score",)),
]
SETUP_WAIT_S = 7.0       # a new page loading (YouTube is the slowest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--only", help="task numbers to run, e.g. 2,3 (see --list)")
    parser.add_argument("--no-save", action="store_true", help="don't overwrite docs/eval.md")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")       # Telugu tasks print on any Windows console
    tasks = TASKS
    if args.only:
        tasks = [TASKS[int(n) - 1] for n in args.only.split(",") if n.strip().isdigit()]
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
    for task in tasks:
        ok_runs, secs = 0, []
        for _ in range(args.runs):
            for step in task.setup:
                if step == UNTIL_TWO_VIDEOS:
                    _scroll_until_two_videos(assistant)
                    continue
                assistant.handle_text(step)
                time.sleep(SETUP_WAIT_S if step.startswith(("search", "open", "go")) else 1.5)
            t0 = time.perf_counter()
            msgs = assistant.handle_text(task.said)
            reply = next((m for m in msgs if m.get("t") == "reply"), {})
            _cancel_everything(assistant, msgs)              # never send or call
            worked = False
            if task.expect is not None and not task.expect(msgs):
                pass
            elif reply.get("ok"):
                # check for up to 12 s: the first Edge/Calculator start of the day can be slow
                for _ in range(24):
                    time.sleep(0.5)
                    if task.check():
                        worked = True
                        break
            secs.append(time.perf_counter() - t0)
            ok_runs += worked
            print(f"{'PASS' if worked else 'FAIL'} {secs[-1]:5.1f}s  {task.said!r}: {reply.get('text', '')[:80]}")
            # Only clean up if the window we opened is really in front; never send keys blind.
            front = active_title().replace("​", "").lower()
            if task.cleanup == "close_window" and ("notepad" in front or front == "calculator"):
                ctl.close_window()
            elif task.cleanup == "close_tab" and front.endswith("microsoft edge"):
                _close_tab()
            elif task.cleanup:
                print(f"      (skipped cleanup: '{active_title()[:40]}' is in front, not the window we opened)")
            time.sleep(1.5)
        rows.append((task.said, ok_runs, args.runs, sum(secs) / len(secs), task.group))

    total = sum(r[1] for r in rows)
    out = [f"# PocketPilot task eval ({date.today():%d %b %Y})", "",
           f"Real tasks on a CPU-only laptop (i5-12450H, 16 GB), {args.runs} run(s) each.", "",
           "WhatsApp tasks stop at the Approve card (cancelled by the eval: nothing is sent or called).", "",
           "| Group | Task | Success | Avg time |", "|---|---|---|---|"]
    out += [f"| {g} | {s} | {ok}/{n} | {t:.1f} s |" for s, ok, n, t, g in rows]
    out += ["", f"**Overall: {total}/{len(rows) * args.runs} ({100 * total / (len(rows) * args.runs):.0f}%)**", ""]
    for g in dict.fromkeys(r[4] for r in rows):
        ok_g = sum(r[1] for r in rows if r[4] == g)
        n_g = sum(r[2] for r in rows if r[4] == g)
        out.append(f"- {g}: {ok_g}/{n_g}")
    out.append("")
    if not args.no_save and not args.only:
        (ROOT / "docs" / "eval.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    return 0


def _scroll_until_two_videos(assistant) -> None:  # noqa: ANN001
    """Like a person: scroll (up to 3 times) until at least two videos are on screen."""
    from agent.results import videos
    from agent.smart_click import SmartClicker

    clicker = SmartClicker(budget_s=4)
    for _ in range(4):
        seen = 0
        for _ in range(3):                               # the page may still be waking up
            seen = len(videos(clicker.controls(), on_youtube=True))
            if seen:
                break
            time.sleep(0.7)
        if seen >= 2:
            return
        assistant.handle_text("scroll down")
        time.sleep(1.5)


def _cancel_everything(assistant, msgs: list[dict]) -> None:  # noqa: ANN001
    """Cancel every Approve card and "which one?" question the task produced."""
    for m in msgs:
        if m.get("t") == "approve_request":
            assistant.approve(m["id"], False)
    assistant.executor.choice = None


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
