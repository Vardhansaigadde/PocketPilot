"""Screen explainer: "what's on my screen?", "summarize this page", "explain this error", "read this".

- summarize / explain / read: Windows OCR reads the text of the active window,
  then the text model (qwen3:4b) summarizes or explains it. Reading text is
  more accurate than a small vision model squinting at a picture.
- describe: a 768 px screenshot goes to the vision model (qwen3.5:4b), which
  unloads itself after 5 idle minutes to free memory.
Everything stays on the laptop; screenshots are never saved.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Any, Callable

import httpx

from . import screen

log = logging.getLogger("pocketpilot.explainer")

TEXT_LIMIT = 2000          # characters of screen text sent to the model (~500 tokens, ~15 s on a CPU)
READ_LIMIT = 600           # characters read aloud for "read the screen"
VISION_SIZE = 768          # screenshot size for the vision model (~35 s on a CPU)
TIMEOUT_S = 180.0

SUMMARIZE = ("Below is the text on the user's screen (from OCR, so menus and buttons are mixed in). "
             "Summarize the main content in 2-3 short, simple sentences. Ignore menus, buttons and ads. "
             "Plain text only.")
EXPLAIN = ("Below is text from the user's screen that contains an error. In simple English, say in 2-3 short "
           "sentences what the error means and the most likely fix. Plain text only.")
DESCRIBE = "In 2-3 short, simple sentences, tell the user what is on their screen. Plain text only."

# Forcing this shape stops the model from "thinking out loud" before it answers.
ANSWER_SHAPE = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


_ERROR_WORDS = re.compile(r"error|exception|traceback|failed|failure|not found|denied|invalid|cannot|"
                          r"can't|unable|warning|fatal|refused|timed out|crash", re.I)


def error_part(text: str, limit: int = 1500) -> str:
    """The lines around the first error-looking line (errors are usually short)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _ERROR_WORDS.search(line):
            start = max(0, i - 3)
            return "\n".join(lines[start:start + 25])[:limit]
    return text[:limit]


def short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if text[limit - 1] != " ":            # don't stop in the middle of a word
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


class ScreenExplainer:
    def __init__(
        self,
        text_model: str = "qwen3:4b",
        vision_model: str = "qwen3.5:4b",
        base_url: str = "http://127.0.0.1:11434",
        client: httpx.Client | None = None,
        capture: Callable[[], Any] = screen.capture,
        read_text: Callable[[Any], str] = screen.page_text,
        after: Callable[[], None] | None = None,
    ) -> None:
        self.text_model = text_model
        self.vision_model = vision_model
        self.url = base_url.rstrip("/") + "/api/chat"
        self.client = client or httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, connect=3.0))
        self.capture = capture
        self.read_text = read_text
        self.after = after       # e.g. re-warm the command model once we're done

    def look(self, mode: str) -> str:
        try:
            return self._look(mode)
        except httpx.ConnectError:
            return "I can't reach the AI model. Is Ollama running?"
        except httpx.TimeoutException:
            return "That took too long. Try again in a moment."
        except screen.OcrUnavailable as exc:
            return f"I can't read the screen: {exc}."
        finally:
            if mode != "read" and self.after is not None:
                try:
                    self.after()
                except Exception:  # pragma: no cover - best effort
                    log.exception("after-hook failed")

    def _look(self, mode: str) -> str:
        shot = self.capture()
        if mode == "describe":
            return self._ask(self.vision_model, DESCRIBE, image=shot.image, keep_alive="5m")
        text = self.read_text(shot).strip()
        if not text:
            if mode == "read":
                return "I can't find any text to read on the screen."
            return self._ask(self.vision_model, DESCRIBE, image=shot.image, keep_alive="5m")
        if mode == "read":
            return short(text, READ_LIMIT)
        if mode == "explain_error":
            return self._ask(self.text_model, EXPLAIN, text=error_part(text))
        return self._ask(self.text_model, SUMMARIZE, text=text[:TEXT_LIMIT])

    def _ask(self, model: str, instruction: str, text: str = "", image: Any = None,
             keep_alive: str = "1h") -> str:
        message: dict[str, Any] = {"role": "user", "content": instruction + ("\n\n" + text if text else "")}
        if image is not None:
            small = image.copy()
            small.thumbnail((VISION_SIZE, VISION_SIZE))
            buf = io.BytesIO()
            small.convert("RGB").save(buf, "JPEG", quality=80)
            message["images"] = [base64.b64encode(buf.getvalue()).decode()]
        r = self.client.post(self.url, json={
            "model": model, "messages": [message], "stream": False, "think": False,
            "keep_alive": keep_alive, "options": {"temperature": 0.2, "num_predict": 200},
            "format": ANSWER_SHAPE,
        })
        if r.status_code == 404:
            return f"The model {model} isn't downloaded. On the laptop run: ollama pull {model}"
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "").strip()
        try:
            answer = str(json.loads(content).get("answer", ""))
        except (ValueError, AttributeError):
            answer = content            # older Ollama without structured output
        return short(answer, 600) or "Sorry, I couldn't work that out."
