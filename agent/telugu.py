"""Telugu and Tenglish commands, instantly and without the AI.

"అమ్మకి కాల్ చెయ్యి", "ammaki call cheyyi" -> call Amma on WhatsApp.

How it works:
1. normalise: every word becomes simple Latin ("tenglish"). Telugu script is
   transliterated (అమ్మ -> amma), common English loanwords written in Telugu
   become English (నోట్‌ప్యాడ్ -> notepad, కాల్ -> call), family words become the
   way they're saved in contacts (అమ్మ -> Amma), and case endings are split off
   (అమ్మకి -> Amma ki). The ORIGINAL word is kept next to each one, so a
   message or a YouTube search uses exactly what was said, in Telugu.
2. match a few patterns on the normalised words (call, message, open, volume,
   scroll, YouTube, weather, stop...). Anything else goes to the AI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from skills.websites import resolve as resolve_site

from .apps import find_app
from .commands import (
    ClickCmd, Command, GoToCmd, HotkeyCmd, GridClickCmd, GridCmd, MediaCmd, NewsCmd, OpenAppCmd, ScrollCmd,
    SearchCmd, SmartClickCmd, StopCmd, WakeScreenCmd, WeatherCmd, WhatsAppCmd,
)

TELUGU = re.compile(r"[ఀ-౿]")

# ---- Telugu script -> simple Latin ------------------------------------------------------------

_VOWELS = {"అ": "a", "ఆ": "aa", "ఇ": "i", "ఈ": "ee", "ఉ": "u", "ఊ": "oo", "ఋ": "ru", "ఎ": "e", "ఏ": "e",
           "ఐ": "ai", "ఒ": "o", "ఓ": "o", "ఔ": "au"}
_SIGNS = {"ా": "aa", "ి": "i", "ీ": "ee", "ు": "u", "ూ": "oo", "ృ": "ru", "ె": "e", "ే": "e", "ై": "ai",
          "ొ": "o", "ో": "o", "ౌ": "au"}
_CONSONANTS = {
    "క": "k", "ఖ": "kh", "గ": "g", "ఘ": "gh", "ఙ": "n", "చ": "ch", "ఛ": "chh", "జ": "j", "ఝ": "jh",
    "ఞ": "n", "ట": "t", "ఠ": "th", "డ": "d", "ఢ": "dh", "ణ": "n", "త": "t", "థ": "th", "ద": "d",
    "ధ": "dh", "న": "n", "ప": "p", "ఫ": "ph", "బ": "b", "భ": "bh", "మ": "m", "య": "y", "ర": "r",
    "ఱ": "r", "ల": "l", "ళ": "l", "వ": "v", "శ": "sh", "ష": "sh", "స": "s", "హ": "h",
}
_VIRAMA, _ANUSVARA, _VISARGA = "్", "ం", "ః"
_DIGITS = {chr(0x0C66 + i): str(i) for i in range(10)}          # ౦..౯


def transliterate(word: str) -> str:
    """'అమ్మ' -> 'amma', 'పెంచు' -> 'penchu', 'హైదరాబాద్' -> 'haidaraabaad'."""
    out: list[str] = []
    chars = [c for c in word if c not in "‌‍"]
    for i, ch in enumerate(chars):
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
            if nxt not in _SIGNS and nxt != _VIRAMA:
                out.append("a")                                   # inherent vowel
        elif ch in _SIGNS:
            out.append(_SIGNS[ch])
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch == _ANUSVARA:
            out.append("m" if _CONSONANTS.get(nxt, "") in ("p", "ph", "b", "bh", "m") else "n")
        elif ch == _VISARGA:
            out.append("h")
        elif ch in _DIGITS:
            out.append(_DIGITS[ch])
        elif ch == _VIRAMA:
            continue
        else:
            out.append(ch)
    return "".join(out)


# ---- words people say -------------------------------------------------------------------------

# English words written in Telugu script (and a few Telugu words) -> the English word.
LOANWORDS = {
    "నోట్‌ప్యాడ్": "notepad", "నోట్ప్యాడ్": "notepad", "నోట్ ప్యాడ్": "notepad",
    "క్యాలిక్యులేటర్": "calculator", "కాలిక్యులేటర్": "calculator", "కాల్క్యులేటర్": "calculator",
    "క్రోమ్": "chrome", "ఎడ్జ్": "edge", "వాట్సాప్": "whatsapp", "వాట్సప్": "whatsapp",
    "యూట్యూబ్": "youtube", "యుట్యూబ్": "youtube", "స్పాటిఫై": "spotify", "గూగుల్": "google",
    "గిట్‌హబ్": "github", "గిట్హబ్": "github", "చాట్‌జీపీటీ": "chatgpt", "ఫైల్స్": "files",
    "సెట్టింగ్స్": "settings", "పెయింట్": "paint", "కెమెరా": "camera", "వర్డ్": "word", "ఎక్సెల్": "excel",
    "కాల్": "call", "వీడియో": "video", "మెసేజ్": "message", "మెసెజ్": "message", "మెస్సేజ్": "message",
    "వాల్యూమ్": "volume", "సౌండ్": "volume", "శబ్దం": "volume", "స్క్రోల్": "scroll", "గ్రిడ్": "grid",
    "క్లిక్": "click", "ఓపెన్": "open", "మ్యూట్": "mute", "ప్లే": "play", "పాజ్": "pause",
    "పాట": "song", "పాటలు": "songs", "వార్తలు": "news", "న్యూస్": "news", "వాతావరణం": "weather",
    "వెదర్": "weather", "ల్యాప్‌టాప్": "laptop", "ల్యాప్టాప్": "laptop", "స్క్రీన్": "screen",
    "స్టాప్": "stop", "సెర్చ్": "search", "హాయ్": "hi", "హలో": "hello",
    # English words the Telugu speech model writes in Telugu script ("స్క్రోల్ డౌన్")
    "డౌన్": "down", "అప్": "up", "క్లోజ్": "close", "సెండ్": "send", "టైప్": "type", "ఎంటర్": "enter",
    "నెక్స్ట్": "next", "ప్రీవియస్": "previous", "బ్యాక్": "back", "ఫుల్": "full", "మినిమైజ్": "minimize",
    "మాక్సిమైజ్": "maximize", "విండో": "window", "ట్యాబ్": "tab", "న్యూ": "new", "పేజ్": "page", "పేజీ": "page",
    "బ్రౌజర్": "browser", "ఫైల్": "file", "ఫోల్డర్": "folder", "ఆఫీస్": "office", "షో": "show", "హైడ్": "hide",
    "జూమ్": "zoom", "ఇన్": "in", "అవుట్": "out", "ఆఫ్": "off", "ఆన్": "on", "రీడ్": "read", "ఎక్స్‌ప్లెయిన్": "explain",
    "స్లీప్": "sleep", "వేక్": "wake", "లాక్": "lock", "టైమ్": "time", "డేట్": "date", "క్రికెట్": "cricket",
    "స్కోర్": "score", "రిజల్ట్": "result", "వెబ్‌సైట్": "website", "లింక్": "link", "ఫస్ట్": "first",
    "సెకండ్": "second", "థర్డ్": "third", "లాస్ట్": "last", "అమెజాన్": "amazon", "ఇన్‌స్టాగ్రామ్": "instagram", "జీమెయిల్": "gmail",
}

_JOINERS = str.maketrans("", "", "‌‍")
LOANWORDS = {k.translate(_JOINERS): v for k, v in LOANWORDS.items()}

# Family words -> how they are usually saved in contacts.
FAMILY = {
    "amma": "Amma", "nanna": "Nanna", "naanna": "Nanna", "appa": "Appa", "akka": "Akka", "anna": "Anna",
    "chelli": "Chelli", "tammudu": "Thammudu", "thammudu": "Thammudu", "ammamma": "Ammamma",
    "naanamma": "Nanamma", "nanamma": "Nanamma", "taatayya": "Thatha", "tatayya": "Thatha", "thatha": "Thatha",
    "taata": "Thatha", "mamayya": "Mama", "maamayya": "Mama", "mama": "Mama", "atta": "Atta", "attayya": "Atta",
    "babai": "Babai", "baabaai": "Babai", "pinni": "Pinni", "peddamma": "Peddamma", "peddanaanna": "Peddananna",
}

# Telugu city names (transliterated) -> the English name the weather service knows.
CITIES = {
    "haidaraabaad": "Hyderabad", "hyderabad": "Hyderabad", "vijayavaada": "Vijayawada", "vijayawada": "Vijayawada",
    "vishaakhapatnam": "Visakhapatnam", "vishaakapatnam": "Visakhapatnam", "vaijaag": "Visakhapatnam",
    "vizag": "Visakhapatnam", "varangal": "Warangal", "tirupati": "Tirupati", "gunturu": "Guntur",
    "guntur": "Guntur", "nellooru": "Nellore", "nellore": "Nellore", "karnoolu": "Kurnool", "kurnool": "Kurnool",
    "kaakinaada": "Kakinada", "raajamahendravaram": "Rajahmundry", "raajamandri": "Rajahmundry",
    "khammam": "Khammam", "nijaamaabaad": "Nizamabad", "karimnagar": "Karimnagar", "kareemnagar": "Karimnagar",
    "anantapuram": "Anantapur", "kadapa": "Kadapa", "ongolu": "Ongole", "chennai": "Chennai", "bengalooru": "Bengaluru",
    "bengalooru ": "Bengaluru", "bangalore": "Bengaluru", "mumbai": "Mumbai", "dhilli": "Delhi", "dilli": "Delhi",
    "delhi": "Delhi",
}

# Endings stuck to a word: అమ్మకి -> అమ్మ + కి ("to Amma"), హైదరాబాద్‌లో -> + లో ("in").
_ENDINGS_TE = ("గారికి", "కి", "కు", "తో", "లో", "ని", "ను")
_ENDINGS_LATIN = ("gaariki", "ki", "ku", "tho", "lo")

# Words that show Latin text is Tenglish, not English.
TENGLISH_MARKERS = {
    "cheyyi", "cheyi", "chey", "cheyandi", "cheyyandi", "penchu", "tagginchu", "pampu", "pampandi", "pettu",
    "aapu", "aagu", "aapeyi", "vetuku", "teruvu", "teravu", "chupinchu", "choopinchu", "ani", "kindaki",
    "paiki", "kinda", "pai", "ekkuva", "takkuva", "cheppu", "ela", "undi", "kottu", "aapandi", "paatalu",
    "paata", "vaataavaranam", "vatavaranam", "okati", "rendu", "moodu",
}


@dataclass(frozen=True)
class Word:
    norm: str        # simple Latin / English form, lowercase
    orig: str        # exactly what was said


def _split_ending(word: str) -> tuple[str, str]:
    """('అమ్మకి') -> ('అమ్మ', 'కి'); ('ammaki') -> ('amma', 'ki')."""
    if TELUGU.search(word):
        for e in _ENDINGS_TE:
            if word.endswith(e) and len(word) > len(e) + 1:
                return word[: -len(e)], e
        return word, ""
    low = word.lower()
    for e in _ENDINGS_LATIN:
        stem = low[: -len(e)]
        if low.endswith(e) and (stem in FAMILY or stem in CITIES or len(stem) >= 4):
            return word[: -len(e)], e
    return word, ""


def _norm_one(word: str) -> str:
    if word in LOANWORDS:
        return LOANWORDS[word]
    if TELUGU.search(word):
        return transliterate(word).lower()
    return word.lower()


def normalise(text: str) -> list[Word]:
    """Turn what was said into Words (simple Latin + the original). Case endings become their own word."""
    words: list[Word] = []
    for raw in re.findall(r"[\wఀ-౿‌‍'-]+|[+\-*/=%]", text):
        raw = raw.translate(_JOINERS)                    # invisible joiners from Telugu keyboards
        if raw in LOANWORDS:
            words.append(Word(LOANWORDS[raw], raw))
            continue
        stem, ending = _split_ending(raw)
        stem_norm = _norm_one(stem)
        if ending and (stem_norm in FAMILY or stem_norm in CITIES or TELUGU.search(raw)
                       or stem_norm in ("kinda", "pai", "youtube", "whatsapp")):
            words.append(Word(stem_norm, stem))
            words.append(Word(_norm_one(ending) if TELUGU.search(ending) else ending.lower(), ending))
        else:
            words.append(Word(_norm_one(raw), raw))
    return words


def applies(text: str) -> bool:
    """Telugu script, or Latin text with Tenglish words in it."""
    if TELUGU.search(text):
        return True
    return bool(set(re.findall(r"[a-z]+", text.lower())) & TENGLISH_MARKERS)


# ---- patterns -------------------------------------------------------------------------------------

_DO = r"(?:cheyyi|cheyi|chey|cheyyandi|cheyandi|chesi|kottu|pettu)"
_TO = r"(?: (?:ki|ku|gaariki))?"


def _name(words: list[Word]) -> str:
    """Spoken name -> contact name: family words as saved ("Amma"), others transliterated, capitalised."""
    out = []
    for w in words:
        if w.norm in FAMILY:
            out.append(FAMILY[w.norm])
        elif TELUGU.search(w.orig):
            out.append(w.norm.capitalize())
        else:
            out.append(w.orig)
    return " ".join(out).strip()


def _place(words: list[Word]) -> str:
    key = " ".join(w.norm for w in words).strip()
    if key in CITIES:
        return CITIES[key]
    return " ".join(CITIES.get(w.norm, w.norm.capitalize() if TELUGU.search(w.orig) else w.orig) for w in words)


class _Match:
    """Regex over the normalised words, with a way back to the original words of each group."""

    def __init__(self, words: list[Word]) -> None:
        self.words = words
        self.text = " ".join(w.norm for w in words)
        self._starts = []
        pos = 0
        for w in words:
            self._starts.append(pos)
            pos += len(w.norm) + 1

    def match(self, pattern: str) -> re.Match[str] | None:
        return re.match(pattern + "$", self.text, re.I)

    def group_words(self, m: re.Match[str], name: str) -> list[Word]:
        if m.group(name) is None:
            return []
        start, end = m.span(name)
        return [w for w, s in zip(self.words, self._starts) if s >= start and s + len(w.norm) <= end]

    def orig(self, m: re.Match[str], name: str) -> str:
        return " ".join(w.orig for w in self.group_words(m, name)).strip()


_NUM = {"okati": 1, "rendu": 2, "moodu": 3, "naalugu": 4, "nalugu": 4, "aidu": 5, "aaru": 6, "edu": 7,
        "enimidi": 8, "tommidi": 9, "padi": 10}


# "rendo video play cheyyi", "మొదటి రిజల్ట్ ఓపెన్ చెయ్యి", "chivari video"
_ORDINALS = {
    "modati": 1, "modhati": 1, "modatidi": 1, "first": 1,
    "rendo": 2, "rendava": 2, "rendavadi": 2, "rendodi": 2, "second": 2,
    "moodo": 3, "mudo": 3, "moodava": 3, "moodavadi": 3, "third": 3,
    "naalugo": 4, "nalugo": 4, "naalugava": 4, "aido": 5, "ayido": 5, "aidava": 5, "aaro": 6,
    "chivari": -1, "chivaridi": -1, "last": -1,
}
_RESULT_KINDS = {"video": "video", "videos": "video", "song": "video", "songs": "video",
                 "result": "result", "website": "result", "site": "result", "link": "link"}


def to_command(text: str) -> Command | None:
    """A Command for a common Telugu/Tenglish phrase, or None (then the AI tries)."""
    words = normalise(text.strip(" .!?"))
    if not words:
        return None
    x = _Match(words)

    if x.match(r"(?:aapu|aagu|aapeyi|aapandi|stop)(?: " + _DO + ")?"):
        return StopCmd(action="stop")

    # tabs: "tab close cheyyi", "ee tab mooseyyi", "tab malli open cheyyi", "kotta tab"
    if x.match(r"(?:ee )?tab (?:close|mooseyyi|mooseyi|moosey|moosivey|moosiveyi|moosu)(?: " + _DO + ")?"):
        return HotkeyCmd(action="hotkey", combo="close_tab")
    if x.match(r"(?:(?:aa|close chesina) )?tab (?:mallee|malli) (?:open|teru|terichi)(?: " + _DO + ")?"):
        return HotkeyCmd(action="hotkey", combo="reopen_tab")
    if x.match(r"(?:kotta|new) tab(?: (?:open|teru))?(?: " + _DO + ")?"):
        return HotkeyCmd(action="hotkey", combo="new_tab")

    # the nth result or video on screen
    if m := x.match(r"(?P<ord>" + "|".join(_ORDINALS) + r") (?P<kind>" + "|".join(_RESULT_KINDS) + r")"
                    r"(?: (?:play|open|click|pettu|choodu|chudu|chupinchu|select))?(?: " + _DO + ")?"):
        from .commands import OpenResultCmd

        return OpenResultCmd(action="open_result", n=_ORDINALS[m.group("ord")], kind=_RESULT_KINDS[m.group("kind")])

    # calls: "amma ki call cheyyi", "amma ki video call cheyyi", "call amma ki"
    if m := x.match(r"(?P<who>.+?)" + _TO + r" (?P<video>video )?call(?: " + _DO + ")?"):
        who = _name(x.group_words(m, "who"))
        if who and who.lower() not in ("video",):
            return WhatsAppCmd(action="whatsapp", contact=who[:60],
                               kind="video_call" if m.group("video") else "voice_call")

    # messages: "akka ki hi ani message pampu", "akka ki message pampu hi ani"
    if m := x.match(r"(?P<who>.+?) (?:ki|ku|gaariki) (?P<text>.+?) ani(?: whatsapp)?(?: message| msg)?(?: "
                    r"(?:pampu|pampandi|cheyyi|chey|pettu|cheyandi))?"):
        who, msg = _name(x.group_words(m, "who")), x.orig(m, "text")
        if who and msg:
            return WhatsAppCmd(action="whatsapp", contact=who[:60], kind="message", text=msg[:500])

    # volume, media
    if x.match(r"(?:volume|sound) (?:penchu|ekkuva|ekkuva " + _DO + r"|up)(?: " + _DO + ")?"):
        return MediaCmd(action="media", key="volume_up")
    if x.match(r"(?:volume|sound) (?:tagginchu|takkuva|takkuva " + _DO + r"|down)(?: " + _DO + ")?"):
        return MediaCmd(action="media", key="volume_down")
    if x.match(r"(?:mute|volume aapu|sound aapu)(?: " + _DO + ")?"):
        return MediaCmd(action="media", key="mute")
    if x.match(r"(?:play|pause|play pause)(?: " + _DO + ")?"):
        return MediaCmd(action="media", key="play_pause")

    # scrolling
    if x.match(r"(?:kinda ki|kindaki|kindiki|kinda) scroll(?: " + _DO + ")?|scroll (?:kinda ki|kindaki)(?: " + _DO + ")?"):
        return ScrollCmd(action="scroll", direction="down", amount=5)
    if x.match(r"(?:pai ki|paiki|paina) scroll(?: " + _DO + ")?|scroll (?:pai ki|paiki)(?: " + _DO + ")?"):
        return ScrollCmd(action="scroll", direction="up", amount=5)

    # wake the laptop / screen
    if x.match(r"(?:laptop|screen|computer) (?:open|teruvu|teravu|on)(?: " + _DO + ")?"):
        return WakeScreenCmd(action="wake_screen")

    # grid
    if x.match(r"grid (?:chupinchu|choopinchu|pettu|open)(?: " + _DO + ")?"):
        return GridCmd(action="grid", show=True)
    if m := x.match(r"(?P<n>\d+|" + "|".join(_NUM) + r")(?: meeda| pai)? click(?: " + _DO + ")?"):
        n = m.group("n")
        cell = int(n) if n.isdigit() else _NUM[n.lower()]
        return GridClickCmd(action="grid_click", cell=cell)
    if m := x.match(r"(?P<what>.+?)(?: meeda| pai)? click(?: " + _DO + ")?"):
        return SmartClickCmd(action="click_on", target=x.orig(m, "what")[:80])

    # YouTube: "youtube lo telugu songs pettu", "<song> paata pettu"
    if m := x.match(r"youtube(?: lo)? (?P<q>.+?) (?:vetuku|pettu|chupinchu|play " + _DO + r"|play|search " + _DO + ")"):
        return SearchCmd(action="search", site="youtube", query=x.orig(m, "q")[:200])
    if m := x.match(r"(?P<q>.+?) youtube(?: lo)? (?:vetuku|pettu|chupinchu|play " + _DO + r"|play)"):
        return SearchCmd(action="search", site="youtube", query=x.orig(m, "q")[:200])
    if m := x.match(r"(?P<q>.+? (?:song|songs|paata|paatalu)) (?:pettu|play " + _DO + r"|play|vinipinchu)"):
        return SearchCmd(action="search", site="youtube", query=x.orig(m, "q")[:200])
    if m := x.match(r"(?P<q>.+?) (?:google lo |)(?:vetuku|search " + _DO + ")"):
        return SearchCmd(action="search", site="google", query=x.orig(m, "q")[:200])

    # weather: "hyderabad lo weather ela undi", "weather cheppu"
    if m := x.match(r"(?:(?P<place>.+?)(?: lo)? )?weather(?: (?:ela|elaa|undi|unnadi|entha|cheppu|chepandi|enti))*"):
        place = _place(x.group_words(m, "place")) if m.group("place") else None
        return WeatherCmd(action="weather", place=place[:80] if place else None)

    # news
    if x.match(r"(?:news|varthalu|vaartalu)(?: (?:cheppu|chepandi|chadivi vinipinchu))?"):
        return NewsCmd(action="news", topic=None)

    # opening apps and websites: "notepad open cheyyi", "youtube teruvu"
    if m := x.match(r"(?P<what>.+?) (?:open|teruvu|teravu)(?: " + _DO + ")?"):
        what = " ".join(w.norm for w in x.group_words(m, "what"))
        if app := find_app(what):
            return OpenAppCmd(action="open_app", app=app)
        if resolve_site(what):
            return GoToCmd(action="goto", site=what[:200])

    if x.match(r"click(?: " + _DO + ")?"):
        return ClickCmd(action="click")
    return None


def to_english(text: str) -> str:
    """Normalised text for the AI ("ammaki hi ani message pampu" style), names already English."""
    return " ".join(FAMILY.get(w.norm, w.norm) for w in normalise(text))


def fix_names(cmd: Command) -> Command:
    """The AI sometimes keeps names and places in Telugu script: make them English
    so WhatsApp search and the weather service understand them."""
    from .commands import AirQualityCmd

    if isinstance(cmd, WhatsAppCmd) and TELUGU.search(cmd.contact):
        words = [w for w in normalise(cmd.contact) if w.norm not in ("ki", "ku", "gaariki", "tho")]
        return cmd.model_copy(update={"contact": _name(words)[:60] or cmd.contact})
    if isinstance(cmd, (WeatherCmd, AirQualityCmd)) and cmd.place and TELUGU.search(cmd.place):
        words = [w for w in normalise(cmd.place) if w.norm != "lo"]
        return cmd.model_copy(update={"place": _place(words)[:80]})
    return cmd


# ---- Telugu replies (v5) ------------------------------------------------------------------------
# The executor answers in English; these turn the replies heard most into Telugu.
# Anything not listed stays English (the phone speaks it with the English voice).

_WEATHER = {
    "clear sky": "ఆకాశం నిర్మలంగా ఉంది", "mainly clear": "దాదాపు నిర్మలంగా ఉంది",
    "partly cloudy": "కొంచెం మబ్బుగా ఉంది", "cloudy": "మబ్బుగా ఉంది", "foggy": "పొగమంచు ఉంది",
    "light drizzle": "చిన్న చినుకులు పడుతున్నాయి", "drizzle": "చినుకులు పడుతున్నాయి",
    "light rain": "చిన్న వర్షం పడుతోంది", "rain": "వర్షం పడుతోంది", "heavy rain": "భారీ వర్షం పడుతోంది",
    "light showers": "చిరుజల్లులు పడుతున్నాయి", "showers": "జల్లులు పడుతున్నాయి",
    "heavy showers": "భారీ జల్లులు పడుతున్నాయి", "thunderstorms": "ఉరుములతో వర్షం",
}

_AQI = {"good": "బాగుంది", "moderate": "పర్వాలేదు",
        "unhealthy for sensitive people": "ఆస్తమా ఉన్నవాళ్లకు మంచిది కాదు",
        "unhealthy": "బాగాలేదు, బయట మాస్క్ వేసుకోండి", "very unhealthy": "చాలా బాగాలేదు, లోపలే ఉండండి",
        "hazardous": "ప్రమాదకరంగా ఉంది, లోపలే ఉండండి"}

_SCROLL = {"down": "కిందకి", "up": "పైకి", "left": "ఎడమకి", "right": "కుడికి"}


def _weather_te(m: re.Match) -> str:
    sky = _WEATHER.get(m["sky"], m["sky"])
    out = f"{m['place']}లో ఇప్పుడు {m['temp']}°C, {sky}."
    if m["lo"]:
        out += f" ఈరోజు {m['lo']} నుంచి {m['hi']}°C."
    if m["rain"]:
        out += f" వర్షం పడే అవకాశం {m['rain']}%."
    return out


# (English reply pattern, Telugu reply or function). First match wins.
_REPLIES: list[tuple[str, Any]] = [
    (r"Closed the tab\.", "ట్యాబ్ మూసేశాను."),
    (r"This tab has unsaved changes.*", "ఈ ట్యాబ్‌లో సేవ్ చేయని మార్పులు ఉన్నాయి. సేవ్ చేయాలా అని అడుగుతోంది, ల్యాప్‌టాప్‌లో ఎంచుకోండి. లేదా ప్రెస్ ఎస్కేప్ అని చెప్పండి."),
    (r"Reopened the last closed tab\.", "మూసిన ట్యాబ్ మళ్ళీ తెరిచాను."),
    (r"New tab\.", "కొత్త ట్యాబ్ తెరిచాను."),
    (r"This window has no tabs I can close\..*", "ఈ విండోలో ట్యాబ్స్ లేవు. క్లోజ్ విండో అని చెప్పండి."),
    (r"Searching (?P<site>.+?) for (?P<x>.+) in a new tab\.", "కొత్త ట్యాబ్‌లో {site}లో {x} వెతుకుతున్నాను."),
    (r"Opening (?P<x>.+) in a new tab\.", "కొత్త ట్యాబ్‌లో {x} తెరుస్తున్నాను."),    (r"Opening the last (?P<k>video|result): (?P<x>.+)\.",
     lambda m: f"చివరి {'వీడియో' if m['k'] == 'video' else 'రిజల్ట్'} తెరుస్తున్నాను: {m['x']}."),
    (r"Opening the (?P<n>\d+)\w\w (?P<k>video|result): (?P<x>.+)\.",
     lambda m: f"{m['n']}వ {'వీడియో' if m['k'] == 'video' else 'రిజల్ట్'} తెరుస్తున్నాను: {m['x']}."),
    (r"Opening (?P<x>.+?)\.(?: .*)?", "{x} తెరుస్తున్నాను."),
    (r"The (?P<x>.+?) app isn't installed, so I opened .+ on the web\.", "{x} యాప్ లేదు, వెబ్‌లో తెరిచాను."),
    (r"Volume up\.", "సౌండ్ పెంచాను."),
    (r"Volume down\.", "సౌండ్ తగ్గించాను."),
    (r"Toggled mute\.", "మ్యూట్ మార్చాను."),
    (r"Play / pause\.", "ప్లే / పాజ్ చేశాను."),
    (r"Next track\.", "తర్వాతి పాట."),
    (r"Previous track\.", "ముందు పాట."),
    (r"Scrolled (?P<d>\w+)\.", lambda m: f"{_SCROLL.get(m['d'], m['d'])} స్క్రోల్ చేశాను."),
    (r"Typed it\.", "టైప్ చేశాను."),
    (r"Double-clicked\.", "డబుల్ క్లిక్ చేశాను."),
    (r"Clicked (?P<x>.+?)\.", "{x} క్లిక్ చేశాను."),
    (r"Grid on\..*", "గ్రిడ్ వచ్చింది. క్లిక్ అని ఒక నంబర్ చెప్పండి."),
    (r"Grid off\.", "గ్రిడ్ తీసేశాను."),
    (r"Message to (?P<x>.+) is ready\. Approve on your phone to send it\.",
     "{x}కి మెసేజ్ రెడీ. పంపడానికి ఫోన్‌లో Approve నొక్కండి."),
    (r"Approve on your phone to call (?P<x>.+)\.", "{x}కి కాల్ చేయడానికి ఫోన్‌లో Approve నొక్కండి."),
    (r"Approve on your phone to close the window\.", "విండో మూయడానికి ఫోన్‌లో Approve నొక్కండి."),
    (r"Approve on your phone to (?P<x>.+)\.", "ఫోన్‌లో Approve నొక్కండి."),
    (r"Sent to (?P<x>.+)\.", "{x}కి పంపాను."),
    (r"Calling (?P<x>.+) \((?:voice|video)\)\.", "{x}కి కాల్ చేస్తున్నాను."),
    (r"Opened your chat with (?P<x>.+)\.", "{x} చాట్ తెరిచాను."),
    (r"What should I say to (?P<x>.+)\?", "{x}కి ఏం పంపాలి?"),
    (r"Which (?P<x>.+?)\? (?P<list>.+)\. Say the name or the number\.",
     "ఏ {x}? {list}. పేరు లేదా నంబర్ చెప్పండి."),
    (r"I couldn't find (?P<x>.+) in WhatsApp\.", "వాట్సాప్‌లో {x} కనిపించలేదు."),
    (r"I couldn't find (?P<x>.+?)\. Did you mean (?P<list>.+)\? Say the number or the name\.",
     "{x} కనిపించలేదు. మీ ఉద్దేశం {list}? నంబర్ లేదా పేరు చెప్పండి."),
    (r"I couldn't find (?P<x>.+) on the screen\..*", "స్క్రీన్ మీద {x} కనిపించలేదు. షో గ్రిడ్ అని చెప్పండి."),
    (r"WhatsApp isn't open\..*", "వాట్సాప్ తెరిచి లేదు. ముందు వాట్సాప్ తెరవండి."),
    (r"Closed the window\.", "విండో మూసేశాను."),
    (r"Cancelled\.|OK, cancelled\.", "సరే, రద్దు చేశాను."),
    (r"That request expired\..*", "ఆ రిక్వెస్ట్ టైమ్ అయిపోయింది. మళ్ళీ అడగండి."),
    (r"Stopped\.", "ఆపేశాను."),
    (r"Screen is on\. It's locked.*", "స్క్రీన్ ఆన్ అయ్యింది. లాక్ తీయండి."),
    (r"Screen is on\.", "స్క్రీన్ ఆన్ అయ్యింది."),
    (r"Searching (?P<site>.+?) for (?P<x>.+)\.", "{site}లో {x} వెతుకుతున్నాను."),
    (r"I can only see (?P<n>\d+) (?P<k>video|result)s? on the screen\..*",
     lambda m: f"స్క్రీన్ మీద {m['n']} {'వీడియోలు' if m['k'] == 'video' else 'రిజల్ట్స్'} మాత్రమే ఉన్నాయి. కిందకి స్క్రోల్ చేసి మళ్ళీ చెప్పండి."),
    (r"I can't see any (?P<k>video|result)s on the screen\..*",
     lambda m: f"స్క్రీన్ మీద {'వీడియోలు' if m['k'] == 'video' else 'రిజల్ట్స్'} కనిపించట్లేదు. షో గ్రిడ్ అని చెప్పండి."),
    (r"(?P<place>[^:]+): (?P<temp>-?\d+)°C and (?P<sky>[a-z ]+?)(?:, feels like -?\d+°C)?\."
     r"(?: Today (?P<lo>-?\d+) to (?P<hi>-?\d+)°C)?(?:, (?P<rain>\d+)% chance of rain)?.*", _weather_te),
    (r"Air quality in (?P<place>.+?) is (?P<q>[a-z ]+): AQI (?P<n>\d+).*",
     lambda m: f"{m['place']}లో గాలి నాణ్యత {_AQI.get(m['q'], m['q'])}: AQI {m['n']}."),
    # Approve card questions
    (r'Send to (?P<x>.+) on WhatsApp: "(?P<m>.*)"\?', '{x}కి వాట్సాప్‌లో పంపాలా: "{m}"?'),
    (r"Group (?P<k>voice|video) call (?P<x>.+) on WhatsApp\? .*",
     lambda m: f"{m['x']} గ్రూప్‌కి {'వీడియో ' if m['k'] == 'video' else ''}కాల్ చేయాలా? (గ్రూప్‌లో అందరికీ రింగ్ అవుతుంది)"),
    (r"(?P<k>Voice|Video) call (?P<x>.+) on WhatsApp\?",
     lambda m: f"{m['x']}కి వాట్సాప్ {'వీడియో ' if m['k'] == 'Video' else ''}కాల్ చేయాలా?"),
    (r"Close the active window\?", "ఇప్పుడున్న విండో మూసేయాలా?"),
    (r"Delete all of PocketPilot's history\?", "PocketPilot హిస్టరీ మొత్తం తీసేయాలా?"),
    (r'Click "(?P<x>.+)"\?', '"{x}" క్లిక్ చేయాలా?'),
    (r"Sorry, I didn't understand\..*", "క్షమించండి, అర్థం కాలేదు. ఉదా: నోట్‌ప్యాడ్ ఓపెన్ చెయ్యి, వాతావరణం."),
    (r"I didn't catch that\..*", "వినపడలేదు. మళ్ళీ చెప్పండి."),
    (r"Still working on the last one…", "ఇంకా ముందు పని చేస్తున్నాను…"),
    (r"Sorry, that didn't work\.", "క్షమించండి, అది పని చేయలేదు."),
]
_REPLIES_RE = [(re.compile(p, re.S), r) for p, r in _REPLIES]


def reply(text: str) -> str:
    """An English reply -> Telugu, if it is one we know; otherwise unchanged."""
    for rx, out in _REPLIES_RE:
        m = rx.fullmatch(text.strip())
        if m:
            said = out(m) if callable(out) else out.format(**{k: v or "" for k, v in m.groupdict().items()})
            return _SPACE_BEFORE_ENDING.sub(r"\1 \2", said)
    return text


# "Amma ❤️కి" reads badly: put a space between an emoji/symbol and a Telugu ending.
_SPACE_BEFORE_ENDING = re.compile(r"([^\w\s\u0c00-\u0c7f\u200c\u200d.)\"'])(\u0c15\u0c3f|\u0c32\u0c4b)")
