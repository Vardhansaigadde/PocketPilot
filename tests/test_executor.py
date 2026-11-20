"""The executor does exactly one safe thing per command (fake mouse, fake apps)."""

import pytest

from agent.approvals import Approvals
from agent.apps import APPS, find_app
from agent.assistant import Assistant
from agent.commands import BadCommand, parse_command
from agent.executor import Executor
from tests.test_dispatch import FakeController


class FakeGrid:
    def __init__(self):
        self.visible = False

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def cell_center(self, cell):
        return (cell * 10, cell * 20)


class FakeSkills:
    def __init__(self):
        self.calls = []

    def weather(self, place):
        self.calls.append(("weather", place))
        return "Sunny"

    def air_quality(self, place):
        self.calls.append(("air", place))
        return "Good"

    def wiki(self, topic):
        self.calls.append(("wiki", topic))
        return "A summary"

    def search(self, site, query):
        self.calls.append(("search", site, query))
        return "Searching"

    def open_site(self, site):
        self.calls.append(("site", site))
        return f"Opening {site}."


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make(clock=None):
    ctl, launched = FakeController(), []
    approvals = Approvals(clock=clock or Clock())
    ex = Executor(ctl, approvals, skills=FakeSkills(), grid=FakeGrid(), launcher=launched.append,
                  app_available=lambda target: True)
    return ex, ctl, launched


def run(ex, data):
    return ex.run(parse_command(data))


def test_scroll_down_is_negative_wheel():
    ex, ctl, _ = make()
    run(ex, {"action": "scroll", "direction": "down", "amount": 3})
    assert ctl.calls == [("scroll", 0, -3)]


def test_open_app_uses_the_fixed_target():
    ex, _, launched = make()
    out = run(ex, {"action": "open_app", "app": "notepad"})
    assert launched == ["notepad.exe"] and out.say == "Opening Notepad."


def test_unknown_app_is_rejected_before_anything_runs():
    with pytest.raises(BadCommand):
        parse_command({"action": "open_app", "app": "cmd.exe"})
    with pytest.raises(BadCommand):
        parse_command({"action": "open_app", "app": "powershell"})


def test_extra_fields_and_unknown_actions_are_rejected():
    with pytest.raises(BadCommand):
        parse_command({"action": "open_app", "app": "notepad", "args": "/c del"})
    with pytest.raises(BadCommand):
        parse_command({"action": "run_shell", "cmd": "dir"})
    with pytest.raises(BadCommand):
        parse_command(["open_app"])


def test_no_terminal_apps_in_the_allow_list():
    for bad in ("cmd", "powershell", "terminal", "command prompt", "wt"):
        assert find_app(bad) is None
    targets = " ".join(t for _, t in APPS.values()).lower()
    assert "cmd" not in targets and "powershell" not in targets


def test_close_window_waits_for_approve():
    ex, ctl, _ = make()
    out = run(ex, {"action": "close_window"})
    assert out.approval is not None
    assert ("close_window",) not in ctl.calls          # nothing yet
    assert ex.approvals.resolve(out.approval.id, ok=True) == "Closed the window."
    assert ("close_window",) in ctl.calls


def test_close_window_cancel_does_nothing():
    ex, ctl, _ = make()
    out = run(ex, {"action": "close_window"})
    assert ex.approvals.resolve(out.approval.id, ok=False) == "Cancelled."
    assert ("close_window",) not in ctl.calls
    # the same id can't be reused afterwards
    assert "expired" in ex.approvals.resolve(out.approval.id, ok=True)
    assert ("close_window",) not in ctl.calls


def test_approval_expires():
    clock = Clock()
    ex, ctl, _ = make(clock)
    out = run(ex, {"action": "close_window"})
    clock.now += 31
    assert "expired" in ex.approvals.resolve(out.approval.id, ok=True)
    assert ("close_window",) not in ctl.calls


def test_stop_cancels_approvals_hides_grid_and_releases_mouse():
    ex, ctl, _ = make()
    pending = run(ex, {"action": "close_window"}).approval
    run(ex, {"action": "grid", "show": True})
    assert ex.grid.visible
    out = run(ex, {"action": "stop"})
    assert out.say == "Stopped."
    assert not ex.grid.visible
    assert ("release_all",) in ctl.calls
    assert "expired" in ex.approvals.resolve(pending.id, ok=True)
    assert ("close_window",) not in ctl.calls


def test_grid_click_moves_then_clicks_and_hides_grid():
    ex, ctl, _ = make()
    run(ex, {"action": "grid", "show": True})
    run(ex, {"action": "grid_click", "cell": 7, "button": "right"})
    assert ctl.calls == [("move_to", 70, 140), ("click", "right", 1)]
    assert not ex.grid.visible


def test_skills_are_called():
    ex, _, _ = make()
    assert run(ex, {"action": "weather", "place": "Pune"}).say == "Sunny"
    run(ex, {"action": "search", "site": "youtube", "query": "lofi"})
    assert ex.skills.calls == [("weather", "Pune"), ("search", "youtube", "lofi")]


def test_failure_becomes_a_polite_reply():
    ex, _, _ = make()

    def boom(target):
        raise OSError("not installed")

    ex.launch = boom
    out = run(ex, {"action": "open_app", "app": "spotify"})
    assert not out.ok and "didn't work" in out.say


# ---- assistant glue ---------------------------------------------------------------

class FakePlanner:
    def __init__(self, data):
        self.data, self.asked = data, []

    def to_command(self, text):
        self.asked.append(text)
        return parse_command(self.data)


def test_assistant_fast_path_skips_the_ai():
    ex, ctl, _ = make()
    planner = FakePlanner({"action": "unknown"})
    msgs = Assistant(ex, planner).handle_text("volume up")
    assert planner.asked == []
    assert msgs == [{"t": "reply", "text": "Volume up.", "ok": True}]
    assert ("media", "volume_up") in ctl.calls


def test_assistant_uses_the_ai_for_other_phrases():
    ex, _, launched = make()
    planner = FakePlanner({"action": "open_app", "app": "calculator"})
    msgs = Assistant(ex, planner).handle_text("I need to do some maths")
    assert planner.asked == ["I need to do some maths"]
    assert launched == ["calculator:"]
    assert msgs[0]["ok"]


def test_assistant_without_ai_says_it_did_not_understand():
    ex, _, _ = make()
    msgs = Assistant(ex).handle_text("do something clever")
    assert msgs[0]["ok"] is False and "didn't understand" in msgs[0]["text"]


def test_assistant_sends_an_approve_request():
    ex, _, _ = make()
    msgs = Assistant(ex).handle_text("close this window")
    assert msgs[1]["t"] == "approve_request" and msgs[1]["seconds"] == 30


class FakeTranscriber:
    def __init__(self, text):
        self.text = text

    def transcribe(self, audio):
        return self.text


def test_assistant_audio_reports_what_it_heard():
    ex, ctl, _ = make()
    msgs = Assistant(ex, transcriber=FakeTranscriber(" Scroll down. ")).handle_audio(b"x")
    assert msgs[0] == {"t": "heard", "text": "Scroll down."}
    assert ("scroll", 0, -5) in ctl.calls


def test_assistant_silence():
    ex, _, _ = make()
    msgs = Assistant(ex, transcriber=FakeTranscriber("")).handle_audio(b"x")
    assert msgs[0]["ok"] is False and "didn't catch" in msgs[0]["text"]


# ---- websites and step-by-step commands --------------------------------------------

def test_goto_uses_the_site_skill():
    ex, _, _ = make()
    ex.skills.open_site = lambda site: f"Opening {site}."
    assert run(ex, {"action": "goto", "site": "github"}).say == "Opening github."


def test_steps_run_in_order_with_waits():
    ex, ctl, launched = make()
    waits = []
    msgs = Assistant(ex, sleep=waits.append).handle_text(
        "open notepad then type hello then press enter")
    assert launched == ["notepad.exe"]
    assert ctl.calls == [("type_text", "hello"), ("key", "enter")]
    assert waits == [2.0, 0.4]                      # long wait after opening an app
    assert msgs == [{"t": "reply", "text": "Opening Notepad. Typed it. Pressed enter.", "ok": True}]


def test_steps_stop_at_the_first_problem():
    ex, ctl, launched = make()
    msgs = Assistant(ex, sleep=lambda s: None).handle_text(
        "open notepad then do something weird then press enter")
    assert launched == ["notepad.exe"]
    assert ("key", "enter") not in ctl.calls        # nothing after the failed step
    assert msgs[0]["ok"] is False and "Stopped at step 2" in msgs[0]["text"]


def test_steps_wait_for_approve():
    ex, ctl, _ = make()
    msgs = Assistant(ex, sleep=lambda s: None).handle_text("scroll down then close the window then press enter")
    assert [m["t"] for m in msgs] == ["reply", "approve_request"]
    assert ("key", "enter") not in ctl.calls


def test_missing_app_opens_its_website_instead():
    ex, _, launched = make()
    ex.app_available = lambda target: target != "spotify:"
    out = run(ex, {"action": "open_app", "app": "spotify"})
    assert launched == []                                   # no broken app link
    assert ex.skills.calls == [("site", "https://open.spotify.com")]
    assert "isn't installed" in out.say and out.ok


def test_installed_app_opens_normally():
    ex, _, launched = make()
    run(ex, {"action": "open_app", "app": "spotify"})
    assert launched == ["spotify:"] and ex.skills.calls == []


# ---- smart click ----------------------------------------------------------------------------

class FakeClicker:
    def __init__(self, hit):
        self.hit, self.asked = hit, []

    def find(self, target):
        self.asked.append(target)
        return self.hit


def test_smart_click_moves_and_clicks():
    from agent.smart_click import Candidate

    ex, ctl, _ = make()
    ex.clicker = FakeClicker(Candidate("Equals", "Button", (100, 200, 140, 240)))
    out = run(ex, {"action": "click_on", "target": "equals"})
    assert ctl.calls == [("move_to", 120, 220), ("click", "left", 1)]
    assert out.say == "Clicked Equals."


def test_smart_click_risky_button_waits_for_approve():
    from agent.smart_click import Candidate

    ex, ctl, _ = make()
    ex.clicker = FakeClicker(Candidate("Send", "Button", (0, 0, 20, 20)))
    out = run(ex, {"action": "click_on", "target": "send"})
    assert out.approval is not None and ctl.calls == []
    assert ex.approvals.resolve(out.approval.id, ok=True) == "Clicked Send."
    assert ("click", "left", 1) in ctl.calls


def test_smart_click_not_found_suggests_grid():
    ex, ctl, _ = make()
    ex.clicker = FakeClicker(None)
    out = run(ex, {"action": "click_on", "target": "unicorn"})
    assert not out.ok and "show grid" in out.say and ctl.calls == []


def test_screen_command_tells_the_phone_to_wait():
    class FakeScreen:
        def look(self, mode):
            return f"{mode} done"

    ex, _, _ = make()
    ex.screen = FakeScreen()
    early = []
    msgs = Assistant(ex, notify=early.extend).handle_text("summarize this page")
    assert early and "Looking at your screen" in early[0]["text"]
    assert msgs[0]["text"] == "summarize done"
    early.clear()
    Assistant(ex, notify=early.extend).handle_text("read the screen")    # fast: no wait message
    assert early == []
