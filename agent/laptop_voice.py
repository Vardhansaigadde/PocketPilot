"""Laptop microphone: say the wake word ("Hey Jarvis" by default), then your command.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .assistant import Assistant

log = logging.getLogger("pocketpilot.laptop_voice")

RATE = 16_000
CHUNK = 1280                 # 80 ms, the size openWakeWord expects
WAKE_MODEL = "hey_jarvis"    # default; POCKETPILOT_WAKE_WORD picks another
# Wake words openWakeWord can download ready-made. Anything else must be a trained .onnx file.
BUILT_IN_WAKE_WORDS = ("hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy")


@dataclass(frozen=True)
class WakeWord:
    load: str        # what openWakeWord loads: a built-in name, or the path of a .onnx model
    key: str         # the name its predictions come back under
    spoken: str      # what to say: "Hey Jarvis", "Hey Pilot"
    built_in: bool


def wake_word(setting: str | None, data_dir: Path | None = None) -> WakeWord:
    """POCKETPILOT_WAKE_WORD -> what to load. 'hey_jarvis' (default), 'alexa', ... or a custom
    model file such as 'hey_pilot.onnx' (looked for in data/), trained with openWakeWord."""
    name = (setting or WAKE_MODEL).strip()
    if name.lower().endswith(".onnx"):
        path = Path(name)
        if not path.is_absolute() and data_dir is not None and not path.exists():
            path = data_dir / path
        if not path.exists():
            raise FileNotFoundError(f"wake word model {name} not found (put it in data/)")
        stem = path.stem
        return WakeWord(str(path), stem, _spoken(stem), built_in=False)
    if name.lower() not in BUILT_IN_WAKE_WORDS:
        raise ValueError(f"unknown wake word {name!r}: use one of {', '.join(BUILT_IN_WAKE_WORDS)} "
                         "or a trained .onnx file")
    return WakeWord(name.lower(), name.lower(), _spoken(name), built_in=True)


def _spoken(stem: str) -> str:
    """'hey_pilot_v0.1' -> 'Hey Pilot'."""
    words = [w for w in stem.replace("-", "_").split("_") if w and not w[0].isdigit() and not w.startswith("v0")]
    return " ".join(w.capitalize() for w in words) or stem
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
        wake: WakeWord | None = None,
    ) -> None:
        self.wake = wake or wake_word(None)
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

        if self.wake.built_in:
            openwakeword.utils.download_models([self.wake.load])   # once, ~5 MB, then cached
        else:
            openwakeword.utils.download_models([])                 # only the shared audio models
        wake = Model(wakeword_models=[self.wake.load], inference_framework="onnx")
        speaker = _Speaker() if self.speak_replies else None
        rec = Recorder()
        noise = 200.0
        recording = False

        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK,
                            callback=self._on_audio):
            log.info('laptop mic on: say "%s" then a command', self.wake.spoken)
            while not self._stop.is_set():
                try:
                    chunk = self._audio.get(timeout=0.5)
                except queue.Empty:
                    continue
                if not recording:
                    level = rms(chunk)
                    noise = 0.95 * noise + 0.05 * level     # slowly track background noise
                    if _score(wake.predict(chunk), self.wake.key) >= WAKE_THRESHOLD:
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
                messages = self.assistant.handle_audio(audio, source="laptop mic")
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


def _score(scores: dict, key: str) -> float:
    """openWakeWord names results after the model ("hey_jarvis_v0.1" for "hey_jarvis")."""
    if key in scores:
        return float(scores[key])
    return max((float(v) for k, v in scores.items() if k.startswith(key)), default=0.0)
