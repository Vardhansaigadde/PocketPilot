"""Shared test setup: tests never look at the real laptop screen."""

import pytest


@pytest.fixture(autouse=True)
def no_real_front_window(monkeypatch):
    """The executor asks which window is in front (is it a browser?). In tests that is
    "no window", unless a test passes its own `front=`."""
    monkeypatch.setattr("agent.executor._front_title", lambda: "")
