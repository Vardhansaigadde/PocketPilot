"""'Play the second video' / 'open the first result': picked from what is on screen.
The fake pages copy what UI Automation really showed for YouTube, Google and Bing in Edge."""

import pytest

from agent.approvals import Approvals
from agent.commands import OpenResultCmd
from agent.executor import Executor
from agent.results import pick, results, short_title, videos
from agent.router import fast_path
from agent.smart_click import Candidate
from tests.test_dispatch import FakeController


def c(name, kind, x, y, w, h):
    return Candidate(name, kind, (x, y, x + w, y + h))


YOUTUBE = [
    c("Home", "Hyperlink", 20, 185, 255, 50),                                  # left menu
    c("Subscriptions", "Hyperlink", 20, 316, 255, 50),
    c("YouTube Video Player", "Hyperlink", 335, 260, 625, 352),               # the ad's player
    c("Bring your documents to life by generating audio summaries", "Hyperlink", 980, 262, 809, 27),
    c("Sponsored", "Text", 1020, 335, 73, 19),
    c("Kesariya 8K Music Video | Arijit Singh | Brahmastra 4 minutes, 11 seconds", "Hyperlink", 980, 634, 826, 66),
    c("Kesariya 8K Music Video | Arijit Singh | Brahmastra 4 minutes, 11 seconds", "Text", 980, 634, 826, 66),
    c("Sony Music India", "Hyperlink", 1020, 742, 114, 23),                   # channel name
    c("Mix - Kesariya - Brahmastra | Ranbir Kapoor, Alia Bhatt | 4K", "Hyperlink", 980, 1017, 886, 66),
    c("Kesariya Lofi | Slowed and Reverb 3 minutes, 50 seconds", "Hyperlink", 980, 1200, 826, 66),
    c("Kesariya Full Song Lyrics 2 hours, 1 minute", "Hyperlink", 980, 1400, 826, 66),
]

GOOGLE = [
    c("AI Mode", "Hyperlink", 248, 210, 96, 60),
    c("Python Tutorial W3Schools https://www.w3schools.com › python", "Hyperlink", 263, 307, 292, 90),
    c("Read more", "Hyperlink", 728, 430, 87, 21),
    c("Python Full Course for Beginners YouTube Programming with Mosh 12 Feb 2025", "Hyperlink", 473, 550, 606, 104),
    c("Learn Python in Only 30 Minutes (Beginner Tutorial) YouTube Indently 18 Nov 2024", "Hyperlink", 473, 924, 606, 105),
]

BING = [
    c("LikeDislikeThe best starting points for learning Python include the official tutorial "
      "(https://docs.python.org) and W3Schools", "ListItem", 185, 765, 1350, 644),     # AI answer box
    c("Copilot Search Branding", "Hyperlink", 185, 783, 134, 19),
    c("Copilot Search Branding", "Text", 185, 774, 134, 37),
    c("Learn more about Python from the official docs and guides", "Hyperlink", 185, 900, 600, 30),
    c("coursera.orghttps://www.coursera.org › python", "ListItem", 185, 306, 729, 337),   # an ad
    c("Sponsored", "Text", 188, 417, 60, 16),
    c("100% Online Courses | Coursera", "Hyperlink", 185, 370, 687, 34),
    c("W3SchoolsPython Tutorial - W3Schoolshttps://www.w3schools.com/python/", "ListItem", 1121, 828, 414, 104),
    c("Python Tutorial - W3Schools", "Hyperlink", 1121, 828, 414, 104),            # AI answer source card
    c("Python.org The Python Tutorial", "ListItem", 185, 1100, 729, 150),             # real result
    c("https://docs.python.org › 3 › tutorial", "Text", 229, 1124, 300, 20),
    c("The Python Tutorial — Python 3.15 documentation", "Hyperlink", 185, 1150, 500, 30),
    c("Tutorial index", "Hyperlink", 185, 1200, 200, 20),                              # sub-link, same box
    c("W3Schools Python", "ListItem", 185, 1260, 729, 150),
    c("https://www.w3schools.com › python", "Text", 229, 1284, 300, 20),
    c("Python Tutorial - W3Schools", "Hyperlink", 185, 1310, 500, 30),
]


def test_youtube_counts_only_real_videos():
    names = [short_title(v.name) for v in videos(YOUTUBE, on_youtube=True)]
    assert names == ["Kesariya 8K Music Video | Arijit Singh | Brahmastra",
                     "Kesariya Lofi | Slowed and Reverb", "Kesariya Full Song Lyrics"]


def test_google_results_and_videos():
    assert [short_title(r.name) for r in results(GOOGLE)] == [
        "Python Tutorial W3Schools", "Python Full Course for Beginners",
        "Learn Python in Only 30 Minutes (Beginner Tutorial)"]
    hit, count = pick(GOOGLE, 2, "video", "python tutorial - Google Search")
    assert count == 2 and "Learn Python" in hit.name


def test_bing_skips_ads_ai_cards_and_sub_links():
    assert [r.name for r in results(BING)] == ["The Python Tutorial — Python 3.15 documentation",
                                               "Python Tutorial - W3Schools"]


def test_pick_last_and_too_far():
    assert pick(YOUTUBE, -1, "video", "kesariya - YouTube")[0].name.startswith("Kesariya Full Song")
    assert pick(YOUTUBE, 5, "video", "kesariya - YouTube") == (None, 3)
    assert pick([], 1, "result") == (None, 0)


class FakeClicker:
    def __init__(self, cands, title):
        self.cands, self.title = cands, title

    def controls(self):
        return self.cands

    def window_title(self):
        return self.title


def run(cmd, cands, title):
    ctl = FakeController()
    ex = Executor(ctl, Approvals(), clicker=FakeClicker(cands, title), launcher=lambda t: None,
                  app_available=lambda t: True)
    return ex.run(cmd), ctl


def test_executor_clicks_the_second_video():
    out, ctl = run(OpenResultCmd(action="open_result", n=2, kind="video"), YOUTUBE, "kesariya - YouTube - Edge")
    assert out.ok and out.say == 'Opening the 2nd video: "Kesariya Lofi | Slowed and Reverb".'
    assert ("move_to", 1393, 1233) in ctl.calls and ("click", "left", 1) in ctl.calls


def test_executor_says_how_many_it_can_see():
    out, ctl = run(OpenResultCmd(action="open_result", n=6, kind="video"), YOUTUBE, "kesariya - YouTube")
    assert not out.ok and "only see 3 videos" in out.say
    assert not any(call[0] == "click" for call in ctl.calls)


@pytest.mark.parametrize("said, n, kind", [
    ("play the second video", 2, "video"),
    ("click the 3rd video", 3, "video"),
    ("open the first result", 1, "result"),
    ("open the last result", -1, "result"),
    ("open video number 2", 2, "video"),
    ("watch the fourth video on youtube", 4, "video"),
    ("click the second link", 2, "link"),
    ("play the second one", 2, "result"),
])
def test_phrases(said, n, kind):
    cmd = fast_path(said)
    assert isinstance(cmd, OpenResultCmd) and (cmd.n, cmd.kind) == (n, kind)


def test_the_second_one_alone_stays_a_which_one_answer():
    assert fast_path("the second one") is None
    assert fast_path("click the login button").action == "click_on"


@pytest.mark.parametrize("said, n, kind", [
    ("రెండో వీడియో ప్లే చెయ్యి", 2, "video"),
    ("modati result open cheyyi", 1, "result"),
    ("మూడో పాట పెట్టు", 3, "video"),
    ("చివరి వీడియో", -1, "video"),
])
def test_telugu_phrases(said, n, kind):
    from agent import telugu

    cmd = telugu.to_command(said)
    assert isinstance(cmd, OpenResultCmd) and (cmd.n, cmd.kind) == (n, kind)


def test_telugu_reply():
    from agent.telugu import reply

    assert reply('Opening the 2nd video: "Kesariya".') == '2వ వీడియో తెరుస్తున్నాను: "Kesariya".'


def test_browser_page_that_is_still_waking_up_is_read_again():
    class WakingClicker(FakeClicker):
        def __init__(self):
            super().__init__(YOUTUBE, "kesariya - YouTube - Personal - Microsoft Edge")
            self.reads = 0

        def controls(self):
            self.reads += 1
            return [] if self.reads == 1 else self.cands       # 1st read: only the toolbar

    ctl, clicker = FakeController(), WakingClicker()
    ex = Executor(ctl, Approvals(), clicker=clicker, launcher=lambda t: None, app_available=lambda t: True,
                  sleep=lambda s: None)
    out = ex.run(OpenResultCmd(action="open_result", n=1, kind="video"))
    assert out.ok and clicker.reads == 2
