"""Opening websites by name or address: only safe https addresses come out."""

import pytest

from skills.websites import label, resolve


@pytest.mark.parametrize("said, url", [
    ("github", "https://github.com"),
    ("git hub", "https://github.com"),
    ("the ChatGPT website", "https://chatgpt.com"),
    ("CodeChef.", "https://www.codechef.com"),
    ("youtube", "https://www.youtube.com"),
    ("github dot com", "https://github.com"),
    ("github.com/Vardhansaigadde/PocketPilot", "https://github.com/Vardhansaigadde/PocketPilot"),
    ("github dot com slash Vardhansaigadde slash PocketPilot", "https://github.com/Vardhansaigadde/PocketPilot"),
    ("github/Vardhansaigadde", "https://github.com/Vardhansaigadde"),
    ("example.org", "https://example.org"),
    ("https://news.ycombinator.com", "https://news.ycombinator.com"),
    ("http://example.com", "https://example.com"),           # always upgraded to https
])
def test_resolves(said, url):
    assert resolve(said) == url


@pytest.mark.parametrize("said", [
    "", "sleep", "the desktop", "my files", "some random thing.",
    "javascript:alert(1)", "file:///C:/Windows/System32/cmd.exe", r"C:\Windows",
    "data:text/html,hi", "ftp://example.com", "github.com/<script>", "x" * 300,
])
def test_refuses(said):
    assert resolve(said) is None


def test_labels():
    assert label("https://github.com") == "GitHub"
    assert label("https://github.com/a/b") == "GitHub/a/b"
    assert label("https://www.example.org") == "example.org"
