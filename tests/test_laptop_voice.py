"""End-of-speech detection for the laptop mic (synthetic audio, no microphone)."""

import numpy as np
import pytest

pytest.importorskip("numpy")

from agent.laptop_voice import CHUNK, RATE, Recorder  # noqa: E402

LOUD = np.full(CHUNK, 3000, dtype=np.int16)
QUIET = np.zeros(CHUNK, dtype=np.int16)
SECOND = RATE // CHUNK   # chunks per second (12)


def feed(rec, chunks):
    for i, c in enumerate(chunks):
        if rec.add(c):
            return i + 1
    return None


def test_stops_after_a_pause():
    rec = Recorder(silence_s=0.8)
    rec.reset(noise_floor=100)
    stopped_at = feed(rec, [LOUD] * 10 + [QUIET] * 30)
    assert stopped_at == 10 + rec.silence_chunks
    audio = rec.audio()
    assert audio.dtype == np.float32 and abs(audio.max() - 3000 / 32768) < 1e-6


def test_gives_up_if_nobody_speaks():
    rec = Recorder(start_timeout_s=4)
    rec.reset(noise_floor=100)
    assert feed(rec, [QUIET] * 100) == rec.start_chunks
    assert rec.audio().size == 0


def test_long_speech_is_cut_at_max():
    rec = Recorder(max_s=8)
    rec.reset(noise_floor=100)
    assert feed(rec, [LOUD] * 200) == rec.max_chunks


def test_noisy_room_raises_the_threshold():
    rec = Recorder()
    rec.reset(noise_floor=1500)          # e.g. a fan
    hum = np.full(CHUNK, 1600, dtype=np.int16)
    assert feed(rec, [hum] * 30) is None  # hum isn't speech
    assert not rec.heard_speech
