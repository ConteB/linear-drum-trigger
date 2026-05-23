"""Layer-1 unit oracles for ``midi_augment.seed`` (F0-T16-pre).

Derive from F0-T15-pre §4.1 — ``seed = sha256(master_seed ‖ source_midi_id ‖
variant_idx)[:8]``. The oracle pins down: (a) bit-determinism (same inputs ->
same seed, across runs), (b) sensitivity (any input change flips the seed
with overwhelming probability), (c) the value range (non-negative 64-bit),
(d) fail-loud on invalid inputs.
"""
from __future__ import annotations

import pytest

from data_engineering.midi_augment.seed import derive_jitter_seed


class TestDeriveJitterSeedDeterminism:
    """Same inputs -> same seed, every time."""

    def test_repeated_call_is_identical(self) -> None:
        s1 = derive_jitter_seed(42, "bronze/gmd/foo.mid", 1)
        s2 = derive_jitter_seed(42, "bronze/gmd/foo.mid", 1)
        assert s1 == s2

    def test_baseline_variant_has_its_own_seed(self) -> None:
        # variant 0 (baseline) MUST still derive a real seed — the pipeline
        # walks the same code path on the baseline branch and consumes the
        # RNG for the round-trip invariant. A "skip RNG for variant 0"
        # shortcut would corrupt replay.
        s_baseline = derive_jitter_seed(42, "bronze/gmd/foo.mid", 0)
        s_jittered = derive_jitter_seed(42, "bronze/gmd/foo.mid", 1)
        assert s_baseline != s_jittered


class TestDeriveJitterSeedSensitivity:
    """Any input change flips the seed (collision prob ~ 2⁻⁶⁴)."""

    def test_master_seed_change_flips_output(self) -> None:
        s_a = derive_jitter_seed(42, "bronze/gmd/foo.mid", 1)
        s_b = derive_jitter_seed(43, "bronze/gmd/foo.mid", 1)
        assert s_a != s_b

    def test_source_midi_id_change_flips_output(self) -> None:
        s_a = derive_jitter_seed(42, "bronze/gmd/foo.mid", 1)
        s_b = derive_jitter_seed(42, "bronze/gmd/bar.mid", 1)
        assert s_a != s_b

    def test_variant_idx_change_flips_output(self) -> None:
        s_a = derive_jitter_seed(42, "bronze/gmd/foo.mid", 1)
        s_b = derive_jitter_seed(42, "bronze/gmd/foo.mid", 2)
        assert s_a != s_b


class TestDeriveJitterSeedRange:
    """Output fits ``numpy.random.default_rng`` (non-negative 64-bit)."""

    def test_output_is_non_negative(self) -> None:
        s = derive_jitter_seed(0, "x", 0)
        assert s >= 0

    def test_output_fits_uint64(self) -> None:
        s = derive_jitter_seed(2**100, "any-id-string", 7)
        assert 0 <= s < 2**64

    @pytest.mark.parametrize("master_seed", [0, 1, 42, 999_999, 2**63])
    @pytest.mark.parametrize("variant_idx", [0, 1, 2, 7, 64])
    def test_smoke_range_under_many_inputs(
        self, master_seed: int, variant_idx: int
    ) -> None:
        s = derive_jitter_seed(master_seed, "id", variant_idx)
        assert 0 <= s < 2**64


class TestDeriveJitterSeedFailLoud:
    """Reject every malformed argument — no silent zero."""

    def test_rejects_negative_master_seed(self) -> None:
        with pytest.raises(ValueError, match="master_seed"):
            derive_jitter_seed(-1, "x", 0)

    def test_rejects_negative_variant_idx(self) -> None:
        with pytest.raises(ValueError, match="variant_idx"):
            derive_jitter_seed(0, "x", -1)

    def test_rejects_empty_source_midi_id(self) -> None:
        with pytest.raises(ValueError, match="source_midi_id"):
            derive_jitter_seed(0, "", 0)
