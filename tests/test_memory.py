"""History log: what gets stored, periods, answers and clearing (in-memory SQLite)."""

from datetime import datetime, timedelta

from agent.approvals import Approvals
from agent.assistant import Assistant
from agent.executor import Executor
from agent.memory import Memory, describe
from tests.test_dispatch import FakeController


class Clock:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at


def test_log_and_recall_periods():
    clock = Clock(datetime(2026, 11, 20, 10, 0))
    m = Memory(clock=clock)
    m.log("phone mic", "open notepad", {"action": "open_app", "app": "notepad"}, True, "Opening Notepad.")
    clock.at = datetime(2026, 11, 21, 9, 30)
    m.log("typed", "weather", {"action": "weather"}, True, "Sunny")
    clock.at = datetime(2026, 11, 21, 10, 0)
    assert [e.said for e in m.recall("yesterday")] == ["open notepad"]
    assert [e.said for e in m.recall("today")] == ["weather"]
    assert [e.said for e in m.recall("last_hour")] == ["weather"]
    assert len(m.recall("this_week")) == 2               # Fri 20 and Sat 21 Nov 2026 share a week


def test_memory_questions_are_not_listed():
    m = Memory()
    m.log("typed", "what did I do today", {"action": "memory"}, True, "...")
    assert m.recall("today") == []


def test_describe():
    clock = Clock(datetime(2026, 11, 21, 9, 5))
    m = Memory(clock=clock)
    m.log("typed", "open notepad", {"action": "open_app"}, True, "ok")
    assert describe(m.recall("today"), "today") == "Today: 09:05 open notepad."
    assert "don't have anything" in describe([], "yesterday")


def test_clear():
    m = Memory()
    m.log("typed", "a", None, True, "")
    m.log("typed", "b", None, True, "")
    assert m.clear() == 2 and m.recall("today") == []


def test_file_database_survives_restart(tmp_path):
    path = tmp_path / "data" / "history.db"
    Memory(path).log("typed", "open notepad", {"action": "open_app"}, True, "ok")
    assert [e.said for e in Memory(path).recall("today")] == ["open notepad"]


def make(memory, summarize=None):
    ex = Executor(FakeController(), Approvals(), launcher=lambda t: None, memory=memory,
                  summarize=summarize, app_available=lambda t: True)
    return Assistant(ex, memory=memory)


def test_assistant_logs_commands_with_their_source():
    m = Memory()
    a = make(m)
    a.handle_text("volume up")
    a.handle_text("open notepad", source="laptop mic")
    entries = m.recall("today")
    assert [(e.source, e.said, e.action, e.ok) for e in entries] == [
        ("typed", "volume up", "media", True), ("laptop mic", "open notepad", "open_app", True)]


def test_what_did_i_do_today():
    m = Memory()
    a = make(m)
    a.handle_text("open notepad")
    out = a.handle_text("what did I do today")
    assert out[0]["text"].startswith("Today:") and "open notepad" in out[0]["text"]


def test_long_days_are_summarized_by_the_model():
    m = Memory()
    for i in range(12):
        m.log("typed", f"command {i}", {"action": "media"}, True, "ok")
    seen = []
    a = make(m, summarize=lambda text: seen.append(text) or "You mostly changed the volume.")
    assert a.handle_text("what did I do today")[0]["text"] == "You mostly changed the volume."
    assert "command 11" in seen[0]


def test_clear_history_needs_approve():
    m = Memory()
    m.log("typed", "x", None, True, "")
    a = make(m)
    msgs = a.handle_text("clear my history")
    assert msgs[1]["t"] == "approve_request" and len(m.recall("today")) >= 1
    assert a.approve(msgs[1]["id"], True)[0]["text"].startswith("Deleted")
    assert m.recall("today") == []
