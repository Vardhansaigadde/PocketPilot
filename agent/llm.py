"""The AI planner: a local Ollama model turns a free-form request into ONE command.

The model is forced to answer in the Command JSON shape (structured output) and
the answer is validated again with Pydantic. If it's not a valid command, we
say "didn't understand"; nothing runs.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import httpx

from skills import air_quality, weather, web_search, websites, wikipedia

from .apps import APPS
from .assistant import DIDNT_UNDERSTAND, PlannerError
from .commands import GRID_CELLS, BadCommand, Command, UnknownCmd, command_schema, parse_command

log = logging.getLogger("pocketpilot.llm")

WARM_UP_TIMEOUT_S = 180.0   # first load from disk on a CPU can take about a minute

SYSTEM_PROMPT = f"""You control a Windows laptop for the user. Turn their request into exactly ONE JSON action.
Reply with JSON only. Choose "action" from:
- scroll: direction "up"/"down", amount 1-20 (default 5)
- click: button "left"/"right"/"middle", count 1 or 2
- type: text to type into the active window
- key: one of enter, backspace, delete, tab, esc, space, up, down, left, right, home, end, page_up, page_down
- media: volume_up, volume_down, mute, play_pause, next, prev (next/previous song or track = these keys)
- hotkey: app_next, app_prev, task_view, show_desktop, copy, paste, cut, undo, select_all,
  new_tab, next_tab, prev_tab, back, forward, refresh, address_bar (browser)
- open_app: app is one of {", ".join(APPS)}
- close_window: close the active window (the user will be asked to approve)
- grid: show true/false (numbered grid over the screen for clicking)
- grid_click: cell 1-{GRID_CELLS}, button, count
- click_on: target = the name of a button, link or tab on screen, button, count
- screen: mode describe (what's on screen, what am I doing/looking at) / summarize (what a page or article
  says) / explain_error / read (read the text aloud)
- weather: place (city) or null for the home city. {weather.DESCRIPTION}
- air_quality: place or null. {air_quality.DESCRIPTION}
- wiki: topic. {wikipedia.DESCRIPTION}
- goto: site = a website name or address. {websites.DESCRIPTION} Known names: {", ".join(sorted(websites.SITES))}
- search: site bing/google/youtube/amazon/github/chatgpt/spotify, query. {web_search.DESCRIPTION}
- stop: stop everything
- unknown: say = one short friendly sentence, when nothing above fits or the request is unsafe.
Rules: never invent apps or actions. Prefer a useful action over unknown: when the user
describes a need, pick the app or website that fits it. Use an app when one on the list
fits (sums or maths -> calculator, writing code -> vscode, notes -> notepad); use goto for
online things (practising coding problems -> a coding practice website, films -> a streaming site).
If the user names a specific app that is not in the open_app list, use unknown (never open a
different app instead). Payments, passwords, OTPs, booking, deleting files, sending messages
and running commands are not allowed: use unknown.
Examples:
"make it louder" -> {{"action":"media","key":"volume_up"}}
"I want to listen to some lofi" -> {{"action":"search","site":"youtube","query":"lofi music"}}
"open something to write notes" -> {{"action":"open_app","app":"notepad"}}
"go back to the previous page" -> {{"action":"hotkey","combo":"back"}}
"hit the next button" -> {{"action":"click_on","target":"next"}}
"what is this article about" -> {{"action":"screen","mode":"summarize"}}
"look at my display and tell me what's there" -> {{"action":"screen","mode":"describe"}}
"I want to check my emails" -> {{"action":"goto","site":"gmail"}}
"find the react repository on github" -> {{"action":"search","site":"github","query":"react"}}
"is it hot outside in Chennai" -> {{"action":"weather","place":"Chennai"}}
"who invented the telephone" -> {{"action":"wiki","topic":"invention of the telephone"}}
"let me solve some programming challenges" -> {{"action":"goto","site":"leetcode"}}
"I want to draw something" ->{{"action":"open_app","app":"paint"}}
"open photoshop" -> {{"action":"unknown","say":"I can't open Photoshop. I can open: {", ".join(APPS)}."}}
"pay my electricity bill" -> {{"action":"unknown","say":"I can't make payments. I can open a search page for you instead."}}
"""


def _strip_discriminator(node: Any) -> Any:
    """Ollama's schema-to-grammar converter doesn't need Pydantic's 'discriminator' hints."""
    if isinstance(node, dict):
        return {k: _strip_discriminator(v) for k, v in node.items() if k != "discriminator"}
    if isinstance(node, list):
        return [_strip_discriminator(v) for v in node]
    return node


class OllamaPlanner:
    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434",
                 client: httpx.Client | None = None, timeout: float = 60.0) -> None:
        self.model = model
        self.url = base_url.rstrip("/") + "/api/chat"
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=3.0))
        self.schema = _strip_discriminator(command_schema())

    def _body(self, text: str, strict: bool) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "keep_alive": "1h",   # stay in memory for an hour after each use
            "options": {"temperature": 0, "num_predict": 160},
            "format": self.schema if strict else "json",
        }
        if strict:
            body["think"] = False   # qwen3: answer straight away, no long reasoning
        return body

    def warm_up(self) -> None:
        """Load the model and read its instructions in the background, so the first
        real command is fast (a cold start can take 30+ s on a CPU)."""
        def run() -> None:
            try:
                self.to_command("volume up", timeout=WARM_UP_TIMEOUT_S)
                log.info("AI model %s ready", self.model)
            except Exception as exc:  # Ollama not running, model not pulled...
                log.warning("AI model not ready: %s", exc)
        threading.Thread(target=run, name="ai-warmup", daemon=True).start()

    def _ask(self, text: str, timeout: float | None = None) -> str:
        extra = {"timeout": timeout} if timeout else {}
        try:
            r = self.client.post(self.url, json=self._body(text, strict=True), **extra)
            if r.status_code == 400:
                # Older Ollama or a model without "think": retry with plain JSON mode.
                log.warning("Ollama rejected the strict request (%s); retrying", r.text[:200])
                r = self.client.post(self.url, json=self._body(text, strict=False), **extra)
        except httpx.ConnectError as exc:
            raise PlannerError("I can't reach the AI model. Is Ollama running?") from exc
        except httpx.TimeoutException as exc:
            raise PlannerError("The AI model took too long. Try a simpler command.") from exc
        if r.status_code == 404:
            raise PlannerError(f"The AI model isn't downloaded. On the laptop run: ollama pull {self.model}")
        if r.status_code >= 400:
            raise PlannerError("The AI model had a problem. Try again.")
        return r.json().get("message", {}).get("content", "")

    def to_command(self, text: str, timeout: float | None = None) -> Command:
        content = self._ask(text, timeout)
        try:
            data = json.loads(content)
            cmd = parse_command(data)
        except (json.JSONDecodeError, BadCommand) as exc:
            log.warning("model gave an unusable answer %r (%s)", content[:300], exc)
            return UnknownCmd(action="unknown", say=DIDNT_UNDERSTAND)
        return cmd
