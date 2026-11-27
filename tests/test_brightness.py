"""Laptop screen brightness: phrases, the command, the phone's ☀ buttons (fake screen only)."""

import pytest
from fastapi.testclient import TestClient

from agent.approvals import Approvals
from agent.brightness import MIN_LEVEL, Brightness, BrightnessError, target
from agent.commands import BrightnessCmd
from agent.executor import Executor
from agent.router import fast_path
from server.main import create_app
from tests.test_dispatch import FakeController


class FakeScreen:
    def __init__(self, level=60, can_set=True):
        self.level, self.can_set = level, can_set

    def get(self):
        return self.level

    def set(self, level):
        if self.can_set:
            self.level = level
        return self.can_set


def test_steps_and_limits():
    assert target(60, "up") == 70 and target(60, "down") == 50
    assert target(98, "up") == 100 and target(8, "down") == MIN_LEVEL     # never fully black
    assert target(60, "set", 0) == MIN_LEVEL and target(60, "set", 150) == 100


def test_change_applies_it():
    screen = FakeScreen(60)
    assert Brightness(screen).change("down") == 50 and screen.level == 50
    assert Brightness(screen).change("set", 80) == 80


def test_no_builtin_screen_explains():
    with pytest.raises(BrightnessError, match="laptop's own screen"):
        Brightness(FakeScreen(None)).change("up")
    with pytest.raises(BrightnessError, match="didn't let me"):
        Brightness(FakeScreen(50, can_set=False)).change("up")


@pytest.mark.parametrize("said, change, level", [
    ("brightness up", "up", None), ("increase the brightness", "up", None), ("make the screen brighter", "up", None),
    ("brightness down", "down", None), ("dim the screen", "down", None), ("make it darker", "down", None),
    ("brightness 50", "set", 50), ("set brightness to 70 percent", "set", 70), ("brightness to fifty", "set", 50),
    ("max brightness", "set", 100), ("minimum brightness", "set", 5),
])
def test_phrases(said, change, level):
    assert fast_path(said) == BrightnessCmd(action="brightness", change=change, level=level)


def test_other_phrases_unchanged():
    assert fast_path("volume up").action == "media"
    assert fast_path("brightness 500") is None                              # not a level


def test_executor_says_the_level():
    ex = Executor(FakeController(), Approvals(), brightness=Brightness(FakeScreen(60)),
                  launcher=lambda t: None, app_available=lambda t: True)
    assert ex.run(BrightnessCmd(action="brightness", change="up")).say == "Brightness 70%."
    off = Executor(FakeController(), Approvals(), launcher=lambda t: None, app_available=lambda t: True)
    assert not off.run(BrightnessCmd(action="brightness", change="up")).ok


def test_phone_buttons_work_without_voice():
    screen = FakeScreen(60)
    app = create_app(token="t", controller=FakeController(), brightness=Brightness(screen))
    with TestClient(app).websocket_connect("/ws?token=t") as ws:
        ws.receive_json()                                                  # hello
        ws.send_json({"t": "brightness", "change": "up"})
        reply = ws.receive_json()
    assert reply == {"t": "reply", "text": "Brightness 70%.", "ok": True, "quiet": True} and screen.level == 70


def test_phone_rejects_bad_brightness_messages():
    from server.protocol import BadMessage, parse_message

    with pytest.raises(BadMessage):
        parse_message('{"t": "brightness", "change": "explode"}')


def test_telugu():
    from agent import telugu

    assert telugu.to_command("brightness penchu") == BrightnessCmd(action="brightness", change="up")
    assert telugu.to_command("బ్రైట్‌నెస్ తగ్గించు") == BrightnessCmd(action="brightness", change="down")
    assert telugu.reply("Brightness 40%.") == "బ్రైట్‌నెస్ 40%."
