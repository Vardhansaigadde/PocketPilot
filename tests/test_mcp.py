"""v7: the MCP bridge (pocketpilot_mcp.py). Fake HTTP only; nothing on the real laptop moves."""

import asyncio
import json

import httpx
import pytest

from pocketpilot_mcp import APPROVE_NOTE, NOT_RUNNING, PocketPilotLink, create_server


def call(server, name, **args):
    result = asyncio.run(server.call_tool(name, args))
    return " ".join(getattr(c, "text", "") for c in result.content)


class Recorder:
    """A fake PocketPilot: remembers each request and answers like the local API."""

    def __init__(self, reply=None):
        self.requests = []
        self.reply = reply or {"ok": True, "reply": "Done.", "needs_approval": False, "choices": None}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.url.path, json.loads(request.content), request.headers["authorization"]))
        return httpx.Response(200, json=self.reply)


def server_with(tmp_path, reply=None):
    (tmp_path / "token.txt").write_text("tok\n", encoding="utf-8")
    fake = Recorder(reply)
    return create_server(PocketPilotLink(transport=httpx.MockTransport(fake), data_dir=tmp_path)), fake


def test_lists_the_tools(tmp_path):
    server, _ = server_with(tmp_path)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"pocketpilot", "open_app", "weather", "read_screen", "whatsapp_message", "stop"} <= names
    assert "approve" not in " ".join(names)                     # an AI app can never approve


@pytest.mark.parametrize("tool, args, command", [
    ("open_app", {"app": "notepad"}, {"action": "open_app", "app": "notepad"}),
    ("weather", {"place": "Hyderabad"}, {"action": "weather", "place": "Hyderabad"}),
    ("weather", {}, {"action": "weather"}),
    ("web_search", {"query": "lofi"}, {"action": "search", "site": "google", "query": "lofi"}),
    ("convert_currency", {"amount": 100, "from_currency": "usd", "to_currency": "inr"},
     {"action": "currency", "amount": 100, "from_cur": "USD", "to_cur": "INR"}),
    ("click", {"target": "Sign in", "double": True}, {"action": "click_on", "target": "Sign in", "button": "left", "count": 2}),
    ("scroll", {"direction": "down", "amount": 999}, {"action": "scroll", "direction": "down", "amount": 50}),
    ("brightness", {"change": "set", "level": 40}, {"action": "brightness", "change": "set", "level": 40}),
    ("whatsapp_call", {"contact": "Amma", "video": True}, {"action": "whatsapp", "contact": "Amma", "kind": "video_call"}),
    ("stop", {}, {"action": "stop"}),
])
def test_each_tool_builds_one_allowed_command(tmp_path, tool, args, command):
    server, fake = server_with(tmp_path)
    call(server, tool, **args)
    path, body, auth = fake.requests[0]
    assert path == "/api/run" and body == {"command": command} and auth == "Bearer tok"


def test_plain_instruction_goes_to_say(tmp_path):
    server, fake = server_with(tmp_path)
    call(server, "pocketpilot", instruction="open notepad and type hi")
    assert fake.requests[0][:2] == ("/api/say", {"text": "open notepad and type hi"})


def test_tells_the_ai_to_wait_for_approve(tmp_path):
    server, _ = server_with(tmp_path, {"ok": True, "reply": "Message to Amma is ready.", "needs_approval": True})
    text = call(server, "whatsapp_message", contact="Amma", text="hi")
    assert text.startswith("Message to Amma is ready.") and APPROVE_NOTE.strip() in text


def test_which_one_options_are_passed_on(tmp_path):
    server, _ = server_with(tmp_path, {"ok": True, "reply": "Which Akka?", "choices": ["Akka", "Sharmila Akka"]})
    assert "Options: Akka; Sharmila Akka." in call(server, "whatsapp_message", contact="Akka", text="hi")


def test_pocketpilot_not_running(tmp_path):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    (tmp_path / "token.txt").write_text("tok", encoding="utf-8")
    server = create_server(PocketPilotLink(transport=httpx.MockTransport(refuse), data_dir=tmp_path))
    assert call(server, "weather") == NOT_RUNNING
    no_token = create_server(PocketPilotLink(data_dir=tmp_path / "nothing"))
    assert call(no_token, "weather") == NOT_RUNNING


def test_end_to_end_through_the_real_local_api(tmp_path):
    """MCP tool -> pocketpilot_mcp -> /api/run -> assistant -> executor (fake mouse)."""
    from fastapi.testclient import TestClient

    from agent.approvals import Approvals
    from agent.assistant import Assistant
    from agent.executor import Executor
    from server.main import create_app
    from tests.test_dispatch import FakeController

    ctl = FakeController()
    ex = Executor(ctl, Approvals(), launcher=lambda t: None, app_available=lambda t: True)
    app = create_app(token="tok", controller=ctl, assistant=Assistant(ex))
    local = TestClient(app, client=("127.0.0.1", 50000))
    (tmp_path / "token.txt").write_text("tok", encoding="utf-8")
    def forward(request: httpx.Request) -> httpx.Response:              # MCP bridge -> real local API
        r = local.post(request.url.path, content=request.content, headers=dict(request.headers))
        return httpx.Response(r.status_code, json=r.json())

    server = create_server(PocketPilotLink(transport=httpx.MockTransport(forward), data_dir=tmp_path))
    assert call(server, "media", key="volume_up") == "Volume up."
    assert ("media", "volume_up") in ctl.calls
