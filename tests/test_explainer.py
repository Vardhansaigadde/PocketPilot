"""Screen explainer with a fake screen and a fake Ollama (no real screenshot, no model)."""

import json

import httpx
from PIL import Image

from agent.explainer import ScreenExplainer, error_part, short
from agent.screen import Shot

TRACEBACK = """File Edit View
Traceback (most recent call last):
  File "app.py", line 3, in <module>
    import requests
ModuleNotFoundError: No module named 'requests'
Ln 5, Col 1"""


def make(text="", answer="A short answer.", status=200, seen=None, after=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(status, json={"message": {"content": json.dumps({"answer": answer})}})

    shot = Shot(Image.new("RGB", (1600, 900), "white"), 0, 0)
    return ScreenExplainer(client=httpx.Client(transport=httpx.MockTransport(handler)),
                           capture=lambda: shot, read_text=lambda s: text, after=after)


def test_summarize_sends_screen_text_to_the_text_model():
    seen = []
    out = make("An article about black holes. " * 200, seen=seen).look("summarize")
    assert out == "A short answer."
    body = seen[0]
    assert body["model"] == "qwen3:4b" and "images" not in body["messages"][0]
    assert len(body["messages"][0]["content"]) < 3000          # text is capped


def test_explain_error_sends_only_the_error_part():
    seen = []
    make(TRACEBACK, seen=seen).look("explain_error")
    sent = seen[0]["messages"][0]["content"].split("\n\n", 1)[1]
    assert "ModuleNotFoundError" in sent and "Ln 5" in sent


def test_describe_sends_a_small_screenshot_to_the_vision_model():
    seen = []
    make(seen=seen).look("describe")
    body = seen[0]
    assert body["model"] == "qwen3.5:4b" and body["keep_alive"] == "5m"
    assert len(body["messages"][0]["images"]) == 1


def test_read_needs_no_model_and_is_short():
    seen = []
    out = make("word " * 500, seen=seen).look("read")
    assert seen == [] and len(out) <= 600 and out.endswith("…")


def test_no_text_falls_back_to_vision_for_summaries():
    seen = []
    make("", seen=seen).look("summarize")
    assert seen[0]["model"] == "qwen3.5:4b"


def test_missing_model_and_offline_are_polite():
    assert "ollama pull" in make("text", status=404).look("summarize")

    def offline(request):
        raise httpx.ConnectError("refused")
    ex = ScreenExplainer(client=httpx.Client(transport=httpx.MockTransport(offline)),
                         capture=lambda: Shot(Image.new("RGB", (10, 10)), 0, 0), read_text=lambda s: "hi")
    assert "Ollama" in ex.look("summarize")


def test_after_hook_rewarms_the_command_model():
    calls = []
    make("text", after=lambda: calls.append(1)).look("summarize")
    make("text", after=lambda: calls.append(2)).look("read")      # read uses no model: no re-warm
    assert calls == [1]


def test_error_part_and_short():
    assert error_part(TRACEBACK).startswith("File Edit View\nTraceback")
    assert short("a b c d e f", 6) == "a b c…"
    assert short("hello wonderful world", 12) == "hello…"
