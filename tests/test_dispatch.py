import json

import pytest

from server.input_control import dispatch
from server.protocol import parse_message


class FakeController:
    """Records what would have happened instead of moving the real mouse."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, *args))
        return record


@pytest.mark.parametrize(
    "message, expected",
    [
        ({"t": "move", "dx": 5, "dy": -2}, ("move", 5, -2)),
        ({"t": "click", "button": "right"}, ("click", "right", 1)),
        ({"t": "click", "count": 2}, ("click", "left", 2)),
        ({"t": "button", "action": "down"}, ("button", "left", True)),
        ({"t": "button", "action": "up"}, ("button", "left", False)),
        ({"t": "scroll", "dy": 1.5}, ("scroll", 0.0, 1.5)),
        ({"t": "zoom", "steps": -1}, ("zoom", -1)),
        ({"t": "key", "key": "enter"}, ("key", "enter")),
        ({"t": "text", "text": "hello"}, ("type_text", "hello")),
        ({"t": "hotkey", "combo": "app_next"}, ("hotkey", "app_next")),
        ({"t": "media", "key": "volume_up"}, ("media", "volume_up")),
    ],
)
def test_each_message_calls_one_action(message, expected):
    ctl = FakeController()
    reply = dispatch(parse_message(json.dumps(message)), ctl)
    assert ctl.calls == [expected]
    assert reply is None


def test_ping_gets_pong_and_touches_nothing():
    ctl = FakeController()
    reply = dispatch(parse_message('{"t": "ping", "sent": 123.5}'), ctl)
    assert ctl.calls == []
    assert reply["t"] == "pong" and reply["sent"] == 123.5
