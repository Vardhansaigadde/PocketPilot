from server.pairing import check_token, load_or_create_token, make_token, pair_url


def test_tokens_are_long_and_unique():
    a, b = make_token(), make_token()
    assert a != b and len(a) >= 20


def test_check_token():
    t = make_token()
    assert check_token(t, t)
    assert not check_token(t + "x", t)
    assert not check_token("", t)
    assert not check_token(None, t)


def test_token_is_saved_and_reused(tmp_path):
    path = tmp_path / "data" / "token.txt"
    first = load_or_create_token(path)
    assert path.read_text() == first
    assert load_or_create_token(path) == first


def test_rotate_makes_a_new_token(tmp_path):
    path = tmp_path / "token.txt"
    first = load_or_create_token(path)
    second = load_or_create_token(path, rotate=True)
    assert second != first and path.read_text() == second


def test_pair_url_is_https_by_default():
    assert pair_url("192.168.1.5", 8765, "abc") == "https://192.168.1.5:8765/?token=abc"


def test_pair_url_plain_http():
    url = pair_url("192.168.1.5", 8765, "abc", scheme="http")
    assert url == "http://192.168.1.5:8765/?token=abc"
