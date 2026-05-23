"""Layer C — Machine-Gun Chaos generator (mixed-dataset R&D, 2026-05-23).

DOSSIER §3.4 LOCKED concept, here implemented:

* **Per-bus independent Poisson processes** — each of the 8 logical buses
  (kick/snare/hi-hat/tom-mid/tom-floor/ride/crash-A/crash-B-misc) fires
  according to its own Poisson process with rate ``λ ∈ [2, 15] hits/sec``.
* **Sub-grid onsets** — inter-arrival times come from
  :func:`random.Random.expovariate`, so onsets land off any 16th/32nd grid
  and the model cannot exploit grid position as a shortcut.
* **Uniform velocity** — ``Uniform[40, 120]``, no natural skew.
* **Multi-hits & blast beats** — high-λ buses (≥ 10) produce dense bursts.

Doctrine: anti-shortcut learning. The chaos layer is *non-musical by
construction*: it breaks every assumption the model could learn from GMD
alone (kick-on-1, snare-on-2-4, hi-hat-grid-dependence, crash-only-on-bar-1).

Determinism: a master seed + groove index fully determines the output via
:class:`random.Random` (Python stdlib, no NumPy dependency). Same seed
⇒ same MIDI bytes.
"""
from __future__ import annotations

import random
from typing import Final

from ._writer import BUS_TO_GM_NOTES, GrooveSpec

#: Number of grooves emitted by :func:`generate_chaos_grooves`.
N_GROOVES: Final[int] = 30

#: Default master seed (Decision CEO 2026-05-23 — distinct from mix seed).
_DEFAULT_MASTER_SEED: Final[int] = 19260424

#: Poisson rate bounds (DOSSIER §3.4 LOCKED).
LAMBDA_MIN: Final[float] = 2.0
LAMBDA_MAX: Final[float] = 15.0

#: Velocity bounds for uniform sampling — wider than musical range on purpose.
VELOCITY_MIN: Final[int] = 40
VELOCITY_MAX: Final[int] = 120

#: Duration bounds (seconds). Mirrors the GMD distribution (short loops).
DURATION_S_MIN: Final[float] = 2.0
DURATION_S_MAX: Final[float] = 6.0

#: BPM bounds — the tempo carries the tick conversion, not the structure.
BPM_MIN: Final[int] = 80
BPM_MAX: Final[int] = 200

#: Ticks per beat (must match :mod:`midi_synth._writer`).
_TICKS_PER_BEAT: Final[int] = 480


def _derive_rng(master_seed: int, index: int) -> random.Random:
    """Seed a :class:`random.Random` deterministically from ``(seed, index)``.

    We use a 64-bit mix that's independent across indices (no correlation in
    the low bits) — Python ``random.Random`` accepts an arbitrary int.
    """
    # Multiply-xor mix — same effect as sha256 + truncation at far lower cost,
    # adequate for non-cryptographic determinism.
    mixed = (master_seed * 6364136223846793005 + index * 1442695040888963407) & ((1 << 64) - 1)
    return random.Random(mixed)


def _generate_bus_events(
    rng: random.Random,
    bus_id: int,
    duration_s: float,
    bpm: int,
) -> list[tuple[int, int, int]]:
    """Emit ``(abs_tick, note, velocity)`` triples for a single bus via Poisson.

    The bus' Poisson rate ``λ`` is sampled once per bus from Uniform(2, 15);
    inter-arrival times are exponential. Each hit picks one of the bus' GM
    notes uniformly (kit-driven, from :data:`BUS_TO_GM_NOTES`).
    """
    lam = rng.uniform(LAMBDA_MIN, LAMBDA_MAX)
    notes = BUS_TO_GM_NOTES[bus_id]
    ticks_per_second = _TICKS_PER_BEAT * bpm / 60.0
    out: list[tuple[int, int, int]] = []
    t = 0.0
    # The exponential draw is the inter-arrival; cumulative-sum gives onset.
    while True:
        dt = rng.expovariate(lam)
        t += dt
        if t >= duration_s:
            break
        abs_tick = int(round(t * ticks_per_second))
        note = rng.choice(notes)
        velocity = rng.randint(VELOCITY_MIN, VELOCITY_MAX)
        out.append((abs_tick, note, velocity))
    return out


def _generate_chaos_groove(*, index: int, master_seed: int) -> GrooveSpec:
    """Build one chaos groove deterministically from ``(seed, index)``."""
    rng = _derive_rng(master_seed, index)
    # Pick groove-wide BPM + duration once, before per-bus draws.
    bpm = rng.randint(BPM_MIN, BPM_MAX)
    duration_s = rng.uniform(DURATION_S_MIN, DURATION_S_MAX)

    events: list[tuple[int, int, int]] = []
    for bus_id in range(1, 9):
        events.extend(_generate_bus_events(rng, bus_id, duration_s, bpm))

    # Sort chronologically — _writer also sorts, but defensive deterministic
    # ordering is part of the contract (same seed ⇒ same byte output).
    events.sort(key=lambda e: (e[0], e[1], e[2]))
    name = f"chaos-bpm{bpm}-dur{duration_s:.2f}-idx{index:02d}"
    return GrooveSpec(name=name, bpm=bpm, events=events)


def generate_chaos_grooves(
    *,
    n: int = N_GROOVES,
    master_seed: int = _DEFAULT_MASTER_SEED,
) -> list[GrooveSpec]:
    """Return ``n`` deterministic Machine-Gun Chaos grooves (Layer C).

    Parameters
    ----------
    n
        Number of grooves. Default 30. Must satisfy ``0 < n <= 30``.
    master_seed
        Seed for the underlying :class:`random.Random` mixer. Default
        ``19260424``. Same seed + same index ⇒ byte-identical output.

    Returns
    -------
    list[GrooveSpec]
        Grooves indexed ``[0, n)``.
    """
    if not 0 < n <= N_GROOVES:
        raise ValueError(f"n={n} outside (0, {N_GROOVES}]")
    return [
        _generate_chaos_groove(index=i, master_seed=master_seed) for i in range(n)
    ]
