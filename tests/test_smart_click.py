"""Smart click: matching names, risky buttons, OCR words, fallback order (no real screen)."""

import pytest

from agent.screen import TextBox
from agent.smart_click import (
    Candidate, SmartClicker, best_match, clean_target, is_risky, ocr_candidates, score,
)


def c(name, kind="Button", rect=(0, 0, 100, 30)):
    return Candidate(name, kind, rect)


@pytest.mark.parametrize("target, name, at_least", [
    ("sign in", "Sign in", 1.0),
    ("login", "Log in", 0.95),            # speech-to-text spacing
    ("sign-in", "Sign in", 0.95),
    ("settings", "Settings and more", 0.9),
    ("terminal", "Open Terminal", 0.8),
])
def test_scores_good_matches(target, name, at_least):
    assert score(target, name) >= at_least


@pytest.mark.parametrize("target, name", [
    ("show sidebar", "Hide sidebar"),     # opposite meaning must not match
    ("send", "Settings"),
    ("ok", "Book"),
    ("", "Anything"),
])
def test_rejects_wrong_matches(target, name):
    assert score(target, name) < 0.6


def test_clean_target_drops_filler():
    assert clean_target("the Sign in button") == "sign in"
    assert clean_target("on the Downloads link") == "downloads"


def test_best_match_prefers_exact_then_buttons():
    cands = [c("Search settings", "Text"), c("Search", "Hyperlink"), c("Search", "Button", (10, 10, 50, 30))]
    hit = best_match("search", cands)
    assert hit.name == "Search" and hit.kind in ("Button", "Hyperlink")


def test_long_text_only_counts_on_exact_match():
    paragraph = c("You can show sidebar from the menu at any time", "Text")
    assert best_match("show sidebar", [paragraph]) is None


def test_no_match_returns_none():
    assert best_match("zzz", [c("Save"), c("Open")]) is None


def test_center():
    assert c("x", rect=(100, 200, 140, 220)).center == (120, 210)


@pytest.mark.parametrize("name", ["Send", "Delete file", "Pay now", "Sign in", "Log out", "Place order",
                                  "Submit", "Confirm purchase", "Uninstall"])
def test_risky_names(name):
    assert is_risky(name)


@pytest.mark.parametrize("name", ["Settings", "Search", "Downloads", "Next", "Open", "Sender details"])
def test_safe_names(name):
    assert not is_risky(name)


def test_ocr_candidates_join_words_on_a_line():
    words = [TextBox("Sign", 100, 50, 40, 20), TextBox("in", 145, 50, 20, 20), TextBox("Help", 100, 200, 40, 20)]
    cands = ocr_candidates(words)
    hit = best_match("sign in", cands)
    assert hit.name == "Sign in" and hit.rect == (100, 50, 165, 70)
    assert all("Help" not in x.name or x.name == "Help" for x in cands)   # no joining across lines


def test_clicker_uses_ui_automation_first():
    ocr_calls = []
    finder = SmartClicker(uia=lambda: [c("Equals")], ocr_words=lambda: ocr_calls.append(1) or [])
    assert finder.find("equals").name == "Equals"
    assert ocr_calls == []


def test_clicker_falls_back_to_ocr():
    finder = SmartClicker(uia=lambda: [c("Close")],
                          ocr_words=lambda: [TextBox("Continue", 300, 400, 80, 20)])
    hit = finder.find("continue")
    assert hit.kind == "OCR text" and hit.center == (340, 410)


def test_clicker_survives_broken_sources():
    def boom():
        raise RuntimeError("no UI Automation")
    assert SmartClicker(uia=boom, ocr_words=boom).find("anything") is None
