"""v7: the local API the MCP bridge uses. Only this laptop, only with the token, only allowed commands."""

from fastapi.testclient import TestClient

from agent.approvals import Approvals
from agent.assistant import Assistant
from agent.executor import Executor
from agent.memory import Memory
from server.main import create_app
from tests.test_dispatch import FakeController
from tests.test_whatsapp import make as make_whatsapp

TOKEN = "secret-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def setup(tmp_path, whatsapp=None):
    ctl = FakeController()
    ex = Executor(ctl, Approvals(), launcher=lambda t: None, app_available=lambda t: True, whatsapp=whatsapp)
    memory = Memory(tmp_path / "history.db")
    app = create_app(token=TOKEN, controller=ctl, assistant=Assistant(ex, memory=memory))
    local = TestClient(app, client=("127.0.0.1", 50000))
    return app, local, ctl, memory


def test_runs_an_allowed_command(tmp_path):
    _, local, ctl, memory = setup(tmp_path)
    r = local.post("/api/run", json={"command": {"action": "scroll", "direction": "down", "amount": 3}}, headers=AUTH)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["reply"] == "Scrolled down."
    assert ("scroll", 0, -3) in ctl.calls
    assert [e.source for e in memory.recall("today")] == ["mcp"]   # logged like phone commands


def test_say_uses_the_normal_phrases(tmp_path):
    _, local, ctl, _ = setup(tmp_path)
    r = local.post("/api/say", json={"text": "volume up"}, headers=AUTH)
    assert r.json()["reply"] == "Volume up." and ("media", "volume_up") in ctl.calls


def test_unknown_actions_are_refused(tmp_path):
    _, local, ctl, _ = setup(tmp_path)
    r = local.post("/api/run", json={"command": {"action": "run_shell", "cmd": "del *"}}, headers=AUTH)
    assert r.status_code == 422 and "Not an allowed" in r.json()["reply"] and ctl.calls == []


def test_needs_the_token(tmp_path):
    _, local, ctl, _ = setup(tmp_path)
    assert local.post("/api/say", json={"text": "volume up"}).status_code == 401
    assert local.post("/api/say", json={"text": "volume up"},
                      headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert ctl.calls == []


def test_only_from_this_laptop(tmp_path):
    app, _, ctl, _ = setup(tmp_path)
    phone = TestClient(app, client=("192.168.1.20", 50000))
    assert phone.post("/api/say", json={"text": "volume up"}, headers=AUTH).status_code == 403
    assert ctl.calls == []


def test_whatsapp_waits_for_approve_on_the_phone(tmp_path):
    w, wa, _ = make_whatsapp()
    app, local, _, _ = setup(tmp_path, whatsapp=w)
    with TestClient(app).websocket_connect(f"/ws?token={TOKEN}") as phone:
        phone.receive_json()                                            # hello
        r = local.post("/api/run", headers=AUTH, json={"command": {
            "action": "whatsapp", "contact": "amma", "kind": "message", "text": "hi"}})
        seen = [phone.receive_json() for _ in range(3)]
    assert r.json()["needs_approval"] and "Approve" in r.json()["reply"]
    assert seen[0]["t"] == "heard" and seen[0]["text"].startswith("AI app:")
    assert any(m["t"] == "approve_request" for m in seen)              # the card is on the phone
    assert wa.open == "Amma"                                            # drafted, not sent


def test_empty_say_is_refused(tmp_path):
    _, local, _, _ = setup(tmp_path)
    assert local.post("/api/say", json={"text": "  "}, headers=AUTH).status_code == 422
