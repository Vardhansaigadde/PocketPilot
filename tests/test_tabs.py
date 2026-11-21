"""Close / reopen tabs, and searching inside the browser that is in front."""

import pytest

from agent.approvals import Approvals
from agent.commands import GoToCmd, HotkeyCmd, SearchCmd
from agent.executor import Executor
from agent.router import fast_path
from agent.windows import has_tabs, is_browser
from tests.test_dispatch import FakeController

EDGE = "kesariya - YouTube and 3 more pages - Personal - Microsoft\u200b Edge"
CHROME = "New Tab - Google Chrome"
NOTEPAD = "notes.txt - Notepad"
EXPLORER = "Downloads - File Explorer"


class FakeSkills:
    amazon_domain = "www.amazon.in"

    def __init__(self):
        self.calls = []

    def search(self, site, query):
        self.calls.append(("search", site, query))
        return f"Searching {site} for {query}."

    def open_site(self, site):
        self.calls.append(("open_site", site))
        return f"Opening {site}."


def make(front):
    ctl, skills = FakeController(), FakeSkills()
    ex = Executor(ctl, Approvals(), skills=skills, launcher=lambda t: None, app_available=lambda t: False,
                  front=lambda: front, sleep=lambda s: None)
    return ex, ctl, skills


def test_window_kinds():
    assert is_browser(EDGE) and is_browser(CHROME) and not is_browser(NOTEPAD)
    assert has_tabs(NOTEPAD) and has_tabs(EDGE) and not has_tabs(EXPLORER)


@pytest.mark.parametrize("said, combo", [
    ("close tab", "close_tab"), ("close this tab", "close_tab"), ("close the current tab", "close_tab"),
    ("reopen closed tab", "reopen_tab"), ("bring back the tab", "reopen_tab"),
])
def test_phrases(said, combo):
    assert fast_path(said) == HotkeyCmd(action="hotkey", combo=combo)


def test_close_window_is_still_its_own_command():
    assert fast_path("close the window").action == "close_window"


@pytest.mark.parametrize("front", [EDGE, CHROME, NOTEPAD])
def test_close_tab_in_apps_with_tabs(front):
    ex, ctl, _ = make(front)
    out = ex.run(HotkeyCmd(action="hotkey", combo="close_tab"))
    assert out.ok and out.say == "Closed the tab." and ("hotkey", "close_tab") in ctl.calls


def test_close_tab_never_presses_ctrl_w_elsewhere():
    ex, ctl, _ = make(EXPLORER)                          # Ctrl+W would close the whole window
    out = ex.run(HotkeyCmd(action="hotkey", combo="close_tab"))
    assert not out.ok and "close the window" in out.say and ctl.calls == []


def test_reopen_only_in_a_browser():
    ex, ctl, _ = make(NOTEPAD)
    assert not ex.run(HotkeyCmd(action="hotkey", combo="reopen_tab")).ok and ctl.calls == []
    ex, ctl, _ = make(CHROME)
    assert ex.run(HotkeyCmd(action="hotkey", combo="reopen_tab")).ok and ("hotkey", "reopen_tab") in ctl.calls


def test_search_opens_a_new_tab_in_the_browser_in_front():
    ex, ctl, skills = make(CHROME)
    out = ex.run(SearchCmd(action="search", site="google", query="cricket score"))
    assert out.say == "Searching Google for cricket score in a new tab."
    assert ctl.calls == [("hotkey", "new_tab"), ("type_text", "https://www.google.com/search?q=cricket+score"),
                         ("key", "delete"), ("key", "enter")]
    assert skills.calls == []                            # no new Edge window


def test_go_to_site_in_the_browser_in_front():
    ex, ctl, skills = make(EDGE)
    out = ex.run(GoToCmd(action="goto", site="github"))
    assert out.ok and out.say.endswith("in a new tab.") and ("hotkey", "new_tab") in ctl.calls


def test_no_browser_in_front_uses_edge_as_before():
    ex, ctl, skills = make(NOTEPAD)
    ex.run(SearchCmd(action="search", site="bing", query="cricket score"))
    assert skills.calls == [("search", "bing", "cricket score")] and ctl.calls == []


def test_spotify_app_still_used_when_installed():
    ctl, skills = FakeController(), FakeSkills()
    ex = Executor(ctl, Approvals(), skills=skills, launcher=lambda t: None, app_available=lambda t: True,
                  front=lambda: CHROME, sleep=lambda s: None)
    ex.run(SearchCmd(action="search", site="spotify", query="dude"))
    assert skills.calls == [("search", "spotify", "dude")]


@pytest.mark.parametrize("said, combo", [
    ("ట్యాబ్ క్లోజ్ చెయ్యి", "close_tab"), ("ఈ ట్యాబ్ మూసెయ్యి", "close_tab"), ("tab close cheyyi", "close_tab"),
    ("ట్యాబ్ మళ్ళీ ఓపెన్ చెయ్యి", "reopen_tab"), ("కొత్త ట్యాబ్", "new_tab"),
])
def test_telugu_phrases(said, combo):
    from agent import telugu

    assert telugu.to_command(said) == HotkeyCmd(action="hotkey", combo=combo)


def test_telugu_replies():
    from agent.telugu import reply

    assert reply("Closed the tab.") == "ట్యాబ్ మూసేశాను."
    assert reply("Searching Google for cricket score in a new tab.") == "కొత్త ట్యాబ్‌లో Googleలో cricket score వెతుకుతున్నాను."


def test_unsaved_notepad_tab_says_it_is_asking_to_save():
    ex, ctl, _ = make("*pocketpilot eval test - Notepad")
    out = ex.run(HotkeyCmd(action="hotkey", combo="close_tab"))
    assert ("hotkey", "close_tab") in ctl.calls
    assert "unsaved changes" in out.say and "press escape" in out.say
    assert not any(c[0] in ("key", "click") for c in ctl.calls)   # never answers the save prompt
