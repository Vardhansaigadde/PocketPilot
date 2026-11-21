"""Fixes for words speech-to-text gets wrong (real examples from the history log)."""

import pytest

from agent.names import KnownNames, plain, sounds_like
from agent.router import fast_path
from agent.whatsapp import DidYouMean, WhatsAppError
from tests.test_whatsapp import make


@pytest.mark.parametrize("said, expected", [
    ("Calama.", {"action": "whatsapp", "contact": "amma", "kind": "voice_call"}),
    ("Message. Kid do. Hi.", {"action": "whatsapp", "contact": "Kid do", "kind": "message", "text": "Hi"}),
    ("Open grid hub", {"action": "goto", "site": "github"}),
    ("open good hub", {"action": "goto", "site": "github"}),
    ("Play Dude in What's Spotify.", {"action": "search", "site": "spotify", "query": "Dude"}),
    ("Play Doudin Spotify.", {"action": "search", "site": "spotify", "query": "dude"}),
    ("Play a song in Spotify.", {"action": "search", "site": "spotify", "query": "a song"}),
    ("Message Amma, Heart. Hi.", {"action": "whatsapp", "contact": "Amma heart", "kind": "message", "text": "Hi"}),
])
def test_router_fixes_common_mishearings(said, expected):
    cmd = fast_path(said).model_dump(exclude_none=True)
    assert {k: cmd[k] for k in expected} == expected


def test_real_names_are_left_alone():
    assert fast_path("go to github").site == "github"
    assert fast_path("show grid").action == "grid"
    assert fast_path("play dude").site == "youtube"


def test_sounds_like_real_mishearings():
    assert sounds_like("Kitya", "Kidduuu 🎀") >= 0.7
    assert sounds_like("kid do", "Kidduuu 🎀") >= 0.7
    assert sounds_like("Amah", "Amma ❤️") >= 0.7
    assert sounds_like("ravi", "Ammadu") < 0.5
    assert plain("Amma ❤️") == "Amma"


def test_known_names_are_saved_and_read_back(tmp_path):
    path = tmp_path / "known_names.json"
    k = KnownNames(path)
    k.add(["Amma ❤️", "Kidduuu 🎀", "Amma"])
    assert KnownNames(path).all() == ["Amma ❤️", "Kidduuu 🎀", "Amma"]
    assert KnownNames(path).plain_names() == ["Amma", "Kidduuu"]


def test_whatsapp_learns_chat_names_it_sees():
    w, wa, _ = make()
    w.open_chat("amma")
    assert "Kidduuu 🎀" in w.known.all() and "Chats" not in w.known.all()


def test_unknown_name_asks_did_you_mean_instead_of_failing():
    w, wa, _ = make()
    w.known.add(["Kidduuu 🎀", "Amma", "Appa"])
    with pytest.raises(DidYouMean) as exc:
        w.open_chat("Kitya")
    assert exc.value.names[0] == "Kidduuu 🎀"
    assert "Did you mean 1) Kidduuu 🎀" in str(exc.value)
    assert wa.open is None                                # nothing opened


def test_family_mishearing_opens_amma():
    w, wa, _ = make()
    assert w.open_chat("a month") == "Amma"


def test_nothing_alike_still_says_not_found():
    w, wa, _ = make()
    with pytest.raises(WhatsAppError, match="couldn't find"):
        w.open_chat("Zebra")


def test_did_you_mean_answer_finishes_the_call():
    from agent.approvals import Approvals
    from agent.commands import WhatsAppCmd
    from agent.executor import Executor
    from tests.test_dispatch import FakeController

    w, wa, _ = make()
    w.known.add(["Kidduuu 🎀"])
    ex = Executor(FakeController(), Approvals(), whatsapp=w, launcher=lambda t: None, app_available=lambda t: True)
    out = ex.run(WhatsAppCmd(action="whatsapp", contact="Kitya", kind="voice_call"))
    assert out.choices == ["Kidduuu 🎀"]
    out = ex.answer_choice("one")
    assert out.approval is not None and wa.open == "Kidduuu 🎀"


def test_whisper_gets_learned_names_as_hints():
    from agent.stt import WhisperTranscriber

    k = KnownNames()
    k.add(["Kidduuu 🎀", "Dheemuluuuu 🐶"])
    t = WhisperTranscriber("base.en", known=k)
    assert "Kidduuu" in t.hotwords() and "Dheemuluuuu" in t.current_hint()
    assert "🎀" not in t.hotwords()


def test_telugu_did_you_mean_reply():
    from agent.telugu import reply

    assert reply("I couldn't find Kitya. Did you mean 1) Kidduuu? Say the number or the name.").startswith(
        "Kitya కనిపించలేదు")
