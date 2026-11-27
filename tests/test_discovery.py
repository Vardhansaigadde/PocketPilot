"""v6: the Android app finds the laptop, pins its certificate, and gets what Wake-on-LAN needs."""

import json
import socket

from fastapi.testclient import TestClient

from server.discovery import ASK, Discovery, Network, answer, ca_fingerprint, network_of, tag
from server.main import create_app
from server.pairing import pair_url
from tests.test_dispatch import FakeController

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


def test_network_of_an_unknown_ip_is_empty():
    assert network_of("203.0.113.77") == Network("203.0.113.77", None, None)


def test_hello_tells_the_paired_phone_the_mac():
    net = Network("192.168.1.5", "10:5F:AD:00:00:01", "192.168.1.255")
    app = create_app(token=TOKEN, controller=FakeController(), network=net)
    with TestClient(app).websocket_connect(f"/ws?token={TOKEN}") as ws:
        hello = ws.receive_json()
    assert hello["mac"] == "10:5F:AD:00:00:01" and hello["broadcast"] == "192.168.1.255"


def test_hello_without_network_info_has_no_mac():
    app = create_app(token=TOKEN, controller=FakeController())
    with TestClient(app).websocket_connect(f"/ws?token={TOKEN}") as ws:
        assert "mac" not in ws.receive_json()
