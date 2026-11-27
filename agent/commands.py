"""Every action the assistant can take, as a strict schema (the allow-list).

Both the fast-path router and the AI model must produce one of these. Anything
that doesn't match exactly is rejected before the mouse, keyboard or any app
is touched.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from server.protocol import HOTKEYS, KEYS, MEDIA

from .apps import AppName

GRID_COLS = 12
GRID_ROWS = 8
GRID_CELLS = GRID_COLS * GRID_ROWS


class _Cmd(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScrollCmd(_Cmd):
    action: Literal["scroll"]
    direction: Literal["up", "down"]
    amount: int = Field(default=5, ge=1, le=20)


class ClickCmd(_Cmd):
    action: Literal["click"]
    button: Literal["left", "right", "middle"] = "left"
    count: int = Field(default=1, ge=1, le=2)


class TypeCmd(_Cmd):
    action: Literal["type"]
    text: str = Field(min_length=1, max_length=500)


class KeyCmd(_Cmd):
    action: Literal["key"]
    key: KEYS


class MediaCmd(_Cmd):
    action: Literal["media"]
    key: MEDIA


class BrightnessCmd(_Cmd):
    """Laptop screen brightness: up / down by 10 %, or set to a level (5-100 %)."""
    action: Literal["brightness"]
    change: Literal["up", "down", "set"]
    level: int | None = Field(default=None, ge=0, le=100)


class HotkeyCmd(_Cmd):
    action: Literal["hotkey"]
    combo: HOTKEYS


class OpenAppCmd(_Cmd):
    action: Literal["open_app"]
    app: AppName


class CloseWindowCmd(_Cmd):
    """Closes the active window. Always asks Approve on the phone first."""
    action: Literal["close_window"]


class GridCmd(_Cmd):
    action: Literal["grid"]
    show: bool


class GridClickCmd(_Cmd):
    action: Literal["grid_click"]
    cell: int = Field(ge=1, le=GRID_CELLS)
    button: Literal["left", "right"] = "left"
    count: int = Field(default=1, ge=1, le=2)


class GridZoomCmd(_Cmd):
    """Split one grid box into 9 smaller boxes for precise clicks ("zoom 14")."""
    action: Literal["grid_zoom"]
    cell: int = Field(ge=1, le=GRID_CELLS)


class SmartClickCmd(_Cmd):
    """Click a button/link by its name ("click the Login button")."""
    action: Literal["click_on"]
    target: str = Field(min_length=1, max_length=80)
    button: Literal["left", "right"] = "left"
    count: int = Field(default=1, ge=1, le=2)


class OpenResultCmd(_Cmd):
    """Open the nth search result or video on screen ("play the second video")."""
    action: Literal["open_result"]
    n: int = Field(ge=-1, le=20)                     # 1 = first, -1 = last
    kind: Literal["result", "video", "link"] = "result"

    @field_validator("n")
    @classmethod
    def _not_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("n starts at 1 (or -1 for the last one)")
        return v


class ScreenCmd(_Cmd):
    """Look at the screen: describe it, summarize the page, explain an error, or read it aloud."""
    action: Literal["screen"]
    mode: Literal["describe", "summarize", "explain_error", "read"] = "describe"


class WhatsAppCmd(_Cmd):
    """Message or call someone on WhatsApp. Sending and calling always wait for Approve."""
    action: Literal["whatsapp"]
    contact: str = Field(min_length=1, max_length=60)
    kind: Literal["message", "voice_call", "video_call", "open"] = "open"
    text: str | None = Field(default=None, max_length=500)


class WakeScreenCmd(_Cmd):
    """"Open my laptop" / "wake up": turn the screen back on."""
    action: Literal["wake_screen"]


class KeepAwakeCmd(_Cmd):
    """Keep the laptop from sleeping while PocketPilot runs (charging = only when plugged in)."""
    action: Literal["keep_awake"]
    mode: Literal["charging", "always", "off"] = "always"


class MemoryCmd(_Cmd):
    """"What was I working on yesterday?" -> answer from the local history log."""
    action: Literal["memory"]
    period: Literal["today", "yesterday", "last_hour", "this_week"] = "today"


class ForgetCmd(_Cmd):
    """"Clear my history" (asks Approve on the phone first)."""
    action: Literal["forget_history"]


class WeatherCmd(_Cmd):
    action: Literal["weather"]
    place: str | None = Field(default=None, max_length=80)


class AirQualityCmd(_Cmd):
    action: Literal["air_quality"]
    place: str | None = Field(default=None, max_length=80)


class WikiCmd(_Cmd):
    action: Literal["wiki"]
    topic: str = Field(min_length=1, max_length=100)


class CurrencyCmd(_Cmd):
    action: Literal["currency"]
    amount: float = Field(default=1, gt=0, le=1e12)
    from_cur: str = Field(min_length=3, max_length=3)     # ISO code, e.g. USD
    to_cur: str = Field(default="INR", min_length=3, max_length=3)


class DefineCmd(_Cmd):
    action: Literal["define"]
    word: str = Field(min_length=1, max_length=40)


class NewsCmd(_Cmd):
    action: Literal["news"]
    topic: str | None = Field(default=None, max_length=80)


class CricketCmd(_Cmd):
    action: Literal["cricket"]


class GoToCmd(_Cmd):
    """Open a website by name ("github") or address ("github.com/user/repo")."""
    action: Literal["goto"]
    site: str = Field(min_length=1, max_length=200)


class SearchCmd(_Cmd):
    action: Literal["search"]
    site: Literal["bing", "google", "youtube", "amazon", "github", "chatgpt", "spotify"] = "bing"
    query: str = Field(min_length=1, max_length=200)


class TaskCmd(_Cmd):
    """A request that needs several steps; the task agent works through it."""
    action: Literal["task"]
    goal: str = Field(min_length=3, max_length=300)


class StopCmd(_Cmd):
    action: Literal["stop"]


class UnknownCmd(_Cmd):
    """The model couldn't map the request to an action; `say` explains why."""
    action: Literal["unknown"]
    say: str = Field(default="Sorry, I can't do that yet.", max_length=200)


Command = Annotated[
    Union[
        ScrollCmd, ClickCmd, TypeCmd, KeyCmd, MediaCmd, BrightnessCmd, HotkeyCmd, OpenAppCmd,
        CloseWindowCmd, GridCmd, GridClickCmd, GridZoomCmd, SmartClickCmd, OpenResultCmd, ScreenCmd, WhatsAppCmd, WakeScreenCmd, KeepAwakeCmd, MemoryCmd, ForgetCmd, WeatherCmd, AirQualityCmd, WikiCmd,
        CurrencyCmd, DefineCmd, NewsCmd, CricketCmd, GoToCmd, SearchCmd, TaskCmd, StopCmd, UnknownCmd,
    ],
    Field(discriminator="action"),
]

_adapter: TypeAdapter[Command] = TypeAdapter(Command)


class BadCommand(ValueError):
    """Raised when something isn't a valid command."""


def parse_command(data: Any) -> Command:
    """Validate a dict (e.g. the AI's JSON) into a Command, or raise BadCommand."""
    if not isinstance(data, dict):
        raise BadCommand("command must be a JSON object")
    try:
        return _adapter.validate_python(data)
    except ValidationError as exc:
        raise BadCommand(str(exc.errors()[0].get("msg", "invalid command"))) from exc


def command_schema() -> dict:
    """JSON schema of all commands (given to the AI so it can only answer in this shape)."""
    return _adapter.json_schema()
