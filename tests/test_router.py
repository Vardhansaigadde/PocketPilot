"""Fast-path phrases map to the right command, with no AI involved."""

import pytest

from agent.router import clean, fast_path


@pytest.mark.parametrize(
    "said, expected",
    [
        ("Scroll down.", {"action": "scroll", "direction": "down", "amount": 5}),
        ("scroll up a lot", {"action": "scroll", "direction": "up", "amount": 12}),
        ("scroll down a little", {"action": "scroll", "direction": "down", "amount": 2}),
        ("scroll down 3 times", {"action": "scroll", "direction": "down", "amount": 3}),
        ("Click.", {"action": "click", "button": "left", "count": 1}),
        ("right click", {"action": "click", "button": "right", "count": 1}),
        ("Double click!", {"action": "click", "button": "left", "count": 2}),
        ("Volume up", {"action": "media", "key": "volume_up"}),
        ("turn it down please", {"action": "media", "key": "volume_down"}),
        ("Pause the music.", {"action": "media", "key": "play_pause"}),
        ("next song", {"action": "media", "key": "next"}),
        ("Hey Jarvis, mute.", {"action": "media", "key": "mute"}),
        ("switch app", {"action": "hotkey", "combo": "app_next"}),
        ("show desktop", {"action": "hotkey", "combo": "show_desktop"}),
        ("Copy that", {"action": "hotkey", "combo": "copy"}),
        ("press enter", {"action": "key", "key": "enter"}),
        ("Press the escape key.", {"action": "key", "key": "esc"}),
        ("hit page down", {"action": "key", "key": "page_down"}),
        ("Open Notepad.", {"action": "open_app", "app": "notepad"}),
        ("can you open google chrome", {"action": "open_app", "app": "chrome"}),
        ("launch the calculator", {"action": "open_app", "app": "calculator"}),
        ("open VS Code", {"action": "open_app", "app": "vscode"}),
        ("Close the window.", {"action": "close_window"}),
        ("show grid", {"action": "grid", "show": True}),
        ("hide the grid", {"action": "grid", "show": False}),
        ("click 14", {"action": "grid_click", "cell": 14, "button": "left", "count": 1}),
        ("Click fourteen.", {"action": "grid_click", "cell": 14, "button": "left", "count": 1}),
        ("right click twenty one", {"action": "grid_click", "cell": 21, "button": "right", "count": 1}),
        ("double click 3", {"action": "grid_click", "cell": 3, "button": "left", "count": 2}),
        ("What's the weather?", {"action": "weather", "place": None}),
        ("weather in Hyderabad", {"action": "weather", "place": "hyderabad"}),
        ("what is the weather like in New Delhi today", {"action": "weather", "place": "new delhi"}),
        ("when is sunset", {"action": "weather", "place": None}),
        ("air quality", {"action": "air_quality", "place": None}),
        ("AQI in Mumbai", {"action": "air_quality", "place": "mumbai"}),
        ("search YouTube for lofi music", {"action": "search", "site": "youtube", "query": "lofi music"}),
        ("Play Arijit Singh songs on YouTube.", {"action": "search", "site": "youtube", "query": "Arijit Singh songs"}),
        ("search amazon for wireless mouse", {"action": "search", "site": "amazon", "query": "wireless mouse"}),
        ("youtube cooking videos", {"action": "search", "site": "youtube", "query": "cooking videos"}),
        ("Search for cheap flights to Goa", {"action": "search", "site": "bing", "query": "cheap flights to Goa"}),
        ("Who is APJ Abdul Kalam?", {"action": "wiki", "topic": "APJ Abdul Kalam"}),
        ("tell me about the Taj Mahal", {"action": "wiki", "topic": "Taj Mahal"}),
        ("go to github", {"action": "goto", "site": "github"}),
        ("Open ChatGPT.", {"action": "goto", "site": "ChatGPT"}),
        ("visit codechef", {"action": "goto", "site": "codechef"}),
        ("open youtube", {"action": "goto", "site": "youtube"}),
        ("take me to github.com/Vardhansaigadde/PocketPilot",
         {"action": "goto", "site": "github.com/Vardhansaigadde/PocketPilot"}),
        ("search github for pocketpilot", {"action": "search", "site": "github", "query": "pocketpilot"}),
        ("ask ChatGPT how to reverse a list in Python",
         {"action": "search", "site": "chatgpt", "query": "how to reverse a list in Python"}),
        ("new tab", {"action": "hotkey", "combo": "new_tab"}),
        ("go back", {"action": "hotkey", "combo": "back"}),
        ("refresh the page", {"action": "hotkey", "combo": "refresh"}),
        ("go to the address bar", {"action": "hotkey", "combo": "address_bar"}),
        ("stop", {"action": "stop"}),
        ("Never mind.", {"action": "stop"}),
    ],
)
def test_fast_path(said, expected):
    cmd = fast_path(said)
    assert cmd is not None, said
    assert cmd.model_dump() == expected


def test_type_keeps_original_case():
    cmd = fast_path("Type Hello World.")
    assert cmd.model_dump() == {"action": "type", "text": "Hello World"}


@pytest.mark.parametrize(
    "said",
    [
        "",
        "   ",
        "open the thing I used yesterday",
        "click on the login button",    # smart click is v3
        "reply to Ravi that I'm late",
        "what is this",
        "make it brighter",
        "I want to write some code",    # must not type "some code"
        "write an email to my teacher",
    ],
)
def test_unknown_phrases_go_to_the_ai(said):
    assert fast_path(said) is None


def test_clean_strips_fillers():
    assert clean("Hey Jarvis, please open notepad for me.") == "open notepad"
    assert clean("  Could you scroll down now?  ") == "scroll down"


def test_open_app_wins_over_website():
    assert fast_path("open notepad").model_dump() == {"action": "open_app", "app": "notepad"}


def test_unknown_sites_go_to_the_ai():
    assert fast_path("go to sleep") is None
    assert fast_path("take me to my happy place") is None


def test_split_steps():
    from agent.router import split_steps

    assert split_steps("open edge then type github.com and then press enter") == [
        "open edge", "type github.com", "press enter"]
    assert split_steps("search youtube for rock and roll") == ["search youtube for rock and roll"]
    assert len(split_steps(" then ".join(["scroll down"] * 9))) == 5   # at most 5 steps
