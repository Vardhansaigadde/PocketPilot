"""Speech-to-text with faster-whisper, on the CPU, fully offline after the first download.

The model (base.en ≈ 145 MB) downloads automatically the first time and is
cached. It loads in the background at startup so the first command is quick.
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


def build_hint(names: tuple[str, ...] | list[str] = ()) -> str:
    """The hint plus WhatsApp-style sentences with the user's contact names."""
    people = [n for n in (*names, *FAMILY) if n][:20]
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


class WhisperTranscriber:
    def __init__(self, model_size: str = "base.en", threads: int = 4,
                 names: tuple[str, ...] | list[str] = ()) -> None:
        self.model_size = model_size
        self.threads = threads
        self.hint = build_hint(names)
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel  # heavy import, done once

                log.info("loading Whisper %s (first time downloads it)…", self.model_size)
                self._model = WhisperModel(
                    self.model_size, device="cpu", compute_type="int8", cpu_threads=self.threads,
                )
                log.info("Whisper ready")
            return self._model

    def preload(self) -> None:
        """Load the model in a background thread so the first command isn't slow."""
        threading.Thread(target=self._safe_load, name="whisper-load", daemon=True).start()

    def _safe_load(self) -> None:
        try:
            self._load()
        except Exception:
            log.exception("could not load Whisper")

    def transcribe(self, audio: bytes | Any) -> str:
        """`audio` = a recorded file (webm/ogg/mp4/wav bytes from the phone) or a
        16 kHz mono float32 numpy array (from the laptop mic)."""
        model = self._load()
        source = decode_audio(audio) if isinstance(audio, (bytes, bytearray)) else audio
        if len(source) < SAMPLE_RATE // 4:      # under a quarter second: nothing said
            return ""
        language = "en" if self.model_size.endswith(".en") else None
        segments, _info = model.transcribe(
            source, language=language, beam_size=1, vad_filter=True,
            initial_prompt=self.hint, condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()
