"""End-to-end check of the WebSocket. Skipped if FastAPI isn't installed."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from server.main import create_app  # noqa: E402
from tests.test_dispatch import FakeController  # noqa: E402

TOKEN = "test-token-0123456789"


def make_client():
    ctl = FakeController()
    return TestClient(create_app(TOKEN, ctl)), ctl


def test_phone_page_is_served():
    client, _ = make_client()
    r = client.get("/")
    assert r.status_code == 200 and "PocketPilot" in r.text


def test_ca_certificate_is_served_when_given(tmp_path):
    ca = tmp_path / "pocketpilot-ca.crt"
    ca.write_bytes(b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n")
    client = TestClient(create_app(TOKEN, FakeController(), ca_cert=ca))
    r = client.get("/pocketpilot-ca.crt")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/x-x509-ca-cert"
    assert r.content == ca.read_bytes()


def test_no_ca_route_without_a_ca():
    client, _ = make_client()
    assert client.get("/pocketpilot-ca.crt").status_code == 404


def test_wrong_token_is_refused():
    client, ctl = make_client()
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws?token=wrong") as ws:
            ws.receive_json()
    assert exc.value.code == 1008
    assert ctl.calls == []


def test_right_token_moves_the_mouse():
    client, ctl = make_client()
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        assert ws.receive_json()["t"] == "hello"
        ws.send_text('{"t": "move", "dx": 4, "dy": 2}')
        ws.send_text('{"t": "ping", "sent": 1}')
        assert ws.receive_json()["t"] == "pong"
    assert ("move", 4, 2) in ctl.calls
    assert ("release_all",) in ctl.calls  # cleaned up on disconnect


def make_voice_client(transcript="open notepad"):
    from agent.approvals import Approvals
    from agent.assistant import Assistant
    from agent.executor import Executor
    from tests.test_executor import FakeTranscriber

    ctl, launched = FakeController(), []
    ex = Executor(ctl, Approvals(), launcher=launched.append)
    app = create_app(TOKEN, ctl, assistant=Assistant(ex, transcriber=FakeTranscriber(transcript)))
    return TestClient(app), ctl, launched


def read_until(ws, kind):
    seen = []
    while True:
        m = ws.receive_json()
        seen.append(m)
        if m["t"] == kind:
            return m, seen


def test_typed_command_runs_and_replies():
    client, _, launched = make_voice_client()
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        assert ws.receive_json()["assistant"] is True
        ws.send_text('{"t": "command", "text": "open calculator"}')
        reply, _ = read_until(ws, "reply")
        assert reply == {"t": "reply", "text": "Opening Calculator.", "ok": True}
    assert launched == ["calculator:"]


def test_audio_frame_is_transcribed():
    client, _, launched = make_voice_client("Open Notepad.")
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_json()
        ws.send_bytes(b"fake-webm-audio")
        heard, _ = read_until(ws, "heard")
        assert heard["text"] == "Open Notepad."
        read_until(ws, "reply")
    assert launched == ["notepad.exe"]


def test_too_long_audio_is_rejected():
    from server.protocol import MAX_AUDIO_BYTES

    client, _, launched = make_voice_client()
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_json()
        ws.send_bytes(b"x" * (MAX_AUDIO_BYTES + 1))
        assert ws.receive_json()["t"] == "error"
    assert launched == []


def test_close_window_needs_approve_over_the_socket():
    client, ctl, _ = make_voice_client()
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_json()
        ws.send_text('{"t": "command", "text": "close the window"}')
        req, _ = read_until(ws, "approve_request")
        assert ("close_window",) not in ctl.calls
        ws.send_text('{"t": "approve", "id": "%s", "ok": true}' % req["id"])
        reply, _ = read_until(ws, "reply")
        assert reply["text"] == "Closed the window."
    assert ("close_window",) in ctl.calls


def test_stop_message():
    client, ctl, _ = make_voice_client()
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_json()
        ws.send_text('{"t": "stop"}')
        reply, _ = read_until(ws, "reply")
        assert reply["text"] == "Stopped."
    assert ("release_all",) in ctl.calls


def test_commands_without_assistant_are_refused_politely():
    client, ctl = make_client()
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_json()
        ws.send_text('{"t": "command", "text": "open notepad"}')
        m = ws.receive_json()
        assert m["t"] == "reply" and m["ok"] is False


def test_bad_message_gets_an_error_not_an_action():
    client, ctl = make_client()
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.receive_json()
        ws.send_text('{"t": "key", "key": "f13"}')
        assert ws.receive_json()["t"] == "error"
    assert not any(c[0] == "key" for c in ctl.calls)
