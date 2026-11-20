"""WhatsApp flow with a fake WhatsApp window: nothing is ever really sent or dialled."""

import pytest

from agent.approvals import Approvals
from agent.executor import Executor
from agent.smart_click import Candidate
from agent.whatsapp import WhatsApp, WhatsAppError
from tests.test_dispatch import FakeController


def c(name, kind, x=0, y=0):
    return Candidate(name, kind, (x, y, x + 40, y + 20))


class FakeWhatsApp:
    """Pretends to be WhatsApp's controls; reacts to clicks on chat rows."""

    def __init__(self, contacts=("Amma", "Kidduuu 🎀", "Appa")):
        self.contacts = list(contacts)
        self.open = None
        self.searched = False

    def controls(self, hwnd):
        out = [c("Search or start a new chat", "Edit", 100, 50), c("Chats", "Button", 10, 10)]
        if self.searched:
            out += [c(f"{name} Yesterday hello", "DataItem", 100, 200 + 60 * i) for i, name in enumerate(self.contacts)]
        if self.open:
            out += [c(f"Contact info {self.open}", "Button", 900, 20), c("Video call", "Button", 1700, 20),
                    c("Voice call", "Button", 1750, 20), c(f"Type a message to {self.open}", "Edit", 900, 1000)]
        return out

    def clicked(self, x, y):
        if (x, y) == (120, 60):
            self.searched = True
        for i, name in enumerate(self.contacts):
            if self.searched and (x, y) == (120, 210 + 60 * i):
                self.open, self.searched = name, False


class Ctl(FakeController):
    def __init__(self, wa):
        super().__init__()
        self.wa, self.pos = wa, None

    def move_to(self, x, y):
        self.calls.append(("move_to", x, y))
        self.pos = (x, y)

    def click(self, button, count):
        self.calls.append(("click", button, count))
        self.wa.clicked(*self.pos)


def make(contacts=("Amma", "Kidduuu 🎀", "Appa"), window=1):
    wa = FakeWhatsApp(contacts)
    ctl = Ctl(wa)
    w = WhatsApp(ctl, controls=wa.controls, window=lambda: window, bring_front=lambda h: None,
                 start=lambda: None, sleep=lambda s: None)
    return w, wa, ctl


def typed(ctl):
    return [x[1] for x in ctl.calls if x[0] == "type_text"]


def test_open_chat_finds_contact_with_speech_spelling():
    w, wa, _ = make()
    assert w.open_chat("kidd u") == "Kidduuu"
    assert wa.open == "Kidduuu 🎀"


def test_message_is_typed_but_not_sent():
    w, wa, ctl = make()
    ready = w.prepare_message("amma", "I'll be late")
    assert ready.chat == "Amma" and typed(ctl) == ["amma", "I'll be late"]
    assert ("key", "enter") not in ctl.calls


def test_send_presses_enter_only_when_the_same_chat_is_open():
    w, wa, ctl = make()
    ready = w.prepare_message("amma", "hi")
    assert ready.go() == "Sent to Amma."
    assert ctl.calls[-1] == ("key", "enter")
    ready2 = w.prepare_message("appa", "hi")
    wa.open = "Amma"                                     # someone switched chats meanwhile
    with pytest.raises(WhatsAppError, match="changed"):
        ready2.go()


def test_cancel_wipes_the_draft():
    w, wa, ctl = make()
    ready = w.prepare_message("amma", "draft")
    ready.undo()
    assert ctl.calls[-2:] == [("hotkey", "select_all"), ("key", "backspace")]


def test_call_clicks_the_right_button():
    w, wa, ctl = make()
    ready = w.prepare_call("amma", video=True)
    assert ("click", "left", 1) in ctl.calls
    before = len(ctl.calls)
    assert ready.go() == "Calling Amma (video call)."
    assert ctl.calls[before] == ("move_to", 1720, 30)    # the "Video call" button


def test_unknown_contact_stops_safely():
    w, wa, ctl = make()
    with pytest.raises(WhatsAppError, match="couldn't find Ravi"):
        w.open_chat("Ravi")
    assert wa.open is None and ("key", "esc") in ctl.calls


def test_wrong_chat_opened_stops():
    w, wa, _ = make(contacts=("Ammamma",))
    with pytest.raises(WhatsAppError):
        w.prepare_call("amma")


def test_whatsapp_not_running():
    w, _, _ = make(window=None)
    with pytest.raises(WhatsAppError, match="isn't open"):
        w.open_chat("amma")


# ---- through the executor: Approve / Cancel -------------------------------------------------

def run(ex, data):
    from agent.commands import parse_command
    return ex.run(parse_command(data))


def make_ex():
    w, wa, ctl = make()
    return Executor(ctl, Approvals(), whatsapp=w, app_available=lambda t: True), wa, ctl


def test_message_waits_for_approve_and_shows_the_text():
    ex, wa, ctl = make_ex()
    out = run(ex, {"action": "whatsapp", "contact": "amma", "kind": "message", "text": "I'll be late"})
    assert out.approval.text == 'Send to Amma on WhatsApp: "I\'ll be late"?'
    assert ("key", "enter") not in ctl.calls
    assert ex.approvals.resolve(out.approval.id, ok=True) == "Sent to Amma."


def test_message_cancel_sends_nothing_and_wipes():
    ex, wa, ctl = make_ex()
    out = run(ex, {"action": "whatsapp", "contact": "amma", "kind": "message", "text": "x"})
    assert ex.approvals.resolve(out.approval.id, ok=False) == "Cancelled."
    assert ("key", "enter") not in ctl.calls and ("hotkey", "select_all") in ctl.calls


def test_stop_also_wipes_the_draft():
    ex, wa, ctl = make_ex()
    run(ex, {"action": "whatsapp", "contact": "amma", "kind": "message", "text": "x"})
    ex.stop()
    assert ("hotkey", "select_all") in ctl.calls and ("key", "enter") not in ctl.calls


def test_call_waits_for_approve():
    ex, wa, ctl = make_ex()
    out = run(ex, {"action": "whatsapp", "contact": "amma", "kind": "voice_call"})
    assert out.approval.text == "Voice call Amma on WhatsApp?"
    clicks_before = ctl.calls.count(("click", "left", 1))
    assert ex.approvals.resolve(out.approval.id, ok=False) == "Cancelled."
    assert ctl.calls.count(("click", "left", 1)) == clicks_before     # no call button pressed


def test_problems_become_polite_replies():
    ex, wa, ctl = make_ex()
    out = run(ex, {"action": "whatsapp", "contact": "nobody", "kind": "voice_call"})
    assert not out.ok and "couldn't find nobody" in out.say
