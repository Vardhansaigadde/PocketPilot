"""Laptop microphone: say "Hey Jarvis", then your command.

Flow (all in one background thread):
  listen for the wake word (openWakeWord, tiny, CPU)
  → short beep → record until you stop talking (or 8 s)
  → same assistant as the phone → reply on the phone + spoken on the laptop.

Audio is only kept in memory for the one command and never saved.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable

import numpy as np

from .assistant import Assistant

log = logging.getLogger("pocketpilot.laptop_voice")

RATE = 16_000
CHUNK = 1280                 # 80 ms, the size openWakeWord expects
WAKE_MODEL = "hey_jarvis"    # swap for a custom "hey_pilot" model later
WAKE_THRESHOLD = 0.5


def rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2))) if chunk.size else 0.0


class Recorder:
    """Collects audio after the wake word and decides when the user has finished."""

    def __init__(self, silence_s: float = 0.8, max_s: float = 8.0, start_timeout_s: float = 4.0,
                 min_level: float = 300.0) -> None:
        self.silence_chunks = int(silence_s * RATE / CHUNK)
        self.max_chunks = int(max_s * RATE / CHUNK)
        self.start_chunks = int(start_timeout_s * RATE / CHUNK)
        self.min_level = min_level
        self.reset(0.0)

    def reset(self, noise_floor: float) -> None:
        self.threshold = max(self.min_level, noise_floor * 3)
        self.chunks: list[np.ndarray] = []
        self.heard_speech = False
        self.quiet = 0

    def add(self, chunk: np.ndarray) -> bool:
        """Add 80 ms of audio. Returns True when recording should stop."""
        self.chunks.append(chunk)
        if rms(chunk) >= self.threshold:
            self.heard_speech = True
            self.quiet = 0
        else:
            self.quiet += 1
        n = len(self.chunks)
        if not self.heard_speech:
            return n >= self.start_chunks          # nobody spoke: give up
        return self.quiet >= self.silence_chunks or n >= self.max_chunks

    def audio(self) -> np.ndarray:
        """Recorded speech as float32 16 kHz (empty if nobody spoke)."""
        if not self.heard_speech or not self.chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.chunks).astype(np.float32) / 32768.0


class LaptopVoice:
    def __init__(
        self,
        assistant: Assistant,
        broadcast: Callable[[list[dict]], None],
        speak_replies: bool = True,
    ) -> None:
        self.assistant = assistant
        self.broadcast = broadcast
        self.speak_replies = speak_replies
        self._audio: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_safe, name="laptop-voice", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # -- background thread -----------------------------------------------------------
    def _run_safe(self) -> None:
        try:
            self._run()
        except Exception:
            log.exception("laptop mic stopped working; phone voice still works")

    def _on_audio(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        try:
            self._audio.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass  # busy processing a command; dropping old audio is fine

    def _drain(self) -> None:
        while True:
            try:
                self._audio.get_nowait()
            except queue.Empty:
                return

    def _run(self) -> None:
        import openwakeword.utils
        import sounddevice as sd
        from openwakeword.model import Model

        openwakeword.utils.download_models([WAKE_MODEL])   # once, ~5 MB, then cached
        wake = Model(wakeword_models=[WAKE_MODEL], inference_framework="onnx")
        speaker = _Speaker() if self.speak_replies else None
        rec = Recorder()
        noise = 200.0
        recording = False

        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK,
                            callback=self._on_audio):
            log.info('laptop mic on: say "Hey Jarvis" then a command')
            while not self._stop.is_set():
                try:
                    chunk = self._audio.get(timeout=0.5)
                except queue.Empty:
                    continue
                if not recording:
                    level = rms(chunk)
                    noise = 0.95 * noise + 0.05 * level     # slowly track background noise
                    if wake.predict(chunk).get(WAKE_MODEL, 0.0) >= WAKE_THRESHOLD:
                        wake.reset()
                        _beep()
                        self.broadcast([{"t": "listening", "on": True}])
                        rec.reset(noise)
                        recording = True
                    continue
                if not rec.add(chunk):
                    continue
                recording = False
                self.broadcast([{"t": "listening", "on": False}])
                audio = rec.audio()
                if audio.size == 0:
                    continue
                self.broadcast([{"t": "busy", "on": True}])
                messages = self.assistant.handle_audio(audio)
                self.broadcast([*messages, {"t": "busy", "on": False}])
                if speaker is not None:
                    for m in messages:
                        if m.get("t") == "reply":
                            speaker.say(m["text"])
                self._drain()        # ignore what the mic heard while we were busy/talking
                wake.reset()


def _beep() -> None:
    try:
        import winsound

        winsound.Beep(880, 120)
    except Exception:  # pragma: no cover - not Windows / no sound
        pass


class _Speaker:
    """Windows' built-in voices via pyttsx3 (offline, free)."""

    def __init__(self) -> None:
        try:
            import pyttsx3

            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", 175)
        except Exception:
            log.exception("text-to-speech unavailable")
            self.engine = None

    def say(self, text: str) -> None:
        if self.engine is None:
            return
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception:
            log.exception("could not speak")
