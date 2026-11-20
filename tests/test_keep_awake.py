"""Keep-awake and wake-screen, with fake power status (no real Windows calls)."""

import time

from agent.approvals import Approvals
from agent.commands import parse_command
from agent.executor import Executor
from agent.keep_awake import ES_CONTINUOUS, ES_SYSTEM_REQUIRED, KeepAwake
from tests.test_dispatch import FakeController

HOLD = ES_CONTINUOUS | ES_SYSTEM_REQUIRED


def make(mode, plugged=True):
    calls, power = [], {"on": plugged}
    k = KeepAwake(mode, power=lambda: power["on"], apply=calls.append, every_s=0.01)
    return k, calls, power


def test_charging_mode_follows_the_charger():
    k, calls, power = make("charging")
    assert k.tick() is True and calls[-1] == HOLD              # plugged in: no sleep
    power["on"] = False
    assert k.tick() is False and calls[-1] == ES_CONTINUOUS     # unplugged: normal sleep again
    calls.clear()
    assert k.tick() is False and calls == []                    # nothing to release twice


def test_always_and_off():
    k, calls, _ = make("always", plugged=False)
    assert k.tick() is True and calls[-1] == HOLD
    assert "sleep normally" in k.set_mode("off")
    assert k.tick() is False and calls[-1] == ES_CONTINUOUS


def test_unknown_mode_means_charging():
    k, _, _ = make("sometimes")
    assert k.mode == "charging"


def test_thread_releases_on_stop():
    k, calls, _ = make("always")
    k.start()
    time.sleep(0.05)
    k.stop()
    k._thread.join(1)
    assert HOLD in calls and calls[-1] == ES_CONTINUOUS and not k.holding


def run(ex, data):
    return ex.run(parse_command(data))


def test_wake_screen():
    ctl = FakeController()
    ex = Executor(ctl, Approvals(), locked=lambda: False)
    assert run(ex, {"action": "wake_screen"}).say == "Screen is on."
    assert ("wake_screen",) in ctl.calls


def test_wake_screen_when_locked_says_how_to_unlock():
    ex = Executor(FakeController(), Approvals(), locked=lambda: True)
    assert "face, fingerprint or PIN" in run(ex, {"action": "wake_screen"}).say


def test_keep_awake_command_changes_the_mode():
    k, calls, _ = make("charging")
    ex = Executor(FakeController(), Approvals(), awake=k)
    out = run(ex, {"action": "keep_awake", "mode": "always"})
    assert "even on battery" in out.say and k.mode == "always"
