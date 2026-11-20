"""Settings from `.env` (git-ignored) or environment variables. All optional.

Example .env:
    POCKETPILOT_HOME_CITY=Hyderabad
    POCKETPILOT_MODEL=qwen3:4b
    POCKETPILOT_WHISPER=base.en
    POCKETPILOT_CONTACT=https://github.com/you/pocketpilot
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def read_env_file(path: Path) -> dict[str, str]:
    """Tiny .env reader: KEY=value lines, # comments, optional quotes."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Config:
    home_city: str | None = None
    model: str = "qwen3:4b"           # voice commands: fast on CPU (reuses its instructions)
    vision_model: str = "qwen3.5:4b"  # v3 screen explainer: can see images, slower
    ollama_url: str = "http://127.0.0.1:11434"
    whisper_model: str = "base.en"
    amazon_domain: str = "www.amazon.in"
    contact: str | None = None        # your GitHub repo URL (Wikipedia asks apps for one)
    gnews_key: str | None = None      # free key from gnews.io (news)
    contacts: tuple[str, ...] = ()    # WhatsApp names you call/message, to fix mishearings
    keep_awake: str = "charging"     # charging / always / off
    cricket_key: str | None = None    # free key from cricketdata.org (cricket scores)
    cloud_fallback: bool = False      # OpenRouter (v4); stays OFF unless turned on


def load_config(env_file: Path | None = None) -> Config:
    file_vals = read_env_file(env_file) if env_file else {}

    def get(key: str, default: str | None = None) -> str | None:
        return os.environ.get(key) or file_vals.get(key) or default

    return Config(
        home_city=get("POCKETPILOT_HOME_CITY"),
        model=get("POCKETPILOT_MODEL", Config.model) or Config.model,
        vision_model=get("POCKETPILOT_VISION_MODEL", Config.vision_model) or Config.vision_model,
        ollama_url=get("POCKETPILOT_OLLAMA_URL", Config.ollama_url) or Config.ollama_url,
        whisper_model=get("POCKETPILOT_WHISPER", Config.whisper_model) or Config.whisper_model,
        amazon_domain=get("POCKETPILOT_AMAZON", Config.amazon_domain) or Config.amazon_domain,
        contact=get("POCKETPILOT_CONTACT"),
        gnews_key=get("POCKETPILOT_GNEWS_KEY"),
        keep_awake=(get("POCKETPILOT_KEEP_AWAKE", "charging") or "charging").lower(),
        contacts=tuple(n.strip() for n in (get("POCKETPILOT_CONTACTS", "") or "").split(",") if n.strip()),
        cricket_key=get("POCKETPILOT_CRICKET_KEY"),
        cloud_fallback=(get("POCKETPILOT_CLOUD_FALLBACK", "off") or "off").lower() in ("1", "on", "true", "yes"),
    )
