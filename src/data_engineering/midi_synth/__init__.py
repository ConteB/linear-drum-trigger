"""OP-NEUROTRIGGER — MIDI synthesis layer (mixed-dataset R&D, 2026-05-23).

The Layer-B/C complement to the GMD real grooves: synthetic MIDI generators
that fill the *coverage gaps* of the GMD distribution and force the model to
attend to the spectrum instead of grid position.

Two generators:

* :func:`generate_rare_emphasis_grooves` (Layer B) — 30 grooves with
  crash/china/ride/tom over-represented 3-5× the natural GMD frequency.
* :func:`generate_chaos_grooves` (Layer C, "Machine-Gun Chaos") — 30 grooves
  with per-bus independent Poisson processes (λ ∈ [2, 15] hits/sec), blast
  beats, sub-grid onsets, uniform velocity. Doctrine: anti-shortcut learning
  (DOSSIER §3.4).

Plus the mix orchestrator:

* :func:`build_mix_dataset` — 140 GMD subset + 30 rare + 30 chaos = 200
  grooves, deterministic shuffle (``master_seed=20260524``).

All generators are pure, deterministic, and produce
``list[GrooveSpec]`` — the tuple ``(name, bpm, events)`` consumed by the
shared :func:`write_events_to_midi` helper.
"""
from __future__ import annotations

from ._writer import GrooveSpec, write_events_to_midi
from .chaos_generator import generate_chaos_grooves
from .mix_dataset import MixManifestEntry, build_mix_dataset
from .rare_emphasis import generate_rare_emphasis_grooves

__all__ = [
    "GrooveSpec",
    "MixManifestEntry",
    "build_mix_dataset",
    "generate_chaos_grooves",
    "generate_rare_emphasis_grooves",
    "write_events_to_midi",
]
