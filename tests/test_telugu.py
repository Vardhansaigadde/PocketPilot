"""Telugu and Tenglish commands (no AI, no WhatsApp, no internet)."""

import pytest

from agent.telugu import applies, fix_names, normalise, to_command, to_english, transliterate


@pytest.mark.parametrize("word, latin", [
    ("అమ్మ", "amma"), ("అక్క", "akka"), ("శర్మిల", "sharmila"), ("పెంచు", "penchu"),
    ("తగ్గించు", "tagginchu"), ("పంపు", "pampu"), ("చెయ్యి", "cheyyi"), ("కిందకి", "kindaki"),
    ("హైదరాబాద్", "haidaraabaad"), ("౧౪", "14"),
])
def test_transliterate(word, latin):
    assert transliterate(word) == latin


def test_endings_are_split_and_originals_kept():
    words = normalise("అమ్మకి హాయ్ అని మెసేజ్ పంపు")
    assert [w.norm for w in words] == ["amma", "ki", "hi", "ani", "message", "pampu"]
    assert words[2].orig == "హాయ్"


@pytest.mark.parametrize("said, expected", [
    ("అమ్మకి కాల్ చెయ్యి", {"action": "whatsapp", "contact": "Amma", "kind": "voice_call", "text": None}),
    ("ammaki call cheyyi", {"action": "whatsapp", "contact": "Amma", "kind": "voice_call", "text": None}),
    ("అమ్మకి వీడియో కాల్ చెయ్యి", {"action": "whatsapp", "contact": "Amma", "kind": "video_call", "text": None}),
    ("శర్మిల అక్కకి కాల్ చెయ్యి", {"action": "whatsapp", "contact": "Sharmila Akka", "kind": "voice_call", "text": None}),
    ("అక్కకి హాయ్ అని మెసేజ్ పంపు", {"action": "whatsapp", "contact": "Akka", "kind": "message", "text": "హాయ్"}),
    ("akka ki nenu vastunna ani message pampu",
     {"action": "whatsapp", "contact": "Akka", "kind": "message", "text": "nenu vastunna"}),
    ("నోట్‌ప్యాడ్ ఓపెన్ చెయ్యి", {"action": "open_app", "app": "notepad"}),
    ("notepad open cheyyi", {"action": "open_app", "app": "notepad"}),
    ("వాట్సాప్ ఓపెన్ చెయ్యి", {"action": "open_app", "app": "whatsapp"}),
    ("youtube open cheyyi", {"action": "goto", "site": "youtube"}),
    ("వాల్యూమ్ పెంచు", {"action": "media", "key": "volume_up"}),
    ("sound tagginchu", {"action": "media", "key": "volume_down"}),
    ("కిందకి స్క్రోల్ చెయ్యి", {"action": "scroll", "direction": "down", "amount": 5}),
    ("paiki scroll", {"action": "scroll", "direction": "up", "amount": 5}),
    ("హైదరాబాద్‌లో వాతావరణం ఎలా ఉంది", {"action": "weather", "place": "Hyderabad"}),
    ("weather cheppu", {"action": "weather", "place": None}),
    ("యూట్యూబ్‌లో తెలుగు పాటలు పెట్టు", {"action": "search", "site": "youtube", "query": "తెలుగు పాటలు"}),
    ("అరిజిత్ సింగ్ పాటలు పెట్టు", {"action": "search", "site": "youtube", "query": "అరిజిత్ సింగ్ పాటలు"}),
    ("ఆపు", {"action": "stop"}),
    ("laptop open cheyyi", {"action": "wake_screen"}),
    ("grid chupinchu", {"action": "grid", "show": True}),
    ("14 click cheyyi", {"action": "grid_click", "cell": 14, "button": "left", "count": 1}),
    ("వార్తలు చెప్పు", {"action": "news", "topic": None}),
])
def test_telugu_phrases(said, expected):
    cmd = to_command(said)
    assert cmd is not None, said
    assert cmd.model_dump() == expected


def test_unknown_telugu_goes_to_the_ai():
    assert to_command("నాకు ఏదో కావాలి") is None


@pytest.mark.parametrize("text, telugu", [("అమ్మకి కాల్", True), ("notepad open cheyyi", True),
                                          ("open notepad", False), ("volume up", False)])
def test_applies(text, telugu):
    assert applies(text) is telugu


def test_ai_answers_with_telugu_names_are_fixed():
    from agent.commands import parse_command

    cmd = fix_names(parse_command({"action": "whatsapp", "contact": "అమ్మకి", "kind": "voice_call"}))
    assert cmd.contact == "Amma"
    cmd = fix_names(parse_command({"action": "weather", "place": "హైదరాబాద్"}))
    assert cmd.place == "Hyderabad"


def test_to_english_for_the_ai():
    assert to_english("అమ్మకి కాల్ చెయ్యి") == "Amma ki call cheyyi"


# ---- through the assistant --------------------------------------------------------------------

def test_assistant_runs_telugu_without_the_ai():
    from agent.approvals import Approvals
    from agent.assistant import Assistant
    from agent.executor import Executor
    from tests.test_dispatch import FakeController

    class NoAI:
        def to_command(self, text):
            raise AssertionError("the AI should not be asked")

    ctl = FakeController()
    a = Assistant(Executor(ctl, Approvals(), launcher=lambda t: None, app_available=lambda t: True), planner=NoAI())
    assert a.handle_text("వాల్యూమ్ పెంచు")[0]["text"] == "Volume up."
    assert ("media", "volume_up") in ctl.calls


def test_which_one_can_be_answered_in_telugu():
    from agent.executor import Choice

    c = Choice(None, ["Sharmila Akka", "Yamini Akka", "Leela Akka"], expires=1e18)
    assert c.pick(to_english("రెండు")) == "Yamini Akka"
    assert c.pick(to_english("మొదటిది")) == "Sharmila Akka"
    assert c.pick(to_english("యామిని")) == "Yamini Akka"


# ---- v5 step 2: Telugu speech-to-text + EN / తె switch ------------------------

def test_lang_message_parses_and_rejects_other_languages():
    import json
    import pytest
    from server.protocol import BadMessage, Lang, parse_message

    m = parse_message(json.dumps({"t": "lang", "lang": "te"}))
    assert isinstance(m, Lang) and m.lang == "te"
    with pytest.raises(BadMessage):
        parse_message(json.dumps({"t": "lang", "lang": "fr"}))


class _Seg:
    def __init__(self, text):
        self.text = text


class _FakeWhisper:
    def __init__(self, name):
        self.name, self.calls = name, []

    def transcribe(self, source, **kw):
        self.calls.append(kw)
        return [_Seg(f" {self.name} ")], None


def test_telugu_uses_the_telugu_model_without_the_english_hint():
    import numpy as np
    from agent.stt import WhisperTranscriber

    t = WhisperTranscriber("base.en", telugu_model="te-model")
    t._models = {"base.en": _FakeWhisper("en"), "te-model": _FakeWhisper("te")}
    audio = np.zeros(16_000, dtype=np.float32)
    assert t.transcribe(audio, lang="te") == "te"
    kw = t._models["te-model"].calls[0]
    assert kw["language"] == "te" and kw["initial_prompt"] is None
    assert t.transcribe(audio) == "en"
    assert t._models["base.en"].calls[0]["initial_prompt"]  # English keeps its hint


def test_assistant_language_switch_reaches_the_transcriber():
    from agent.assistant import Assistant
    from tests.test_executor import FakeTranscriber, make

    fake = FakeTranscriber("స్క్రోల్ డౌన్")
    ex, ctl, _ = make()
    a = Assistant(ex, transcriber=fake)
    assert "తెలుగు" in a.set_lang("te")[0]["text"]
    msgs = a.handle_audio(b"x")
    assert fake.lang == "te"
    assert ("scroll", 0, -5) in ctl.calls          # Telugu-script "scroll down" ran
    a.set_lang("en")
    a.handle_audio(b"x")
    assert fake.lang == "en"
