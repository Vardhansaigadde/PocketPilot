"""Messages the phone sends to the laptop.

Every message is JSON with a "t" (type) field. Anything that doesn't match one
of these shapes is rejected before it can touch the mouse or keyboard, so the
server only ever performs a fixed, known set of actions.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

MAX_MOVE = 400.0     # pixels per message; larger jumps are clamped
MAX_SCROLL = 20.0    # wheel steps per message
MAX_TEXT = 500       # characters per text message

KEYS = Literal[
    "enter", "backspace", "delete", "tab", "esc", "space",
    "up", "down", "left", "right", "home", "end", "page_up", "page_down",
]

HOTKEYS = Literal[
    "app_next",      # Alt+Tab
    "app_prev",      # Alt+Shift+Tab
    "task_view",     # Win+Tab
    "show_desktop",  # Win+D
    "copy", "paste", "cut", "undo", "select_all",
    # browser
    "new_tab",       # Ctrl+T
    "next_tab",      # Ctrl+Tab
    "prev_tab",      # Ctrl+Shift+Tab
    "close_tab",     # Ctrl+W (only in apps with tabs, checked by the executor)
    "reopen_tab",    # Ctrl+Shift+T
    "back",          # Alt+Left
    "forward",       # Alt+Right
    "refresh",       # F5
    "address_bar",   # Ctrl+L
]

MEDIA = Literal["volume_up", "volume_down", "mute", "play_pause", "next", "prev"]
BUTTONS = Literal["left", "right", "middle"]


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


class Move(BaseModel):
    t: Literal["move"]
    dx: float
    dy: float

    @field_validator("dx", "dy")
    @classmethod
    def _limit(cls, v: float) -> float:
        return _clamp(v, MAX_MOVE)


class Click(BaseModel):
    t: Literal["click"]
    button: BUTTONS = "left"
    count: int = Field(default=1, ge=1, le=2)


class Button(BaseModel):
    """Press or release a button without clicking (used for drag)."""
    t: Literal["button"]
    button: BUTTONS = "left"
    action: Literal["down", "up"]


class Scroll(BaseModel):
    t: Literal["scroll"]
    dx: float = 0.0
    dy: float = 0.0

    @field_validator("dx", "dy")
    @classmethod
    def _limit(cls, v: float) -> float:
        return _clamp(v, MAX_SCROLL)


class Zoom(BaseModel):
    """Ctrl + mouse wheel. Positive zooms in."""
    t: Literal["zoom"]
    steps: int = Field(ge=-10, le=10)


class Key(BaseModel):
    t: Literal["key"]
    key: KEYS


class Text(BaseModel):
    t: Literal["text"]
    text: str = Field(min_length=1, max_length=MAX_TEXT)


class Hotkey(BaseModel):
    t: Literal["hotkey"]
    combo: HOTKEYS


class Media(BaseModel):
    t: Literal["media"]
    key: MEDIA


class Ping(BaseModel):
    t: Literal["ping"]
    sent: float | None = None   # phone timestamp in ms, echoed back for lag checks


class Say(BaseModel):
    """A typed voice-style command, e.g. "open notepad" (handled by the assistant)."""
    t: Literal["command"]
    text: str = Field(min_length=1, max_length=300)


class Approve(BaseModel):
    """The user's answer to an Approve card."""
    t: Literal["approve"]
    id: str = Field(min_length=1, max_length=32, pattern=r"^[0-9a-f]+$")
    ok: bool


class Stop(BaseModel):
    """Kill switch: cancel approvals, hide the grid, release the mouse."""
    t: Literal["stop"]


class Lang(BaseModel):
    """Voice language switch on the phone: English or Telugu (v5)."""
    t: Literal["lang"]
    lang: Literal["en", "te"]


MAX_AUDIO_BYTES = 2 * 1024 * 1024   # a recorded voice command (binary frame)

Message = Annotated[
    Union[Move, Click, Button, Scroll, Zoom, Key, Text, Hotkey, Media, Ping, Say, Approve, Stop, Lang],
    Field(discriminator="t"),
]

_adapter: TypeAdapter[Message] = TypeAdapter(Message)


class BadMessage(ValueError):
    """Raised when the phone sends something we won't act on."""


def parse_message(raw: str | bytes) -> Message:
    """Turn raw JSON from the phone into a validated message, or raise BadMessage."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BadMessage("not valid JSON") from exc
    if not isinstance(data, dict):
        raise BadMessage("message must be a JSON object")
    try:
        return _adapter.validate_python(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ())) or "message"
        raise BadMessage(f"{where}: {first.get('msg', 'invalid')}") from exc
