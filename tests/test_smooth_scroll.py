"""Smooth scrolling: small finger movements scroll a little at once (no stand-still, then jump)."""

from server.input_control import WHEEL_UNITS, PynputController


class FakeMouse:
    def __init__(self):
        self.units = []                        # what Windows would receive, in 1/120ths of a notch

    def scroll(self, dx, dy):
        self.units.append((int(dx * WHEEL_UNITS), int(dy * WHEEL_UNITS)))


def controller():
    c = PynputController.__new__(PynputController)   # no real mouse or keyboard
    c._mouse = FakeMouse()
    c._scroll_rest = [0.0, 0.0]
    return c


def test_a_small_movement_scrolls_straight_away():
    c = controller()
    c.scroll(0, 0.1)                          # a tenth of a notch: used to send nothing
    assert c._mouse.units == [(0, 12)]


def test_nothing_is_lost_over_many_tiny_moves():
    c = controller()
    for _ in range(30):
        c.scroll(0, -0.02)                    # 30 x 2.4 units = 72 units in total
    assert sum(u for _, u in c._mouse.units) == -72
    assert abs(c._scroll_rest[1]) < 1 / WHEEL_UNITS


def test_both_directions_and_whole_notches():
    c = controller()
    c.scroll(0.5, 1.0)
    assert c._mouse.units == [(60, 120)]
