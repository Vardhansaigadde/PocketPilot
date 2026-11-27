"""Lets the Android app find the laptop again when its Wi-Fi address changes (v6).

The app sends a UDP broadcast on the Wi-Fi:  POCKETPILOT? <tag>
where <tag> is derived from the pairing token. The laptop answers with its current
address only when the tag matches, so other people on the same Wi-Fi learn nothing,
and the token itself is never sent.

Also: the laptop's Wi-Fi MAC and broadcast address, which the app needs for its
Wake-on-LAN button, and the CA fingerprint the app pins (no "not private" warning).
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import socket
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("pocketpilot.discovery")

PORT = 8766
ASK = b"POCKETPILOT? "
MAX_PACKET = 256


def tag(token: str) -> str:
    """What the app sends instead of the token: the first 16 hex chars of SHA-256."""
    return hashlib.sha256(f"pocketpilot-discovery:{token}".encode()).hexdigest()[:16]


def ca_fingerprint(ca_cert: Path) -> str:
    """SHA-256 of the CA certificate (DER), hex. The app trusts only certificates it signed."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    cert = x509.load_pem_x509_certificate(ca_cert.read_bytes())
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


@dataclass(frozen=True)
class Network:
    ip: str
    mac: str | None          # "10:5F:AD:B6:F7:BA" of the adapter that has `ip`
    broadcast: str | None    # "192.168.1.255"


def network_of(ip: str) -> Network:
    """The MAC and broadcast address of the network card that has this IP."""
    try:
        import psutil
    except ImportError:
        return Network(ip, None, None)
    for addrs in psutil.net_if_addrs().values():
        v4 = next((a for a in addrs if a.family == socket.AF_INET and a.address == ip), None)
        if v4 is None:
            continue
        link = next((a for a in addrs if a.family == psutil.AF_LINK), None)
        mac = link.address.replace("-", ":").upper() if link and link.address else None
        broadcast = None
        if v4.netmask:
            net = ipaddress.ip_network(f"{ip}/{v4.netmask}", strict=False)
            broadcast = str(net.broadcast_address)
        return Network(ip, mac, broadcast)
    return Network(ip, None, None)


def answer(packet: bytes, token: str, ip: str, port: int, ca: str | None) -> bytes | None:
    """The reply to one discovery packet, or None to stay silent."""
    if len(packet) > MAX_PACKET or not packet.startswith(ASK):
        return None
    if packet[len(ASK):].strip().decode("ascii", "replace") != tag(token):
        return None                                   # not our phone: say nothing
    return json.dumps({"app": "pocketpilot", "ip": ip, "port": port, "ca": ca}).encode()


class Discovery:
    """A small UDP responder running in a background thread."""

    def __init__(self, token: str, ip: str, port: int, ca: str | None, listen_port: int = PORT) -> None:
        self.token, self.ip, self.port, self.ca = token, ip, port, ca
        self.listen_port = listen_port
        self._stop = threading.Event()
        self._sock: socket.socket | None = None

    def start(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.listen_port))
            sock.settimeout(1.0)
        except OSError as exc:
            log.warning("discovery off: %s", exc)
            return False
        self._sock = sock
        threading.Thread(target=self._run, name="discovery", daemon=True).start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                packet, sender = self._sock.recvfrom(MAX_PACKET + 1)
            except socket.timeout:
                continue
            except OSError:
                break
            reply = answer(packet, self.token, self.ip, self.port, self.ca)
            if reply is not None:
                try:
                    self._sock.sendto(reply, sender)
                except OSError:
                    log.debug("could not answer %s", sender)
        self._sock.close()
