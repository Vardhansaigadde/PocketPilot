"""Audio decoding and grid maths (no microphone, no window, no Whisper model)."""

import io
import math
import struct
import wave

import pytest

from agent.grid import cell_center


def test_grid_corners_and_middle():
    assert cell_center(1, 1600, 1000) == (100, 100)
    assert cell_center(8, 1600, 1000) == (1500, 100)
    assert cell_center(9, 1600, 1000) == (100, 300)
    assert cell_center(40, 1600, 1000) == (1500, 900)


@pytest.mark.parametrize("bad", [0, 41, -3])
def test_grid_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        cell_center(bad, 1600, 1000)


def wav_bytes(seconds=1.0, rate=44100):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<hh", s, s)
            for s in (int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(int(seconds * rate)))
        )
        w.writeframes(frames)
    return buf.getvalue()


def test_decode_audio_resamples_to_16k_mono():
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    from agent.stt import SAMPLE_RATE, decode_audio

    samples = decode_audio(wav_bytes(1.0))
    assert samples.ndim == 1
    assert abs(len(samples) - SAMPLE_RATE) < SAMPLE_RATE * 0.05
    assert 0.1 < float(abs(samples).max()) <= 1.0


def test_decode_audio_rejects_garbage():
    pytest.importorskip("av")
    from agent.stt import decode_audio

    with pytest.raises(Exception):
        decode_audio(b"definitely not audio")
