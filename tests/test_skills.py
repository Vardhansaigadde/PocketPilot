"""Skills, tested against a fake internet (httpx.MockTransport). No real requests."""

import httpx
import pytest

from skills import WebSkills, make_client
from skills.web_search import open_in_edge, search_url

GEO = {"results": [{"name": "Hyderabad", "latitude": 17.38, "longitude": 78.46,
                    "admin1": "Telangana", "country": "India"}]}
FORECAST = {
    "current": {"temperature_2m": 27.4, "apparent_temperature": 31.2, "weather_code": 2},
    "daily": {"temperature_2m_max": [30.6], "temperature_2m_min": [19.1],
              "precipitation_probability_max": [10], "sunset": ["2026-11-20T17:39"]},
}
AIR = {"current": {"us_aqi": 162, "pm2_5": 74.6}}
WIKI_SEARCH = {"query": {"search": [{"title": "A. P. J. Abdul Kalam"}]}}
WIKI_SUMMARY = {"extract": ("Avul Pakir Jainulabdeen Abdul Kalam was an Indian aerospace scientist. "
                            "He served as the 11th president of India from 2002 to 2007. "
                            "He was born in Rameswaram. He studied physics.")}


def fake_internet(routes, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        for part, body in routes.items():
            if part in str(request.url):
                if isinstance(body, int):
                    return httpx.Response(body)
                return httpx.Response(200, json=body)
        return httpx.Response(404)
    return make_client(httpx.MockTransport(handler))


def skills(routes, home=None, seen=None):
    opened = []
    s = WebSkills(fake_internet(routes, seen), opened.append, home_city=home)
    return s, opened


def test_weather():
    s, _ = skills({"geocoding-api": GEO, "api.open-meteo.com/v1/forecast": FORECAST})
    text = s.weather("hyderabad")
    assert text == ("Hyderabad: 27°C and partly cloudy, feels like 31°C. "
                    "Today 19 to 31°C, 10% chance of rain, sunset at 5:39 PM.")


def test_weather_uses_home_city():
    seen = []
    s, _ = skills({"geocoding-api": GEO, "/v1/forecast": FORECAST}, home="Hyderabad", seen=seen)
    s.weather(None)
    assert "name=Hyderabad" in str(seen[0].url)


def test_weather_without_city_asks_which():
    s, _ = skills({})
    assert "Which city" in s.weather(None)


def test_unknown_city():
    s, _ = skills({"geocoding-api": {"results": []}})
    assert s.weather("Atlantis") == "I couldn't find a place called Atlantis."


def test_offline_is_a_polite_sentence():
    s, _ = skills({"geocoding-api": 503})
    assert "internet" in s.weather("Pune")


def test_air_quality():
    s, _ = skills({"geocoding-api": GEO, "air-quality-api": AIR})
    text = s.air_quality("Hyderabad")
    assert text.startswith("Air quality in Hyderabad is unhealthy: AQI 162, PM2.5 75.")
    assert "mask" in text


def test_wikipedia_summary_is_short():
    seen = []
    s, _ = skills({"w/api.php": WIKI_SEARCH, "page/summary/": WIKI_SUMMARY}, seen=seen)
    text = s.wiki("abdul kalam")
    assert text.startswith("Avul Pakir")
    assert text.count(".") <= 4 and len(text) <= 400
    assert "A._P._J._Abdul_Kalam" in str(seen[1].url)
    assert seen[0].headers["user-agent"].startswith("PocketPilot")


def test_wikipedia_403_explains_the_contact_setting():
    s, _ = skills({"w/api.php": 403})
    assert "POCKETPILOT_CONTACT" in s.wiki("anything")


def test_contact_goes_into_the_app_name():
    from skills import user_agent

    assert "(https://github.com/me/pp)" in user_agent("https://github.com/me/pp")


def test_wikipedia_nothing_found():
    s, _ = skills({"w/api.php": {"query": {"search": []}}})
    assert "couldn't find" in s.wiki("zzzqqq")


def test_search_opens_a_safe_url():
    s, opened = skills({})
    assert s.search("youtube", "lofi & chill") == "Searching YouTube for lofi & chill."
    assert opened == ["https://www.youtube.com/results?search_query=lofi+%26+chill"]


@pytest.mark.parametrize("site, start", [
    ("bing", "https://www.bing.com/search?q="),
    ("google", "https://www.google.com/search?q="),
    ("amazon", "https://www.amazon.in/s?k="),
])
def test_search_urls(site, start):
    assert search_url(site, "a b").startswith(start)


def test_search_url_cannot_be_redirected():
    url = search_url("bing", "x\" && del C:\\ /s #")
    assert url.startswith("https://www.bing.com/search?q=") and " " not in url and '"' not in url


def test_open_in_edge_refuses_non_https():
    with pytest.raises(ValueError):
        open_in_edge("file:///C:/Windows/System32/cmd.exe")
