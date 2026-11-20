"""HTTPS certificates made on the laptop, so the phone can use the mic.

Browsers only allow the microphone on secure (HTTPS) pages. Instead of a paid
certificate or an extra program, we make our own tiny certificate authority
(CA), like mkcert does:

- The CA is made once and kept in data/. It is *name-constrained*: it can only
  vouch for private home-network addresses and "localhost", so even if its key
  leaked it could not be used to fake a real website.
- The server certificate is signed by the CA for the laptop's current Wi-Fi IP.
  It is re-made automatically when the IP changes or it is close to expiring.
  The CA stays the same, so a phone that trusts it keeps trusting it.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_DAYS = 3650
SERVER_DAYS = 397        # browsers reject longer-lived server certificates
RENEW_BEFORE_DAYS = 30

# The only addresses the CA may ever vouch for.
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]

CA_CERT = "pocketpilot-ca.crt"
CA_KEY = "pocketpilot-ca.key"
SERVER_CERT = "server.crt"
SERVER_KEY = "server.key"


@dataclass(frozen=True)
class CertPaths:
    cert: Path      # server certificate (given to uvicorn)
    key: Path       # server private key (given to uvicorn, never served)
    ca_cert: Path   # public CA certificate (the phone may install this)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _new_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _write_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def make_ca(data_dir: Path) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    """Create and save a new name-constrained CA."""
    key = _new_key()
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "PocketPilot local CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PocketPilot (this laptop only)"),
    ])
    now = _now()
    permitted: list[x509.GeneralName] = [x509.IPAddress(n) for n in PRIVATE_NETWORKS]
    permitted.append(x509.DNSName("localhost"))
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.NameConstraints(permitted_subtrees=permitted, excluded_subtrees=None),
                       critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_key(data_dir / CA_KEY, key)
    _write_cert(data_dir / CA_CERT, cert)
    return cert, key


def load_ca(data_dir: Path) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey] | None:
    """Load the saved CA, or None if it is missing, broken or nearly expired."""
    try:
        cert = x509.load_pem_x509_certificate((data_dir / CA_CERT).read_bytes())
        key = serialization.load_pem_private_key((data_dir / CA_KEY).read_bytes(), password=None)
    except (OSError, ValueError):
        return None
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        return None
    if cert.public_key().public_numbers() != key.public_key().public_numbers():
        return None
    if cert.not_valid_after_utc - _now() < dt.timedelta(days=RENEW_BEFORE_DAYS):
        return None
    return cert, key


def make_server_cert(
    data_dir: Path, ip: str, ca_cert: x509.Certificate, ca_key: ec.EllipticCurvePrivateKey,
) -> None:
    """Create and save a server certificate for this IP, signed by the CA."""
    key = _new_key()
    now = _now()
    names: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    addr = ipaddress.ip_address(ip)
    if addr != ipaddress.ip_address("127.0.0.1"):
        names.append(x509.IPAddress(addr))
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"PocketPilot {ip}")]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                       critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(data_dir / SERVER_KEY, key)
    _write_cert(data_dir / SERVER_CERT, cert)


def needs_renewal(data_dir: Path, ip: str, ca_cert: x509.Certificate) -> bool:
    """True if the server cert is missing, not for this IP, not from this CA, or expiring."""
    try:
        cert = x509.load_pem_x509_certificate((data_dir / SERVER_CERT).read_bytes())
        if not (data_dir / SERVER_KEY).exists():
            return True
        cert.verify_directly_issued_by(ca_cert)
        ips = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value \
            .get_values_for_type(x509.IPAddress)
    except (OSError, ValueError, TypeError, InvalidSignature, x509.ExtensionNotFound):
        return True
    if ipaddress.ip_address(ip) not in ips:
        return True
    return cert.not_valid_after_utc - _now() < dt.timedelta(days=RENEW_BEFORE_DAYS)


def ensure_certs(data_dir: Path, ip: str) -> CertPaths:
    """Make sure a valid CA and a server cert for `ip` exist; create them if needed."""
    data_dir.mkdir(parents=True, exist_ok=True)
    ca = load_ca(data_dir)
    if ca is None:
        ca = make_ca(data_dir)
    ca_cert, ca_key = ca
    if needs_renewal(data_dir, ip, ca_cert):
        make_server_cert(data_dir, ip, ca_cert, ca_key)
    return CertPaths(
        cert=data_dir / SERVER_CERT,
        key=data_dir / SERVER_KEY,
        ca_cert=data_dir / CA_CERT,
    )
