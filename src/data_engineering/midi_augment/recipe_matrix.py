"""Recipe matrix builder — `|MIDI| × (k+1) × |engine|` with deterministic shuffle.

Implements the F2-T1 ``T1-prep-A`` amendment (Decision Lock CEO 2026-05-23,
sessione T1-prep-D): the F2-T1 render consumes a recipe matrix that pairs every
source MIDI with every engine **and** with every jitter-variant (baseline +
`k` augmented). The shuffle is deterministic — anchored by ``master_seed`` —
so the manifest in F0-T5 §5.5 can replay the exact ordering.

Public surface:

* :class:`RecipeMatrixEntry` — one (MIDI, variant, engine, kit) tuple,
  ready to be expanded into a recipe YAML by ``tools/build_recipe_matrix.py``.
* :func:`build_recipe_matrix_entries` — enumerate the matrix and shuffle it.

This module is *pure*: no I/O, no YAML, no globbing. The recipe YAML emission
lives in ``tools/build_recipe_matrix.py`` (the only tool to instantiate it).
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from .seed import derive_jitter_seed


@dataclass(frozen=True)
class RecipeMatrixEntry:
    """A single row of the F2-T1 recipe matrix.

    Attributes:
        source_midi_id: Stable identifier for the source MIDI (e.g. the
            relative path under ``bronze/gmd/``). Fed into
            :func:`derive_jitter_seed`.
        variant_idx: 0 = baseline (no jitter), 1..k = jittered branches.
        engine: ``"sfizz"`` | ``"drumgizmo"``.
        kit: The kit identifier in the roster (F0-T1b) — opaque string,
            consumed by the recipe builder.
        jitter_seed: The derived seed (bit-deterministic via :mod:`.seed`).
            Cached on the entry so the recipe YAML carries it without
            redundant re-derivation downstream.
    """

    source_midi_id: str
    variant_idx: int
    engine: str
    kit: str
    jitter_seed: int


def build_recipe_matrix_entries(
    *,
    source_midi_ids: Sequence[str],
    engines_kits: Iterable[tuple[str, str]],
    k_variants: int,
    master_seed: int,
) -> list[RecipeMatrixEntry]:
    """Enumerate and shuffle the full recipe matrix.

    Args:
        source_midi_ids: List of source MIDI identifiers (length M). Order
            matters only for replay: the same input list always yields the
            same shuffled output for a given ``master_seed``.
        engines_kits: Iterable of ``(engine, kit)`` pairs (length E). One
            entry per (engine, kit) combination — e.g. ``("sfizz",
            "Frankensnare")``, ``("drumgizmo", "DRSKit")``.
        k_variants: Number of jittered variants per source MIDI (the
            ``k = 2`` of F0-T15-pre §5 — variant_idx will run 0..k inclusive,
            so the cardinality is ``M × (k + 1) × E``).
        master_seed: The run-level seed (recipe_matrix_seed in F0-T5 §5.5).
            Anchors both the per-entry jitter seed *and* the shuffle order.

    Returns:
        List of :class:`RecipeMatrixEntry` of length ``M × (k+1) × E``,
        deterministically shuffled by ``master_seed``.

    Raises:
        ValueError: on empty inputs, ``k_variants < 0``, or
            ``master_seed < 0``.
    """
    if not source_midi_ids:
        raise ValueError("source_midi_ids: must be non-empty")
    if k_variants < 0:
        raise ValueError(f"k_variants: must be non-negative, got {k_variants}")
    if master_seed < 0:
        raise ValueError(f"master_seed: must be non-negative, got {master_seed}")

    engines_kits_list = list(engines_kits)
    if not engines_kits_list:
        raise ValueError("engines_kits: must be non-empty")

    # Enumerate in a fixed order. We *do not* sort the inputs ourselves —
    # caller controls the canonical order. We just iterate (midi, variant,
    # (engine, kit)) lexicographically so the pre-shuffle layout is
    # reproducible from the function arguments alone.
    entries: list[RecipeMatrixEntry] = []
    for source_midi_id in source_midi_ids:
        for variant_idx in range(k_variants + 1):
            jitter_seed = derive_jitter_seed(master_seed, source_midi_id, variant_idx)
            for engine, kit in engines_kits_list:
                entries.append(
                    RecipeMatrixEntry(
                        source_midi_id=source_midi_id,
                        variant_idx=variant_idx,
                        engine=engine,
                        kit=kit,
                        jitter_seed=jitter_seed,
                    )
                )

    # Deterministic Fisher-Yates shuffle anchored by ``master_seed``.
    rng = np.random.default_rng(master_seed)
    indices = np.arange(len(entries))
    rng.shuffle(indices)
    return [entries[i] for i in indices]
