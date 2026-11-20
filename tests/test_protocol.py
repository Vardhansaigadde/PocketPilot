import json

import pytest

from server.protocol import MAX_MOVE, MAX_SCROLL, BadMessage, Click, Move, Scroll, parse_message


def msg(**kw) -> str:
    return json.dumps(kw)


def test_move_parses():
    m = parse_message(msg(t="move", dx=3, dy=-4.5))
    assert isinstance(m, Move) and m.dx == 3 and m.dy == -4.5


def test_huge_move_is_clamped():
    m = parse_message(msg(t="move", dx=99999, dy=-99999))
    assert m.dx == MAX_MOVE and m.dy == -MAX_MOVE


def test_huge_scroll_is_clamped():
    m = parse_message(msg(t="scroll", dy=1000))
    assert isinstance(m, Scroll) and m.dy == MAX_SCROLL


def test_click_defaults_to_left_single():
    m = parse_message(msg(t="click"))
    assert isinstance(m, Click) and m.button == "left" and m.count == 1


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        "[1, 2]",
        msg(t="explode"),                     # unknown type
        msg(dx=1, dy=1),                      # no type
        msg(t="click", button="side"),        # unknown button
        msg(t="click", count=5),              # triple+ clicks not allowed
        msg(t="key", key="f13"),              # key not on the allow-list
        msg(t="hotkey", combo="close_window"),  # risky combo not allowed in v1
        msg(t="text", text=""),               # empty text
        msg(t="text", text="x" * 501),        # too long
        msg(t="zoom", steps=50),              # out of range
        msg(t="move", dx="left", dy=0),       # wrong type
    ],
)
def test_bad_messages_are_rejected(bad):
    with pytest.raises(BadMessage):
        parse_message(bad)


def test_error_message_names_the_problem():
    with pytest.raises(BadMessage, match="key"):
        parse_message(msg(t="key", key="f13"))
