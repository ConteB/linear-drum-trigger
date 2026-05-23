"""Layer-1 unit oracles for ``midi_augment.recipe_matrix`` (F0-T16-pre).

Derive from F2-T1 ``T1-prep-A`` amendment (Decision Lock CEO 2026-05-23
sessione T1-prep-D). The recipe matrix is `|MIDI| × (k+1) × |engine|` with a
deterministic Fisher-Yates shuffle anchored by ``master_seed``; the manifest
in F0-T5 §5.5 stores ``master_seed`` so the ordering replays bit-per-bit.
"""
from __future__ import annotations

import pytest

from data_engineering.midi_augment.recipe_matrix import (
    RecipeMatrixEntry,
    build_recipe_matrix_entries,
)
from data_engineering.midi_augment.seed import derive_jitter_seed


@pytest.fixture
def midis() -> list[str]:
    return ["bronze/gmd/a.mid", "bronze/gmd/b.mid", "bronze/gmd/c.mid"]


@pytest.fixture
def engines_kits() -> list[tuple[str, str]]:
    return [("sfizz", "Frankensnare"), ("drumgizmo", "DRSKit")]


class TestCardinality:
    """Output length is exactly ``|MIDI| × (k+1) × |engine|``."""

    @pytest.mark.parametrize("k", [0, 1, 2, 5])
    def test_count_matches_formula(
        self,
        midis: list[str],
        engines_kits: list[tuple[str, str]],
        k: int,
    ) -> None:
        entries = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=k,
            master_seed=42,
        )
        assert len(entries) == len(midis) * (k + 1) * len(engines_kits)


class TestUniqueness:
    """No two entries are identical (no duplicate (midi, variant, engine, kit))."""

    def test_no_duplicates(
        self, midis: list[str], engines_kits: list[tuple[str, str]]
    ) -> None:
        entries = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=2,
            master_seed=42,
        )
        keys = {
            (e.source_midi_id, e.variant_idx, e.engine, e.kit) for e in entries
        }
        assert len(keys) == len(entries)


class TestDeterminism:
    """Same args → same shuffled list, byte-per-byte."""

    def test_same_master_seed_same_order(
        self, midis: list[str], engines_kits: list[tuple[str, str]]
    ) -> None:
        a = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=2,
            master_seed=42,
        )
        b = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=2,
            master_seed=42,
        )
        assert a == b

    def test_diff_master_seed_diff_order(
        self, midis: list[str], engines_kits: list[tuple[str, str]]
    ) -> None:
        a = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=2,
            master_seed=42,
        )
        b = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=2,
            master_seed=43,
        )
        # Same set of (midi, variant, engine, kit) keys, different order —
        # the jitter_seed differs across master_seeds by construction, so we
        # compare on the structural key only.
        keys_a = {(e.source_midi_id, e.variant_idx, e.engine, e.kit) for e in a}
        keys_b = {(e.source_midi_id, e.variant_idx, e.engine, e.kit) for e in b}
        assert keys_a == keys_b
        # The shuffled sequence (by structural key) must differ — the master
        # seed flips the Fisher-Yates draws.
        order_a = [(e.source_midi_id, e.variant_idx, e.engine, e.kit) for e in a]
        order_b = [(e.source_midi_id, e.variant_idx, e.engine, e.kit) for e in b]
        assert order_a != order_b


class TestSeedDerivation:
    """Each entry's ``jitter_seed`` matches the canonical formula."""

    def test_jitter_seed_matches_module_function(
        self, midis: list[str], engines_kits: list[tuple[str, str]]
    ) -> None:
        master = 17
        entries = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=2,
            master_seed=master,
        )
        for entry in entries:
            expected = derive_jitter_seed(
                master, entry.source_midi_id, entry.variant_idx
            )
            assert entry.jitter_seed == expected


class TestBaselineCoverage:
    """The baseline (variant_idx=0) appears exactly once per (midi, engine, kit)."""

    def test_baseline_coverage(
        self, midis: list[str], engines_kits: list[tuple[str, str]]
    ) -> None:
        entries = build_recipe_matrix_entries(
            source_midi_ids=midis,
            engines_kits=engines_kits,
            k_variants=2,
            master_seed=42,
        )
        baseline_keys = {
            (e.source_midi_id, e.engine, e.kit)
            for e in entries
            if e.variant_idx == 0
        }
        # One baseline per (midi, engine, kit) combination.
        assert len(baseline_keys) == len(midis) * len(engines_kits)


class TestFailLoud:
    def test_rejects_empty_midi_list(
        self, engines_kits: list[tuple[str, str]]
    ) -> None:
        with pytest.raises(ValueError, match="source_midi_ids"):
            build_recipe_matrix_entries(
                source_midi_ids=[],
                engines_kits=engines_kits,
                k_variants=2,
                master_seed=42,
            )

    def test_rejects_empty_engines(self, midis: list[str]) -> None:
        with pytest.raises(ValueError, match="engines_kits"):
            build_recipe_matrix_entries(
                source_midi_ids=midis,
                engines_kits=[],
                k_variants=2,
                master_seed=42,
            )

    def test_rejects_negative_k(
        self, midis: list[str], engines_kits: list[tuple[str, str]]
    ) -> None:
        with pytest.raises(ValueError, match="k_variants"):
            build_recipe_matrix_entries(
                source_midi_ids=midis,
                engines_kits=engines_kits,
                k_variants=-1,
                master_seed=42,
            )

    def test_rejects_negative_master_seed(
        self, midis: list[str], engines_kits: list[tuple[str, str]]
    ) -> None:
        with pytest.raises(ValueError, match="master_seed"):
            build_recipe_matrix_entries(
                source_midi_ids=midis,
                engines_kits=engines_kits,
                k_variants=2,
                master_seed=-1,
            )


class TestEntryIsHashable:
    """Frozen dataclass — usable in sets and as dict keys."""

    def test_entries_are_hashable(self) -> None:
        e = RecipeMatrixEntry(
            source_midi_id="x.mid",
            variant_idx=1,
            engine="sfizz",
            kit="Frankensnare",
            jitter_seed=42,
        )
        s = {e, e}
        assert len(s) == 1
