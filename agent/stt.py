"""Speech-to-text with faster-whisper, on the CPU, fully offline after the first download.

The model (base.en ≈ 145 MB) downloads automatically the first time and is
cached. It loads in the background at startup so the first command is quick.

Telugu (v5) uses a second model, a Telugu-trained Whisper-small (≈ 250 MB,
Apache-2.0), loaded the first time Telugu is used.
"""

from __future__ import annotations

import io
import logging
import threading
from typing import Any

log = logging.getLogger("pocketpilot.stt")

# Nudges Whisper towards the words PocketPilot expects.
HINT = ("Open Notepad. Scroll down. Volume up. Click 14. Show grid. "
        "Weather in Hyderabad. Search YouTube for songs. Close the window.")

# Family names Whisper doesn't know ("Amma" came out as "a month", "Amal", "your mom").
FAMILY = ("Amma", "Nanna", "Appa", "Akka", "Anna", "Chelli", "Thammudu", "Ammamma", "Thatha",
          "Mama", "Atta", "Babai", "Pinni")


# Words Whisper should prefer when it isn't sure (it wrote "grid hub" for GitHub).
HOTWORDS = "WhatsApp GitHub Spotify YouTube Notepad Edge Chrome ChatGPT CodeChef Amma Nanna Akka"
MAX_HINT_NAMES = 25


def build_hint(names: tuple[str, ...] | list[str] = ()) -> str:
    """The hint plus WhatsApp-style sentences with the user's contact names."""
    people = list(dict.fromkeys(n for n in (*names, *FAMILY) if n))[:MAX_HINT_NAMES]
    return HINT + " Call " + ", ".join(people) + " on WhatsApp. Message Amma that I'm coming."


SAMPLE_RATE = 16_000
MAX_SECONDS = 20


def decode_audio(data: bytes) -> Any:
    """Any recorded audio file (bytes) -> 16 kHz mono float32 numpy array.

    Done here with PyAV directly (instead of faster-whisper's helper) so it keeps
    working across PyAV versions.
    """
    import av
    import numpy as np

    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    parts: list[Any] = []
    total = 0
    with av.open(io.BytesIO(bytes(data)), mode="r") as container:
        if not container.streams.audio:
            return np.zeros(0, dtype=np.float32)
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                arr = out.to_ndarray().reshape(-1)
                parts.append(arr)
                total += arr.size
            if total > SAMPLE_RATE * MAX_SECONDS:
                break
        for out in resampler.resample(None):   # flush
            parts.append(out.to_ndarray().reshape(-1))
    if not parts:
        return np.zeros(0, dtype=np.float32)
    return (np.concatenate(parts).astype(np.float32) / 32768.0)[: SAMPLE_RATE * MAX_SECONDS]


TELUGU_MODEL = "ukta-app/whisper-telugu-ct2"


class WhisperTranscriber:
    def __init__(self, model_size: str = "base.en", threads: int = 4,
                 names: tuple[str, ...] | list[str] = (),
                 telugu_model: str = TELUGU_MODEL, known: Any = None) -> None:
        self.model_size = model_size
        self.names = tuple(names)
        self.known = known         # names.KnownNames: WhatsApp chat names seen so far
        self.telugu_model = telugu_model
        self.threads = threads
        self.hint = build_hint(names)
        self._models: dict[str, Any] = {}
        self._lock = threading.Lock()

    def _load(self, lang: str = "en") -> Any:
        name = self.telugu_model if lang == "te" else self.model_size
        with self._lock:
            if name not in self._models:
                from faster_whisper import WhisperModel  # heavy import, done once

                log.info("loading Whisper %s (first time downloads it)…", name)
                self._models[name] = WhisperModel(
                    name, device="cpu", compute_type="int8", cpu_threads=self.threads,
                )
                log.info("Whisper %s ready", name)
            return self._models[name]

    def preload(self) -> None:
        """Load the model in a background thread so the first command isn't slow."""
        threading.Thread(target=self._safe_load, name="whisper-load", daemon=True).start()

    def _safe_load(self) -> None:
        try:
            self._load()
        except Exception:
            log.exception("could not load Whisper")

    def transcribe(self, audio: bytes | Any, lang: str = "en") -> str:
        """`audio` = a recorded file (webm/ogg/mp4/wav bytes from the phone) or a
        16 kHz mono float32 numpy array (from the laptop mic). `lang` = "en" or "te"."""
        model = self._load(lang)
        source = decode_audio(audio) if isinstance(audio, (bytes, bytearray)) else audio
        if len(source) < SAMPLE_RATE // 4:      # under a quarter second: nothing said
            return ""
        if lang == "te":
            language, hint = "te", None         # the English hint would pull it to English
        else:
            language = "en" if self.model_size.endswith(".en") else None
            hint = self.current_hint()
        extra = {"hotwords": self.hotwords()} if lang != "te" else {}
        segments, _info = model.transcribe(
            source, language=language, beam_size=1, vad_filter=True,
            initial_prompt=hint, condition_on_previous_text=False, **extra,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def learned(self) -> list[str]:
        """Chat names seen in WhatsApp (without emoji), most recent first."""
        try:
            return self.known.plain_names()[:MAX_HINT_NAMES] if self.known is not None else []
        except Exception:  # hints must never break speech-to-text
            return []

    def current_hint(self) -> str:
        """The hint with your contact names: from .env first, then the chats WhatsApp showed."""
        return build_hint([*self.names, *self.learned()])

    def hotwords(self) -> str:
        return " ".join(dict.fromkeys([*HOTWORDS.split(), *self.names, *self.learned()[:15]]))
