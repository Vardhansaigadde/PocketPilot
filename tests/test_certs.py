"""Checks for the home-made HTTPS certificates. Skipped if cryptography isn't installed."""

import ipaddress

import pytest

pytest.importorskip("cryptography")

from cryptography import x509  # noqa: E402

from server.certs import ensure_certs  # noqa: E402

IP = "192.168.1.5"


def load(path):
    return x509.load_pem_x509_certificate(path.read_bytes())


def san_ips(cert):
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return san.get_values_for_type(x509.IPAddress), san.get_values_for_type(x509.DNSName)


def test_files_are_created(tmp_path):
    paths = ensure_certs(tmp_path, IP)
    for p in (paths.cert, paths.key, paths.ca_cert, tmp_path / "pocketpilot-ca.key"):
        assert p.exists() and p.stat().st_size > 0


def test_server_cert_covers_ip_and_localhost(tmp_path):
    paths = ensure_certs(tmp_path, IP)
    cert = load(paths.cert)
    ips, dns = san_ips(cert)
    assert ipaddress.ip_address(IP) in ips
    assert ipaddress.ip_address("127.0.0.1") in ips
    assert "localhost" in dns
    cert.verify_directly_issued_by(load(paths.ca_cert))  # raises if not signed by our CA


def test_ca_is_name_constrained_to_private_networks(tmp_path):
    ca = load(ensure_certs(tmp_path, IP).ca_cert)
    ext = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert ext.critical
    permitted = ext.value.permitted_subtrees
    nets = [n.value for n in permitted if isinstance(n, x509.IPAddress)]
    assert all(net.is_private for net in nets)
    assert ipaddress.ip_network("192.168.0.0/16") in nets
    assert [n.value for n in permitted if isinstance(n, x509.DNSName)] == ["localhost"]
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca


def test_second_run_reuses_everything(tmp_path):
    first = ensure_certs(tmp_path, IP)
    ca_bytes, cert_bytes = first.ca_cert.read_bytes(), first.cert.read_bytes()
    second = ensure_certs(tmp_path, IP)
    assert second.ca_cert.read_bytes() == ca_bytes
    assert second.cert.read_bytes() == cert_bytes


def test_new_ip_remakes_server_cert_but_keeps_ca(tmp_path):
    first = ensure_certs(tmp_path, IP)
    ca_bytes, cert_bytes = first.ca_cert.read_bytes(), first.cert.read_bytes()
    second = ensure_certs(tmp_path, "10.0.0.7")
    assert second.ca_cert.read_bytes() == ca_bytes      # phone keeps trusting it
    assert second.cert.read_bytes() != cert_bytes
    ips, _ = san_ips(load(second.cert))
    assert ipaddress.ip_address("10.0.0.7") in ips


def test_broken_server_cert_is_replaced(tmp_path):
    paths = ensure_certs(tmp_path, IP)
    paths.cert.write_text("not a certificate")
    ensure_certs(tmp_path, IP)
    assert ipaddress.ip_address(IP) in san_ips(load(paths.cert))[0]
