"""Every action the assistant can take, as a strict schema (the allow-list).

Both the fast-path router and the AI model must produce one of these. Anything
that doesn't match exactly is rejected before the mouse, keyboard or any app
is touched.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from server.protocol import HOTKEYS, KEYS, MEDIA

from .apps import AppName

GRID_COLS = 8
GRID_ROWS = 5
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


class WeatherCmd(_Cmd):
    action: Literal["weather"]
    place: str | None = Field(default=None, max_length=80)


class AirQualityCmd(_Cmd):
    action: Literal["air_quality"]
    place: str | None = Field(default=None, max_length=80)


class WikiCmd(_Cmd):
    action: Literal["wiki"]
    topic: str = Field(min_length=1, max_length=100)


class SearchCmd(_Cmd):
    action: Literal["search"]
    site: Literal["bing", "google", "youtube", "amazon"] = "bing"
    query: str = Field(min_length=1, max_length=200)


class StopCmd(_Cmd):
    action: Literal["stop"]


class UnknownCmd(_Cmd):
    """The model couldn't map the request to an action; `say` explains why."""
    action: Literal["unknown"]
    say: str = Field(default="Sorry, I can't do that yet.", max_length=200)


Command = Annotated[
    Union[
        ScrollCmd, ClickCmd, TypeCmd, KeyCmd, MediaCmd, HotkeyCmd, OpenAppCmd,
        CloseWindowCmd, GridCmd, GridClickCmd, WeatherCmd, AirQualityCmd, WikiCmd,
        SearchCmd, StopCmd, UnknownCmd,
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
