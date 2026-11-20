"""Fast path: common phrases mapped straight to commands, with no AI.

This is instant and works offline. `fast_path()` returns None when it doesn't
recognise the phrase; the caller then asks the AI model instead.
"""

from __future__ import annotations

import re

from skills.currency import code as currency_code
from skills.websites import resolve as resolve_site

from .apps import app_list_text, find_app
from .commands import (
    GRID_CELLS, CricketCmd, CurrencyCmd, DefineCmd, NewsCmd, UnknownCmd, AirQualityCmd, ClickCmd, CloseWindowCmd, Command, GoToCmd, GridClickCmd, GridCmd,
    ForgetCmd, GridZoomCmd, HotkeyCmd, KeyCmd, MemoryCmd, MediaCmd, OpenAppCmd, ScreenCmd, ScrollCmd, SearchCmd, SmartClickCmd, StopCmd,
    TypeCmd, WhatsAppCmd,
    WeatherCmd, WikiCmd,
)

_FILLER_START = re.compile(
    r"^(?:(?:hey |ok |okay )?(?:jarvis|pilot|pocket ?pilot)[,!.]?\s+|please\s+|can you\s+|could you\s+"
    r"|would you\s+|will you\s+|i want to\s+|i want you to\s+|just\s+)+",
    re.I,
)
_FILLER_END = re.compile(r"(?:\s+please|\s+for me|\s+now)+$", re.I)

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "to": 2, "too": 2, "for": 4, "won": 1,
}

_KEY_NAMES = {
    "enter": "enter", "return": "enter", "escape": "esc", "esc": "esc", "tab": "tab",
    "backspace": "backspace", "back space": "backspace", "delete": "delete", "space": "space",
    "spacebar": "space", "space bar": "space", "up": "up", "down": "down", "left": "left",
    "right": "right", "home": "home", "end": "end", "page up": "page_up",
    "page down": "page_down", "up arrow": "up", "down arrow": "down", "left arrow": "left",
    "right arrow": "right",
}

_SIMPLE: dict[str, Command] = {}

# Tools that can run commands or change the system are never opened, whatever the AI says.
_BLOCKED_APPS = re.compile(
    r"^(?:the |a )?(?:command prompt|cmd|cmd\.exe|command line|terminal|windows terminal|powershell|"
    r"power shell|bash|shell|registry|registry editor|regedit|task manager|control panel|run box|run dialog)"
    r"(?: app| window)?$",
    re.I,
)


def _simple(phrases: str, cmd: Command) -> None:
    for p in phrases.split("|"):
        _SIMPLE[p] = cmd


_simple("stop|cancel|never mind|nevermind|stop it|abort|stop everything", StopCmd(action="stop"))
_simple("click|left click|click it|click that|tap", ClickCmd(action="click"))
_simple("double click|double tap", ClickCmd(action="click", count=2))
_simple("right click", ClickCmd(action="click", button="right"))
_simple("middle click", ClickCmd(action="click", button="middle"))
_simple("volume up|louder|turn it up|turn up the volume|increase volume|increase the volume"
        "|turn the volume up|turn volume up|raise the volume|make it louder",
        MediaCmd(action="media", key="volume_up"))
_simple("volume down|quieter|softer|turn it down|turn down the volume|decrease volume"
        "|turn the volume down|turn volume down|make it quieter"
        "|decrease the volume|lower the volume", MediaCmd(action="media", key="volume_down"))
_simple("mute|unmute|mute the volume|mute sound|silence", MediaCmd(action="media", key="mute"))
_simple("play|pause|resume|play pause|play or pause|pause the music|play the music|play it|play that"
        "|pause the video|play the video|pause music|play music",
        MediaCmd(action="media", key="play_pause"))
_simple("next|next song|next track|skip|skip song|next video", MediaCmd(action="media", key="next"))
_simple("previous|previous song|previous track|last song|go back a song",
        MediaCmd(action="media", key="prev"))
_simple("switch app|switch apps|switch window|switch windows|next app|next window|alt tab",
        HotkeyCmd(action="hotkey", combo="app_next"))
_simple("previous app|previous window|last app", HotkeyCmd(action="hotkey", combo="app_prev"))
_simple("show desktop|go to desktop|minimize everything|minimise everything",
        HotkeyCmd(action="hotkey", combo="show_desktop"))
_simple("show all windows|task view|all windows", HotkeyCmd(action="hotkey", combo="task_view"))
_simple("copy|copy that|copy this", HotkeyCmd(action="hotkey", combo="copy"))
_simple("paste|paste it|paste that", HotkeyCmd(action="hotkey", combo="paste"))
_simple("cut|cut that", HotkeyCmd(action="hotkey", combo="cut"))
_simple("undo|undo that", HotkeyCmd(action="hotkey", combo="undo"))
_simple("select all|select everything", HotkeyCmd(action="hotkey", combo="select_all"))
_simple("close window|close the window|close this window|close this|close it|close app"
        "|close the app|close this app", CloseWindowCmd(action="close_window"))
_simple("show grid|show the grid|grid|grid on|show numbers", GridCmd(action="grid", show=True))
_simple("hide grid|hide the grid|grid off|close grid|close the grid|hide numbers",
        GridCmd(action="grid", show=False))
_simple("new tab|open a new tab|open new tab|open a tab", HotkeyCmd(action="hotkey", combo="new_tab"))
_simple("next tab|switch tab|switch tabs|go to the next tab", HotkeyCmd(action="hotkey", combo="next_tab"))
_simple("previous tab|last tab|go to the previous tab", HotkeyCmd(action="hotkey", combo="prev_tab"))
_simple("go back|back|previous page|go to the previous page|go back a page",
        HotkeyCmd(action="hotkey", combo="back"))
_simple("go forward|forward|next page|go forward a page", HotkeyCmd(action="hotkey", combo="forward"))
_simple("refresh|reload|refresh the page|reload the page|refresh page",
        HotkeyCmd(action="hotkey", combo="refresh"))
_simple("address bar|go to the address bar|click the address bar|go to address bar|search bar"
        "|go to the search bar", HotkeyCmd(action="hotkey", combo="address_bar"))
_simple("what's on my screen|whats on my screen|what is on my screen|what's on the screen"
        "|what is on the screen|what am i looking at|describe the screen|describe my screen"
        "|what do you see|look at my screen|look at the screen|see my screen|see the screen"
        "|see what i'm doing|see what im doing|what am i doing|what am i doing right now",
        ScreenCmd(action="screen", mode="describe"))
_simple("summarize this page|summarise this page|summarize the page|summarise the page|summarize this"
        "|summarise this|summarize the screen|summarise the screen|summarize this article"
        "|give me a summary|what is this page about|what's this page about|tldr",
        ScreenCmd(action="screen", mode="summarize"))
_simple("explain this error|explain the error|what does this error mean|what's this error|what is this error"
        "|why is this failing|fix this error|help me with this error", ScreenCmd(action="screen", mode="explain_error"))
_simple("read the screen|read this|read this page|read it to me|read the page|read it out|read it aloud",
        ScreenCmd(action="screen", mode="read"))
_simple("clear my history|delete my history|clear history|forget my history|forget everything"
        "|erase my history", ForgetCmd(action="forget_history"))
_simple("cricket|cricket score|cricket scores|live score|live scores|live cricket score|what's the score"
        "|whats the score|what is the score|score of the match|match score", CricketCmd(action="cricket"))
_simple("weather|what's the weather|whats the weather|what is the weather|how's the weather"
        "|hows the weather|weather today|is it going to rain|will it rain|sunset"
        "|when is sunset|what time is sunset", WeatherCmd(action="weather"))
_simple("air quality|aqi|what's the air quality|what is the air quality|pollution"
        "|how's the air|hows the air", AirQualityCmd(action="air_quality"))


def clean(text: str) -> str:
    """Trim filler words and punctuation that speech-to-text adds."""
    t = text.strip().strip(" .!?,;:\"'").strip()
    t = _FILLER_START.sub("", t)
    t = _FILLER_END.sub("", t)
    return t.strip(" .!?,;:").strip()


def _number(word: str) -> int | None:
    word = word.strip().lower().replace("-", " ")
    if word.isdigit():
        return int(word)
    parts = word.split()
    if parts and all(p in _NUMBER_WORDS for p in parts) and len(parts) <= 2:
        return sum(_NUMBER_WORDS[p] for p in parts)
    return None


def _scroll(m: re.Match[str]) -> Command:
    amount = 5
    how = (m.group("how") or m.group("how2") or "").strip()
    if how in ("a lot", "a bit more", "more", "way"):
        amount = 12
    elif how in ("a little", "a bit", "slightly", "a little bit"):
        amount = 2
    if m.group("n"):
        n = _number(m.group("n"))
        if n:
            amount = max(1, min(20, n))
    return ScrollCmd(action="scroll", direction=m.group("dir").lower(), amount=amount)


_SCROLL = re.compile(
    r"^scroll (?P<how>a lot |a little bit |a little |a bit |slightly |way )?(?P<dir>up|down)"
    r"(?: (?P<how2>a lot|a little|a bit|more))?(?: (?P<n>[\w-]+)(?: times| lines)?)?$",
    re.I,
)
_GRID_CLICK = re.compile(
    r"^(?P<kind>double click|double tap|right click|click|tap)(?: on)?(?: number| box| cell)? "
    r"(?P<n>[\w-]+(?: [\w-]+)?)$",
    re.I,
)
# Only "type ..." types text. "write ..." is left to the AI, because people say
# "I want to write some code" or "write an email" and mean something else.
# "click the Sign in button", "right click on Recycle Bin", "press the Submit button"
_CLICK_ON = re.compile(
    r"^(?P<kind>double click|double tap|right click|click|tap|press|select|hit|choose)(?: on)? "
    r"(?P<target>.+?)(?: button| link| tab| icon| option)?$",
    re.I,
)
_ZOOM = re.compile(r"^(?:zoom|zoom in|zoom into|zoom in on|zoom on|closer|closer to)(?: box| number| cell)? "
                   r"(?P<n>[\w-]+(?: [\w-]+)?)$", re.I)
# "what was I working on yesterday", "what did I do today", "show my history"
_MEMORY = re.compile(
    r"^(?:what (?:was i (?:working on|doing)|did i do|have i done|did i work on)|show (?:me )?my "
    r"(?:history|activity)|my history)(?: (?P<p>today|yesterday|this week|in the last hour|last hour|"
    r"earlier today|so far))?$",
    re.I,
)
_WA_WORD = r"(?:whatsapp|whats ?app|what'?s ?app|what sapp|wats ?app|watsapp|whatsap)"
_ON_WA = r"(?:\s+(?:(?:on|in|over|through|via) )?" + _WA_WORD + ")?"
# "call amma", "video call amma on whatsapp", "whatsapp call kidduuu"
_WA_CALL = re.compile(
    r"^(?:(?P<v1>video )?call|ring|phone|make a (?P<v2>video )?call to|whatsapp (?P<v3>video )?call(?: to)?)"
    r" (?P<who>.+?)" + _ON_WA + r"(?: (?P<v4>on video|with video))?$",
    re.I,
)
# "message amma that I'll be late", "tell kidduuu on whatsapp that ...", "reply to amma saying ..."
_WA_MSG = re.compile(
    r"^(?:message|text|whatsapp|send (?:a )?(?:whatsapp )?message to|reply to|tell)"
    r" (?P<who>.+?)" + _ON_WA + r"(?: that| saying| to say|:|,) (?P<text>.+)$",
    re.I | re.S,
)
# "send amma a message saying I'm coming"
_WA_SEND = re.compile(r"^send (?P<who>.+?) a (?:whatsapp )?message(?: that| saying|:) (?P<text>.+)$", re.I | re.S)
# "message kiddu hi" (no "that"): the first word is the name
_WA_MSG_SHORT = re.compile(r"^(?:message|msg|text|whatsapp) (?:to )?(?P<who>[\w'-]+)" + _ON_WA + r"[ ,:.]+(?P<text>.+)$",
                           re.I | re.S)
# "send hi to kidduuu", "send good night to amma on whatsapp"
_WA_SEND_TO = re.compile(r"^send (?P<text>.+?) to (?P<who>[\w'-]+(?: [\w'-]+)?)" + _ON_WA + "$", re.I | re.S)
_WA_JUST_NAME = re.compile(r"^(?:message|msg|text) (?P<who>[\w'-]+)" + _ON_WA + "$", re.I)
_WA_OPEN = re.compile(r"^(?:open|show|go to) (?:my |the )?(?:whatsapp )?chat (?:with|of) (?P<who>.+?)" + _ON_WA + "$",
                      re.I)
# "convert 100 dollars to rupees", "how much is 50 euros in rupees", "dollar to rupee", "dollar rate"
_CUR_CONVERT = re.compile(
    r"^(?:convert |change |how much is |what is |what's |whats )?(?P<amt>\d[\d,]*(?:\.\d+)?|a|an|one)?\s*"
    r"(?P<from>[a-z$. ]+?)\s+(?:to|in|into)\s+(?P<to>[a-z. ]+?)(?: today| now| right now)?$",
    re.I,
)
_CUR_RATE = re.compile(
    r"^(?:what(?:'s| is) the |whats the |today'?s )?(?P<from>[a-z. ]+?)(?: to (?P<to>[a-z. ]+?))?"
    r" (?:rate|exchange rate|price|value)(?: today| now)?$",
    re.I,
)
_DEFINE = re.compile(r"^(?:define|definition of|meaning of|what is the meaning of|what's the meaning of"
                     r"|whats the meaning of|dictionary meaning of|dictionary) (?P<word>[a-z][a-z' -]{0,38})$", re.I)
_MEANS = re.compile(r"^what does (?P<word>[a-z][a-z'-]{0,38}) mean$", re.I)
_NEWS = re.compile(r"^(?:news|headlines|latest news|today'?s news|top news|top headlines|what'?s the news"
                   r"|what is the news|tell me the news|any news)(?: (?:about|on|for|from) (?P<topic>.+))?$", re.I)
_TYPE = re.compile(r"^(?:type|type in|type out|enter text)[ :,]+(?P<text>.+)$", re.I | re.S)
_PRESS = re.compile(r"^(?:press|hit|push)(?: the)? (?P<key>.+?)(?: key| button)?$", re.I)
_OPEN = re.compile(r"^(?:open|launch|start|run|bring up|go to|visit|navigate to|take me to"
                   r"|browse to|show me|let me see) (?P<app>.+)$", re.I)
_WEATHER = re.compile(
    r"^(?:what(?:'s| is) the |how(?:'s| is) the )?(?:weather|forecast|temperature|sunset)"
    r"(?: like)?(?: today| tomorrow)? (?:in|at|for) (?P<place>.+?)(?: today| tomorrow)?$",
    re.I,
)
_AIR = re.compile(
    r"^(?:what(?:'s| is) the |how(?:'s| is) the )?(?:air quality|aqi|pollution|air)"
    r"(?: like)? (?:in|at|for) (?P<place>.+)$",
    re.I,
)
_SEARCH_ON = re.compile(
    r"^(?:search|find|look up|look for|play|watch)(?: for)? (?P<q>.+?) on "
    r"(?P<site>youtube|amazon|google|bing|github|chatgpt|spotify)$",
    re.I,
)
_SEARCH_SITE = re.compile(
    r"^(?:search|find|look up|look for)(?: on)? (?P<site>youtube|amazon|google|bing|github|chatgpt|spotify)"
    r"(?: for)? (?P<q>.+)$",
    re.I,
)
_SEARCH_SHORT = re.compile(r"^(?P<site>youtube|amazon|google|spotify) (?P<q>.+)$", re.I)
_ASK_CHATGPT = re.compile(r"^(?:ask|tell) (?:chat ?gpt|chat gpt)(?: about| to| for| that)?[ ,:]+(?P<q>.+)$", re.I)
# "open edge then type github.com then press enter" -> three steps
_THEN = re.compile(r"\s*,?\s+(?:and then|then|after that|and after that)\s+", re.I)
MAX_STEPS = 5

# "play dude", "play the song kesariya": find it on YouTube ("... on spotify" is matched above)
_PLAY = re.compile(r"^(?:play|put on)(?: the song| the track| song| some| me)? (?P<q>.+)$", re.I)
_SEARCH = re.compile(r"^(?:search|google|look up|search the web)(?: for)? (?P<q>.+)$", re.I)
_WIKI = re.compile(
    r"^(?:who is|who was|who are|what is|what are|what was|tell me about|explain|wiki"
    r"|wikipedia)(?: an?| the)? (?P<topic>.+)$",
    re.I,
)


def fast_path(text: str) -> Command | None:
    """Return a Command for a known phrase, or None to let the AI handle it."""
    t = clean(text)
    if not t:
        return None
    low = " ".join(t.lower().split())

    if low in _SIMPLE:
        return _SIMPLE[low]

    if m := _SCROLL.match(low):
        return _scroll(m)

    if m := _ZOOM.match(low):
        n = _number(m.group("n"))
        if n is not None and 1 <= n <= GRID_CELLS:
            return GridZoomCmd(action="grid_zoom", cell=n)

    if m := _GRID_CLICK.match(low):
        n = _number(m.group("n"))
        if n is not None and 1 <= n <= GRID_CELLS:
            kind = m.group("kind").lower()
            return GridClickCmd(
                action="grid_click", cell=n,
                button="right" if kind == "right click" else "left",
                count=2 if kind.startswith("double") else 1,
            )

    if m := _TYPE.match(t):  # original case kept for what gets typed
        return TypeCmd(action="type", text=m.group("text").strip()[:500])

    if m := _PRESS.match(low):
        key = _KEY_NAMES.get(m.group("key").strip())
        if key:
            return KeyCmd(action="key", key=key)

    if m := _OPEN.match(t):
        if _BLOCKED_APPS.match(m.group("app").strip()):
            return UnknownCmd(action="unknown", say=f"For safety I can't open that. I can open: {app_list_text()}.")
        app = find_app(m.group("app"))
        if app:
            return OpenAppCmd(action="open_app", app=app)
        site = m.group("app").strip()
        if resolve_site(site):                       # "go to github", "open codechef.com"
            return GoToCmd(action="goto", site=site[:200])
        # not an app or a known website: fall through to search rules / AI

    if m := _CUR_CONVERT.match(low):
        src, dst = currency_code(m.group("from")), currency_code(m.group("to"))
        if src and dst:
            amt = m.group("amt") or "1"
            amount = 1.0 if amt in ("a", "an", "one") else float(amt.replace(",", ""))
            if amount > 0:
                return CurrencyCmd(action="currency", amount=amount, from_cur=src, to_cur=dst)
    if m := _CUR_RATE.match(low):
        src = currency_code(m.group("from"))
        dst = currency_code(m.group("to")) if m.group("to") else ("USD" if src == "INR" else "INR")
        if src and dst:
            return CurrencyCmd(action="currency", amount=1, from_cur=src, to_cur=dst)

    if m := (_DEFINE.match(low) or _MEANS.match(low)):
        return DefineCmd(action="define", word=m.group("word").strip()[:40])

    if m := _NEWS.match(t):
        return NewsCmd(action="news", topic=(m.group("topic") or "").strip()[:80] or None)

    if m := _WA_CALL.match(t):
        video = any(m.group(g) for g in ("v1", "v2", "v3", "v4"))
        who = m.group("who").strip(" ,.")
        if who and _number(who) is None:
            return WhatsAppCmd(action="whatsapp", contact=who[:60], kind="video_call" if video else "voice_call")

    for rx in (_WA_SEND, _WA_MSG, _WA_SEND_TO, _WA_MSG_SHORT):
        if m := rx.match(t):
            who = re.sub(r"\s+(?:on|in|via|over|through)$", "", m.group("who").strip(" ,."), flags=re.I)
            text = m.group("text").strip()
            if who and text:
                return WhatsAppCmd(action="whatsapp", contact=who[:60], kind="message", text=text[:500])

    if m := _WA_JUST_NAME.match(t):                   # "message amma" -> open her chat
        return WhatsAppCmd(action="whatsapp", contact=m.group("who")[:60], kind="open")

    if m := _WA_OPEN.match(t):
        return WhatsAppCmd(action="whatsapp", contact=m.group("who").strip(" ,.")[:60], kind="open")

    if m := _MEMORY.match(low):
        p = (m.group("p") or "today").replace("in the ", "").replace("earlier today", "today")
        period = {"last hour": "last_hour", "this week": "this_week", "so far": "today"}.get(p, p)
        return MemoryCmd(action="memory", period=period)

    if m := _CLICK_ON.match(t):
        target = re.sub(r"^(?:the|a|an) ", "", m.group("target").strip(), flags=re.I).strip()
        kind = m.group("kind").lower()
        if target and _number(target) is None and target.lower() not in ("it", "that", "this", "here"):
            return SmartClickCmd(action="click_on", target=target[:80],
                                 button="right" if kind == "right click" else "left",
                                 count=2 if kind.startswith("double") else 1)

    if m := _WEATHER.match(low):
        return WeatherCmd(action="weather", place=m.group("place").strip()[:80])

    if m := _AIR.match(low):
        return AirQualityCmd(action="air_quality", place=m.group("place").strip()[:80])

    if m := _ASK_CHATGPT.match(t):
        return SearchCmd(action="search", site="chatgpt", query=m.group("q").strip()[:200])

    for rx in (_SEARCH_ON, _SEARCH_SITE, _SEARCH_SHORT):
        if m := rx.match(t):
            site = m.group("site").lower().replace(" ", "")
            return SearchCmd(action="search", site=site,
                             query=m.group("q").strip()[:200])

    if m := _PLAY.match(t):
        return SearchCmd(action="search", site="youtube", query=m.group("q").strip()[:200])

    if m := _SEARCH.match(t):
        return SearchCmd(action="search", site="bing", query=m.group("q").strip()[:200])

    if m := _WIKI.match(t):
        topic = m.group("topic").strip(" ?")
        if topic and topic.lower() not in ("this", "that", "it", "on my screen", "on the screen"):
            return WikiCmd(action="wiki", topic=topic[:100])

    return None


def split_steps(text: str) -> list[str]:
    """Split "open edge then type github.com then press enter" into separate commands."""
    parts = [p.strip(" ,.") for p in _THEN.split(text.strip()) if p.strip(" ,.")]
    return parts[:MAX_STEPS] if len(parts) > 1 else [text]
