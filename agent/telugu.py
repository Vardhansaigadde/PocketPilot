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

from skills.websites import resolve as resolve_site

from .apps import find_app
from .commands import (
    ClickCmd, Command, GoToCmd, GridClickCmd, GridCmd, MediaCmd, NewsCmd, OpenAppCmd, ScrollCmd,
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
    "స్కోర్": "score", "అమెజాన్": "amazon", "ఇన్‌స్టాగ్రామ్": "instagram", "జీమెయిల్": "gmail",
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


def to_command(text: str) -> Command | None:
    """A Command for a common Telugu/Tenglish phrase, or None (then the AI tries)."""
    words = normalise(text.strip(" .!?"))
    if not words:
        return None
    x = _Match(words)

    if x.match(r"(?:aapu|aagu|aapeyi|aapandi|stop)(?: " + _DO + ")?"):
        return StopCmd(action="stop")

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
