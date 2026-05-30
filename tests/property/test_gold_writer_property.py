"""§6.2 — Gold-tensor writer property-based oracle (Layer 2).

The flat-25 layout and the frame-count formula must hold across the whole
input domain, not just spot values (TESTING_DOCTRINE §2). Awaiting F0-T2d.
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from data_engineering.gold.gold_writer import R_TARGET_HZ, bus_columns, n_frames

pytestmark = [pytest.mark.critical, pytest.mark.property]

_duration = st.floats(min_value=0.0, max_value=600.0, allow_nan=False, allow_infinity=False)


@given(_duration)
def test_n_frames_equals_ceil_formula(duration_s) -> None:
    # F0-T2a §3.4 — n_frame = ceil(duration_s * R_target).
    assert n_frames(duration_s) == math.ceil(duration_s * R_TARGET_HZ)


@given(_duration, _duration)
def test_n_frames_is_monotonic_in_duration(a, b) -> None:
    lo, hi = sorted((a, b))
    assert n_frames(lo) <= n_frames(hi)


@given(st.integers(min_value=0, max_value=8))
def test_bus_columns_partition_the_first_27_columns(bus) -> None:
    # F0-T19 §7b — channels tile columns 0..26 in contiguous triples.
    cols = bus_columns(bus)
    assert cols == (3 * bus, 3 * bus + 1, 3 * bus + 2)
    assert all(0 <= c < 27 for c in cols)
