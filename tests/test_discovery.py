"""v6: the Android app finds the laptop and pins its certificate."""

import json
import socket

from server.discovery import ASK, Discovery, answer, ca_fingerprint, tag
from server.pairing import pair_url

TOKEN = "secret-token"


def test_answers_only_the_paired_phone():
    good = ASK + tag(TOKEN).encode()
    reply = json.loads(answer(good, TOKEN, "192.168.1.5", 8765, "ab12"))
    assert reply == {"app": "pocketpilot", "ip": "192.168.1.5", "port": 8765, "ca": "ab12"}
    assert answer(ASK + tag("other").encode(), TOKEN, "192.168.1.5", 8765, "ab12") is None
    assert answer(b"hello", TOKEN, "192.168.1.5", 8765, None) is None
    assert answer(ASK + b"x" * 500, TOKEN, "192.168.1.5", 8765, None) is None


def test_the_token_never_travels():
    assert TOKEN not in tag(TOKEN) and len(tag(TOKEN)) == 16


def test_real_udp_round_trip():
    d = Discovery(TOKEN, "192.168.1.5", 8765, "ab12", listen_port=0)
    assert d.start()
    port = d._sock.getsockname()[1]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(3)
        s.sendto(ASK + tag(TOKEN).encode(), ("127.0.0.1", port))
        data, _ = s.recvfrom(512)
    d.stop()
    assert json.loads(data)["ip"] == "192.168.1.5"


def test_ca_fingerprint_matches_the_certificate(tmp_path):
    import hashlib

    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    from server.certs import ensure_certs

    paths = ensure_certs(tmp_path, "192.168.1.5")
    der = x509.load_pem_x509_certificate(paths.ca_cert.read_bytes()).public_bytes(serialization.Encoding.DER)
    assert ca_fingerprint(paths.ca_cert) == hashlib.sha256(der).hexdigest()


def test_qr_link_carries_the_fingerprint_only_when_given():
    assert pair_url("1.2.3.4", 8765, "t") == "https://1.2.3.4:8765/?token=t"
    assert pair_url("1.2.3.4", 8765, "t", ca="ab") == "https://1.2.3.4:8765/?token=t&ca=ab"
