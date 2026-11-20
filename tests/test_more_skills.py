"""Currency, dictionary, news and cricket against a fake internet (no real requests, no real keys)."""

import pytest

from skills import WebSkills
from skills.currency import code
from tests.test_skills import fake_internet

RATE = {"amount": 100.0, "base": "USD", "date": "2026-11-20", "rates": {"INR": 9268.0}}
WORD = [{"word": "serendipity", "meanings": [{"partOfSpeech": "noun", "definitions": [
    {"definition": "Finding good things by chance.", "example": "It was pure serendipity."}]}]}]
NEWS = {"articles": [{"title": "ISRO launches a new satellite."}, {"title": "Rain in Hyderabad"},
                     {"title": "Markets rise"}, {"title": "Fourth story"}]}
CRICKET = {"status": "success", "data": [
    {"name": "India vs Australia, 3rd ODI", "matchStarted": True, "matchEnded": False,
     "status": "India need 40 runs", "score": [{"inning": "Australia Inning 1", "r": 280, "w": 8, "o": 50},
                                               {"inning": "India Inning 1", "r": 241, "w": 4, "o": 42.3}]},
    {"name": "Old match", "matchStarted": True, "matchEnded": True, "status": "Done", "score": []}]}


def skills(routes, seen=None, **keys):
    opened = []
    return WebSkills(fake_internet(routes, seen), opened.append, **keys)


def test_currency():
    seen = []
    s = skills({"frankfurter": RATE}, seen=seen)
    assert s.currency(100, "USD", "INR") == "$100 is ₹9,268 (rate of 2026-11-20)."
    assert "amount=100" in str(seen[0].url) and "from=USD" in str(seen[0].url)


@pytest.mark.parametrize("said, iso", [("dollars", "USD"), ("US Dollars", "USD"), ("rupee", "INR"),
                                       ("Rs.", "INR"), ("euros", "EUR"), ("gbp", "GBP"), ("yen", "JPY")])
def test_currency_names(said, iso):
    assert code(said) == iso


def test_unknown_currency_names():
    assert code("github") is None and code("music") is None


def test_same_currency():
    assert "same currency" in skills({}).currency(5, "INR", "INR")


def test_dictionary():
    assert skills({"dictionaryapi": WORD}).define("serendipity") == (
        'serendipity (noun): Finding good things by chance. For example: "It was pure serendipity."')


def test_dictionary_unknown_word():
    assert "couldn't find" in skills({"dictionaryapi": 404}).define("zzqx")


def test_news_needs_a_key():
    out = skills({}).news(None)
    assert "gnews.io" in out and "POCKETPILOT_GNEWS_KEY" in out


def test_news_top_and_topic():
    seen = []
    s = skills({"gnews.io/api/v4/top-headlines": NEWS, "gnews.io/api/v4/search": NEWS}, seen=seen, gnews_key="k")
    assert s.news(None) == "Top news: 1) ISRO launches a new satellite. 2) Rain in Hyderabad. 3) Markets rise."
    assert s.news("ISRO").startswith("News about ISRO: 1)")
    assert "country=in" in str(seen[0].url) and "q=ISRO" in str(seen[1].url)


def test_news_bad_key_and_limit():
    assert "didn't work" in skills({"gnews.io": 401}, gnews_key="bad").news(None)
    assert "limit" in skills({"gnews.io": 429}, gnews_key="k").news(None)


def test_cricket_needs_a_key():
    assert "cricketdata.org" in skills({}).cricket()


def test_cricket_live_first():
    out = skills({"cricapi.com": CRICKET}, cricket_key="k").cricket()
    assert out.startswith("Live: India vs Australia:")
    assert "India 241/4 (42.3 ov)" in out and "India need 40 runs" in out and "Old match" not in out


def test_cricket_bad_key():
    bad = {"status": "failure", "reason": "Invalid API Key"}
    assert "didn't work" in skills({"cricapi.com": bad}, cricket_key="x").cricket()


def test_keys_never_end_up_in_replies():
    out = skills({"gnews.io": 500}, gnews_key="SECRET123").news(None)
    assert "SECRET123" not in out
