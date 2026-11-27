"""Pairing: a secret token the phone gets by scanning a QR code.

The token is saved so a phone that added PocketPilot to its home screen keeps
working after a restart. Run with --new-token to unpair every phone.
"""

from __future__ import annotations

import secrets
import socket
from pathlib import Path

TOKEN_BYTES = 16


def make_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def check_token(given: str | None, expected: str) -> bool:
    if not given:
        return False
    return secrets.compare_digest(given.encode(), expected.encode())


def load_or_create_token(path: Path, rotate: bool = False) -> str:
    """Reuse the saved token, or make (and save) a new one."""
    if not rotate and path.exists():
        saved = path.read_text(encoding="utf-8").strip()
        if len(saved) >= 16:
            return saved
    token = make_token()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    return token


def get_lan_ip() -> str:
    """The laptop's address on the Wi-Fi, which the phone needs to reach it.

    Connecting a UDP socket sends no packets; it only asks the OS which
    network card it would use.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def pair_url(ip: str, port: int, token: str, scheme: str = "https", ca: str | None = None) -> str:
    """The QR link. `ca` = fingerprint of the laptop's own certificate authority: the Android
    app pins it, so it trusts this laptop without a warning (the browser ignores it)."""
    url = f"{scheme}://{ip}:{port}/?token={token}"
    return f"{url}&ca={ca}" if ca else url


def show_qr(url: str, png_path: Path | None = None) -> bool:
    """Print the QR in the terminal and save a PNG. Returns False if qrcode isn't installed."""
    try:
        import qrcode
    except ImportError:
        return False
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    try:
        qr.print_ascii(invert=True)
    except UnicodeEncodeError:
        pass  # old Windows consoles can't draw the blocks; the PNG still works
    if png_path is not None:
        try:
            qr.make_image().save(png_path)
        except Exception:
            return True
    return True
