"""WhatsApp flow with a fake WhatsApp window: nothing is ever really sent or dialled."""

from dataclasses import replace

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


def make(contacts=("Amma", "Kidduuu 🎀", "Appa"), window=1, contacts_list=None):
    wa = FakeWhatsApp(contacts)
    ctl = Ctl(wa)
    w = WhatsApp(ctl, controls=wa.controls, windows=lambda: [window] if window else [],
                 bring_front=lambda h: None, start=lambda: None, sleep=lambda s: None, contacts=contacts_list,
                 front=lambda h: True)
    return w, wa, ctl


def typed(ctl):
    return [x[1] for x in ctl.calls if x[0] == "type_text"]


def test_open_chat_finds_contact_with_speech_spelling():
    w, wa, _ = make()
    assert w.open_chat("kidd u") == "Kidduuu 🎀"            # emoji kept for the Approve card
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


@pytest.mark.parametrize("heard, searched", [("Amah", "Amma"), ("AMMA", "Amma"), ("amma❤️ in watsapp", "amma heart"),
                                             ("kidd u", "Kidduuu"), ("Ravi", "Ravi")])
def test_contact_names_snap_to_the_contact_list(heard, searched):
    w, _, _ = make(contacts_list=["Amma", "Kidduuu"])
    assert w.resolve_contact(heard) == searched


def test_call_window_is_skipped():
    """During a call WhatsApp has a second window; the one with the chat list must be used."""
    wa = FakeWhatsApp()
    ctl = Ctl(wa)

    def controls(hwnd):
        return [] if hwnd == 99 else wa.controls(hwnd)     # 99 = the call window, no search box

    w = WhatsApp(ctl, controls=controls, windows=lambda: [99, 1], bring_front=lambda h: None,
                 start=lambda: None, sleep=lambda s: None, front=lambda h: True)
    assert w.open_chat("amma") == "Amma"


def test_slow_chat_header_is_waited_for():
    wa = FakeWhatsApp()
    ctl = Ctl(wa)
    late = {"left": 3}

    def controls(hwnd):
        out = wa.controls(hwnd)
        if wa.open and late["left"] > 0:                   # header shows up a moment later
            late["left"] -= 1
            out = [c for c in out if not c.name.startswith("Contact info")]
        return out

    w = WhatsApp(ctl, controls=controls, windows=lambda: [1], bring_front=lambda h: None,
                 start=lambda: None, sleep=lambda s: None, front=lambda h: True)
    assert w.open_chat("amma") == "Amma"


def test_nothing_is_typed_when_whatsapp_is_not_in_front():
    """Windows can refuse to bring WhatsApp forward; then keys must not go to another window."""
    wa = FakeWhatsApp()
    ctl = Ctl(wa)
    w = WhatsApp(ctl, controls=wa.controls, windows=lambda: [1], bring_front=lambda h: None,
                 start=lambda: None, sleep=lambda s: None, front=lambda h: False)
    with pytest.raises(WhatsAppError, match="behind another window"):
        w.prepare_message("amma", "hello")
    assert ctl.calls == []                                  # no click, no typing at all


def test_whatsapp_falling_behind_midway_stops_before_sending():
    wa = FakeWhatsApp()
    ctl = Ctl(wa)
    in_front = {"yes": True}
    w = WhatsApp(ctl, controls=wa.controls, windows=lambda: [1], bring_front=lambda h: None,
                 start=lambda: None, sleep=lambda s: None, front=lambda h: in_front["yes"])
    ready = w.prepare_message("amma", "hello")
    in_front["yes"] = False                                 # another window jumps in front
    with pytest.raises(WhatsAppError):
        ready.go()
    assert ("key", "enter") not in ctl.calls



# ---- two chats with the same name: "Amma ❤️" and "Amma" ------------------------------------------

def two_ammas():
    return make(contacts=("Amma ❤️", "Amma", "Appa"))


def test_same_name_asks_instead_of_guessing():
    w, wa, ctl = two_ammas()
    with pytest.raises(WhatsAppError) as err:
        w.open_chat("amma")
    msg = str(err.value)
    assert msg == "Which amma? 1) Amma ❤️ 2) Amma. Say the name or the number."
    assert err.value.names == ["Amma ❤️", "Amma"]
    assert wa.open is None                                   # nothing opened, nothing typed after


def test_saying_the_emoji_picks_that_chat():
    w, wa, _ = two_ammas()
    assert w.open_chat("amma heart") == "Amma ❤️"
    assert typed_search(w, wa) == "amma"                     # WhatsApp search gets the plain name


def test_just_amma_picks_the_plain_one():
    w, wa, _ = two_ammas()
    assert w.open_chat("just amma") == "Amma"


def test_default_from_the_contact_list():
    w, wa, _ = make(contacts=("Amma ❤️", "Amma"), contacts_list=["Amma ❤️"])
    assert w.open_chat("amma") == "Amma ❤️"                 # POCKETPILOT_CONTACTS=Amma ❤️


def test_approve_card_shows_the_exact_contact():
    w, wa, ctl = two_ammas()
    ex = Executor(ctl, Approvals(), whatsapp=w, app_available=lambda t: True)
    out = run(ex, {"action": "whatsapp", "contact": "amma heart", "kind": "message", "text": "hi"})
    assert out.approval.text == 'Send to Amma ❤️ on WhatsApp: "hi"?'
    out = run(ex, {"action": "whatsapp", "contact": "amma", "kind": "voice_call"})
    assert out.approval is None and out.choices == ["Amma ❤️", "Amma"]


def typed_search(w, wa):
    calls = [c for c in w.ctl.calls if c[0] == "type_text"]
    return calls[0][1]



def test_leftover_search_is_cleared_first():
    """With old text in the search box WhatsApp drops its label; clear it, then search."""
    wa = FakeWhatsApp()
    ctl = Ctl(wa)
    state = {"leftover": True}

    def controls(hwnd):
        out = wa.controls(hwnd)
        if state["leftover"]:
            out = [c for c in out if not c.name.startswith("Search")] + [c_("End icon button", "Button", 300, 50)]
        return out

    real_click = ctl.click

    def click(button, count):
        if ctl.pos == (320, 60):                      # the clear (x) button
            state["leftover"] = False
        real_click(button, count)

    ctl.click = click
    w = WhatsApp(ctl, controls=controls, windows=lambda: [1], bring_front=lambda h: None,
                 start=lambda: None, sleep=lambda s: None, front=lambda h: True)
    assert w.open_chat("appa") == "Appa"


def c_(name, kind, x, y):
    return Candidate(name, kind, (x, y, x + 40, y + 20))



# ---- answering "which one?" -------------------------------------------------------------------

def akkas():
    return make(contacts=("Sharmila Akka", "Yamini Akka", "Leela Akka 💝", "Appa"))


def test_choice_answers():
    from agent.executor import Choice

    c = Choice(None, ["Sharmila Akka", "Yamini Akka", "Leela Akka 💝"], expires=1e18)
    for said, want in [("2", "Yamini Akka"), ("second", "Yamini Akka"), ("the first one", "Sharmila Akka"),
                       ("number 3", "Leela Akka 💝"), ("last", "Leela Akka 💝"), ("Sharmila", "Sharmila Akka"),
                       ("yamini akka", "Yamini Akka"), ("leela akka heart", "Leela Akka 💝"),
                       ("cancel", "cancel"), ("7", None), ("open notepad", None)]:
        assert c.pick(said) == want, said


def test_which_akka_then_answer_finishes_the_message():
    from agent.assistant import Assistant

    w, wa, ctl = akkas()
    ex = Executor(ctl, Approvals(), whatsapp=w, app_available=lambda t: True)
    a = Assistant(ex)
    first = a.handle_text("message akka that hi")
    assert first[0]["text"].startswith("Which akka? 1) Sharmila Akka 2) Yamini Akka 3) Leela Akka")
    assert first[1] == {"t": "choices", "text": first[0]["text"],
                        "options": ["Sharmila Akka", "Yamini Akka", "Leela Akka 💝"]}
    second = a.handle_text("yamini")
    assert second[-1]["t"] == "approve_request"
    assert second[-1]["text"] == 'Send to Yamini Akka on WhatsApp: "hi"?'
    assert ("key", "enter") not in ctl.calls                # still waiting for Approve


def test_answer_by_number_for_a_call():
    from agent.assistant import Assistant

    w, wa, ctl = akkas()
    a = Assistant(Executor(ctl, Approvals(), whatsapp=w, app_available=lambda t: True))
    a.handle_text("call akka")
    assert a.handle_text("3")[-1]["text"] == "Voice call Leela Akka 💝 on WhatsApp?"


def test_a_different_command_drops_the_question():
    from agent.assistant import Assistant

    w, wa, ctl = akkas()
    ex = Executor(ctl, Approvals(), whatsapp=w, app_available=lambda t: True)
    a = Assistant(ex)
    a.handle_text("message akka that hi")
    assert a.handle_text("volume up")[0]["text"] == "Volume up."
    assert ex.choice is None                                # "2" now would be an ordinary phrase


def test_question_expires():
    from agent.assistant import Assistant

    now = [0.0]
    w, wa, ctl = akkas()
    ex = Executor(ctl, Approvals(), whatsapp=w, app_available=lambda t: True, clock=lambda: now[0])
    a = Assistant(ex)
    a.handle_text("message akka that hi")
    now[0] += 200
    out = a.handle_text("yamini")
    assert not any(m.get("t") == "approve_request" for m in out)


def test_cancel_the_question():
    from agent.assistant import Assistant

    w, wa, ctl = akkas()
    a = Assistant(Executor(ctl, Approvals(), whatsapp=w, app_available=lambda t: True))
    a.handle_text("call akka")
    assert a.handle_text("cancel")[0]["text"] == "OK, cancelled."



def test_rows_that_only_mention_the_name_are_not_options():
    w, wa, _ = make(contacts=("Sharmila Akka", "Yamini Akka"))
    real = wa.controls

    def controls(hwnd):
        out = real(hwnd)
        if wa.searched:
            out.append(c("12 Yesterday akka sent a photo", "DataItem", 100, 900))   # name is just "12"
        return out

    w.controls = controls
    with pytest.raises(Exception) as err:
        w.open_chat("akka")
    assert err.value.names == ["Sharmila Akka", "Yamini Akka"]



def test_main_contact_with_unread_messages_is_found():
    """'Akka 💝 🥰' with news is labelled '1 unread message Akka 💝 🥰 ...' by WhatsApp."""
    w, wa, _ = make(contacts=("Akka 💝 🥰", "Sharmila Akka", "Yamini Akka"))
    real = wa.controls

    def controls(hwnd):
        out = real(hwnd)
        return [replace(x, name="1 unread message " + x.name) if x.name.startswith("Akka 💝") else x for x in out]

    w.controls = controls
    assert w.open_chat("akka") == "Akka 💝 🥰"               # the main Akka, no question asked


def test_name_part_skips_unread_and_pinned_labels():
    from agent.whatsapp import name_part

    assert name_part("1 unread message Akka 💝 🥰 Yesterday hi") == "Akka 💝 🥰"
    assert name_part("3 unread messages Akka 10:30 pm ok") == "Akka"
    assert name_part("Pinned chat Amma ❤️ Yesterday") == "Amma ❤️"
