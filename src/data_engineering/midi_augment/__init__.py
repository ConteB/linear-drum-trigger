"""OP-NEUROTRIGGER — MIDI augmentation pipeline (F0-T16-pre).

Pre-render augmentation applied to the MIDI sources of the Gold layer, *before*
synthesis. The parameters are LOCKED by Decision Lock CEO 2026-05-23 in
``docs/methodology/F0-T15-pre_MIDI_AUGMENTATION_SPEC.md`` (and mirrored in
DOSSIER §3.1).

Public surface:

* :func:`apply_midi_jitter` — full pipeline (time → flam → velocity → ghost →
  gain → component) for a single ``(source_midi, variant_idx)`` pair.
* :func:`derive_jitter_seed` — bit-deterministic seed derivation
  ``sha256(master_seed ‖ source_midi_id ‖ variant_idx)``.
* :func:`build_recipe_matrix_entries` — `|MIDI| × (k+1) × |engine|` recipe
  matrix with deterministic pre-shuffle (F0-T5 §5.5).
* :class:`MidiAugmentError` — raised on malformed MIDI / invalid parameters.

Design notes:

* Variant 0 is the **baseline** (identity transform): the jittered branches
  augment, they do not replace.
* The jitter parameters are *module-level constants* derived from
  ``F0-T15-pre``; the recipe carries only the ``variant_idx`` and the derived
  ``seed`` — the curves themselves are not per-recipe tunables.
"""
from __future__ import annotations

from .jitter import (
    MidiAugmentError,
    apply_midi_jitter,
)
from .recipe_matrix import RecipeMatrixEntry, build_recipe_matrix_entries
from .seed import derive_jitter_seed

__all__ = [
    "MidiAugmentError",
    "RecipeMatrixEntry",
    "apply_midi_jitter",
    "build_recipe_matrix_entries",
    "derive_jitter_seed",
]
