"""Audio decoding and grid maths (no microphone, no window, no Whisper model)."""

import io
import math
import struct
import wave

import pytest

from agent.grid import Layout, full_screen


def test_96_boxes_over_the_screen():
    g = full_screen(1920, 1080)
    assert g.cells == 96
    assert g.cell_center(1) == (80, 68)          # boxes are 160 x 135
    assert g.cell_center(12) == (1840, 68)
    assert g.cell_center(13) == (80, 202)
    assert g.cell_center(96) == (1840, 1012)


@pytest.mark.parametrize("bad", [0, 97, -3])
def test_grid_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        full_screen(1920, 1080).cell_center(bad)


def test_zoom_splits_one_box_into_nine():
    z = full_screen(1920, 1080).zoom(14)           # box 14 = (160, 135, 160, 135)
    assert z == Layout(160, 135, 160, 135, 3, 3) and z.cells == 9
    assert z.cell_center(1) == (187, 158)
    assert z.cell_center(5) == (240, 202)          # middle of box 14
    assert z.cell_center(9) == (293, 248)


def test_zoom_twice_gets_even_smaller():
    z = full_screen(1920, 1080).zoom(14).zoom(5)
    assert z.w == 53 and z.h == 45


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


def test_whisper_hint_knows_family_and_contact_names():
    from agent.stt import build_hint

    hint = build_hint(["Kidduuu"])
    assert "Amma" in hint and "Kidduuu" in hint and "WhatsApp" in hint
