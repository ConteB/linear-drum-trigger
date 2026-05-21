"""§6.2 — Microphone standardisation oracle.

Core module — mutation kill-rate gate >= 85 % (TESTING_DOCTRINE §3).
Contract: F0-T2a §2.3. Written test-first — awaiting F0-T4b.
"""
from __future__ import annotations

import numpy as np
import pytest

from data_engineering.gold.mic_standardize import (
    CANONICAL_SLOTS,
    MicStandardizeError,
    standardize_mics,
)
from harness import awaiting

pytestmark = pytest.mark.core


@awaiting("F0-T4b")
@pytest.mark.parametrize("n_mic", [1, 2, 4, 8])
def test_output_always_has_eight_slots(make_audio, n_mic) -> None:
    out = standardize_mics(make_audio(n_mic=n_mic, n_sample=512), n_mic)
    assert out.shape == (CANONICAL_SLOTS, 512)


@awaiting("F0-T4b")
def test_unused_slots_are_zero_filled(make_audio) -> None:
    out = standardize_mics(make_audio(n_mic=2, n_sample=256), 2)
    assert np.all(out[2:] == 0)


@awaiting("F0-T4b")
def test_no_input_channel_is_lost_or_reordered(make_audio) -> None:
    audio = make_audio(n_mic=3, n_sample=256)
    out = standardize_mics(audio, 3)
    assert np.array_equal(out[:3], audio)


@awaiting("F0-T4b")
@pytest.mark.parametrize("bad_n_mic", [0, 9, -1, 100])
def test_n_mic_out_of_range_is_rejected(make_audio, bad_n_mic) -> None:
    with pytest.raises(MicStandardizeError):
        standardize_mics(make_audio(n_mic=4, n_sample=128), bad_n_mic)


@awaiting("F0-T4b")
def test_standardisation_is_deterministic(make_audio) -> None:
    # ENGINEERING_STANDARDS §1 — same input, same output.
    audio = make_audio(n_mic=4, n_sample=256)
    assert np.array_equal(standardize_mics(audio, 4), standardize_mics(audio, 4))
