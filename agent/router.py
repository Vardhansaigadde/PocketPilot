"""Fast path: common phrases mapped straight to commands, with no AI.

This is instant and works offline. `fast_path()` returns None when it doesn't
recognise the phrase; the caller then asks the AI model instead.
"""

from __future__ import annotations

import re

from skills.websites import resolve as resolve_site

from .apps import find_app
from .commands import (
    GRID_CELLS, AirQualityCmd, ClickCmd, CloseWindowCmd, Command, GoToCmd, GridClickCmd, GridCmd,
    HotkeyCmd, KeyCmd, MediaCmd, OpenAppCmd, ScrollCmd, SearchCmd, StopCmd, TypeCmd,
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
    "twenty": 20, "thirty": 30, "forty": 40, "to": 2, "too": 2, "for": 4, "won": 1,
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


def _simple(phrases: str, cmd: Command) -> None:
    for p in phrases.split("|"):
        _SIMPLE[p] = cmd


_simple("stop|cancel|never mind|nevermind|stop it|abort|stop everything", StopCmd(action="stop"))
_simple("click|left click|click it|click that|tap", ClickCmd(action="click"))
_simple("double click|double tap", ClickCmd(action="click", count=2))
_simple("right click", ClickCmd(action="click", button="right"))
_simple("middle click", ClickCmd(action="click", button="middle"))
_simple("volume up|louder|turn it up|turn up the volume|increase volume|increase the volume",
        MediaCmd(action="media", key="volume_up"))
_simple("volume down|quieter|softer|turn it down|turn down the volume|decrease volume"
        "|decrease the volume|lower the volume", MediaCmd(action="media", key="volume_down"))
_simple("mute|unmute|mute the volume|mute sound|silence", MediaCmd(action="media", key="mute"))
_simple("play|pause|resume|play pause|play or pause|pause the music|play the music"
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
_TYPE = re.compile(r"^(?:type|type in|type out|enter text)[ :,]+(?P<text>.+)$", re.I | re.S)
_PRESS = re.compile(r"^(?:press|hit|push)(?: the)? (?P<key>.+?)(?: key| button)?$", re.I)
_OPEN = re.compile(r"^(?:open|launch|start|run|bring up|go to|visit|navigate to|take me to"
                   r"|browse to|show me) (?P<app>.+)$", re.I)
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
    r"(?P<site>youtube|amazon|google|bing|github|chatgpt)$",
    re.I,
)
_SEARCH_SITE = re.compile(
    r"^(?:search|find|look up|look for)(?: on)? (?P<site>youtube|amazon|google|bing|github|chatgpt)"
    r"(?: for)? (?P<q>.+)$",
    re.I,
)
_SEARCH_SHORT = re.compile(r"^(?P<site>youtube|amazon|google) (?P<q>.+)$", re.I)
_ASK_CHATGPT = re.compile(r"^(?:ask|tell) (?:chat ?gpt|chat gpt)(?: about| to| for| that)?[ ,:]+(?P<q>.+)$", re.I)
# "open edge then type github.com then press enter" -> three steps
_THEN = re.compile(r"\s*,?\s+(?:and then|then|after that|and after that)\s+", re.I)
MAX_STEPS = 5

_SEARCH = re.compile(r"^(?:search|google|look up|search the web)(?: for)? (?P<q>.+)$", re.I)
_WIKI = re.compile(
    r"^(?:who is|who was|who are|what is|what are|what was|tell me about|define|explain|wiki"
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
        app = find_app(m.group("app"))
        if app:
            return OpenAppCmd(action="open_app", app=app)
        site = m.group("app").strip()
        if resolve_site(site):                       # "go to github", "open codechef.com"
            return GoToCmd(action="goto", site=site[:200])
        # not an app or a known website: fall through to search rules / AI

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
