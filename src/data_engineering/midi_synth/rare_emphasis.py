"""Layer B — rare-emphasis grooves (mixed-dataset R&D, 2026-05-23).

Counterweights the GMD distribution: GMD has crash/china/ride/tom under-
represented relative to kick/snare/hihat, so the model risks learning the
*frequent* events better than the *informative* ones. This module emits 50
deterministic grooves where rare bus voicings are foregrounded — 3-5× the
natural GMD frequency, per the CEO directive (2026-05-23, fine giornata,
extended 2026-05-24 by F0-T4c B6c Decision Lock: 30 → 50 grooves).

Five families, ten grooves each (5 BPM tiers × 2 bar lengths):

* ``crash_led`` — crash on every downbeat (vs only bar-1 in GMD).
* ``china_led`` — china punctuating offbeats (china rare in GMD).
* ``ride_led`` — rock-tempo ride patterns (ride mostly jazz in GMD).
* ``tom_fill_heavy`` — tom fills every 2 bars (vs only the final fill).
* ``splash_bell`` — splash + ride-bell accents.

All groove events go through :mod:`midi_augment.jitter` downstream (k=2 +
baseline) — this module emits the *clean* baseline only.
"""
from __future__ import annotations

from collections.abc import Callable

from ._writer import (
    CHINA,
    CRASH_1,
    CRASH_2,
    HH_CLOSED,
    HH_OPEN,
    HH_PEDAL,
    HI_MID_TOM,
    HIGH_FLOOR_TOM,
    HIGH_TOM,
    KICK,
    LOW_FLOOR_TOM,
    LOW_MID_TOM,
    LOW_TOM,
    RIDE,
    RIDE_BELL,
    SNARE,
    SPLASH,
    TICKS_PER_BEAT,
    GrooveSpec,
)

#: BPM tiers per family — five tiers (80/100/120/140/160) × 2 bar lengths = 10
#: grooves per family. F0-T4c B6c amendment (Decision Lock CEO 2026-05-24):
#: était 3 tiers × 2 bars = 6 grooves per family (30 total) — extended to
#: foreground the rare cymbals across more BPM contexts.
_BPM_TIERS: tuple[int, ...] = (80, 100, 120, 140, 160)
_BARS_OPTIONS: tuple[int, ...] = (2, 3)

#: Number of grooves emitted per family — derived from the cartesian product.
_GROOVES_PER_FAMILY: int = len(_BPM_TIERS) * len(_BARS_OPTIONS)

#: Total grooves emitted by :func:`generate_rare_emphasis_grooves`
#: (5 families × 10 grooves/family = 50). F0-T4c B6c.
N_GROOVES: int = 50


_GroovePattern = Callable[[int], list[tuple[int, int, int]]]


# ----------------------------------------------------------------------------
# Family generators
# ----------------------------------------------------------------------------


def _crash_led(bars: int) -> list[tuple[int, int, int]]:
    """Crash on every downbeat, kick on 1+3, snare on 2+4, eighth hi-hat."""
    eighth = TICKS_PER_BEAT // 2
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * TICKS_PER_BEAT
        # Crash on every downbeat — the rare-emphasis hook.
        out.append((bt, CRASH_1 if bar % 2 == 0 else CRASH_2, 115))
        # Kick on 1 + 3.
        out.append((bt + 0, KICK, 102))
        out.append((bt + 2 * TICKS_PER_BEAT, KICK, 96))
        # Snare on 2 + 4.
        out.append((bt + 1 * TICKS_PER_BEAT, SNARE, 104))
        out.append((bt + 3 * TICKS_PER_BEAT, SNARE, 104))
        # Eighth hi-hat closed (low velocity — crash dominates).
        for step in range(8):
            out.append((bt + step * eighth, HH_CLOSED, 55 + (step % 3) * 6))
    return out


def _china_led(bars: int) -> list[tuple[int, int, int]]:
    """China on each upbeat — replaces the hi-hat as time-keeper."""
    eighth = TICKS_PER_BEAT // 2
    sixteenth = TICKS_PER_BEAT // 4
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * TICKS_PER_BEAT
        # Kick on 1, 2-and, 3.
        out.append((bt, KICK, 100))
        out.append((bt + 1 * TICKS_PER_BEAT + eighth, KICK, 88))
        out.append((bt + 2 * TICKS_PER_BEAT, KICK, 95))
        # Snare on 2 + 4.
        out.append((bt + 1 * TICKS_PER_BEAT, SNARE, 108))
        out.append((bt + 3 * TICKS_PER_BEAT, SNARE, 108))
        # China on every upbeat (the +).
        for step in range(4):
            out.append((bt + step * TICKS_PER_BEAT + eighth, CHINA, 95))
        # Sparse hi-hat closed on downbeats only.
        for step in range(4):
            out.append((bt + step * TICKS_PER_BEAT, HH_CLOSED, 70))
        # Hi-hat foot on 1, 3 (foot ostinato accent).
        out.append((bt, HH_PEDAL, 50))
        out.append((bt + 2 * TICKS_PER_BEAT, HH_PEDAL, 50))
        # Occasional ghost snare 4-e to break monotony.
        if bar % 2 == 1:
            out.append((bt + 3 * TICKS_PER_BEAT + sixteenth, SNARE, 30))
    return out


def _ride_led(bars: int) -> list[tuple[int, int, int]]:
    """Rock-tempo ride pattern — ride on eighth notes (vs jazz triplet)."""
    eighth = TICKS_PER_BEAT // 2
    sixteenth = TICKS_PER_BEAT // 4
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * TICKS_PER_BEAT
        # Kick on 1, 3.
        out.append((bt, KICK, 100))
        out.append((bt + 2 * TICKS_PER_BEAT, KICK, 96))
        # Snare on 2, 4.
        out.append((bt + 1 * TICKS_PER_BEAT, SNARE, 105))
        out.append((bt + 3 * TICKS_PER_BEAT, SNARE, 105))
        # Ride on every eighth — the rare-emphasis hook.
        for step in range(8):
            vel = 80 if step % 2 == 0 else 60
            out.append((bt + step * eighth, RIDE, vel))
        # Bell accents on beats 1, 3.
        out.append((bt, RIDE_BELL, 95))
        out.append((bt + 2 * TICKS_PER_BEAT, RIDE_BELL, 90))
        # Sparse hi-hat foot on +.
        for step in range(4):
            out.append((bt + step * TICKS_PER_BEAT + eighth, HH_PEDAL, 45))
        # Ghost snare 16th before downbeat in odd bars.
        if bar % 2 == 1:
            out.append((bt + 3 * TICKS_PER_BEAT + 3 * sixteenth, SNARE, 28))
    return out


def _tom_fill_heavy(bars: int) -> list[tuple[int, int, int]]:
    """Tom fill on the last beat of *every* bar (vs only the final bar)."""
    eighth = TICKS_PER_BEAT // 2
    sixteenth = TICKS_PER_BEAT // 4
    out: list[tuple[int, int, int]] = []
    toms = (HIGH_TOM, HI_MID_TOM, LOW_MID_TOM, LOW_TOM, HIGH_FLOOR_TOM, LOW_FLOOR_TOM)
    for bar in range(bars):
        bt = bar * 4 * TICKS_PER_BEAT
        # Beat 1: kick + (optional crash bar 0).
        out.append((bt, KICK, 102))
        if bar == 0:
            out.append((bt, CRASH_1, 110))
        # Beat 2: snare.
        out.append((bt + 1 * TICKS_PER_BEAT, SNARE, 105))
        # Beat 3: kick + kick-and (ghost double-pedal).
        out.append((bt + 2 * TICKS_PER_BEAT, KICK, 98))
        out.append((bt + 2 * TICKS_PER_BEAT + eighth, KICK, 80))
        # Beat 4: tom fill on every 16th — the rare-emphasis hook.
        for step in range(4):
            tom = toms[(bar * 4 + step) % len(toms)]
            out.append((bt + 3 * TICKS_PER_BEAT + step * sixteenth, tom, 95 + step * 4))
        # Closed hi-hat on beats 1, 2, 3 (none on beat 4 — tom fill takes over).
        for step in range(6):
            out.append((bt + step * eighth, HH_CLOSED, 60))
    return out


def _splash_bell(bars: int) -> list[tuple[int, int, int]]:
    """Splash + ride bell accents — rare cymbals foregrounded."""
    eighth = TICKS_PER_BEAT // 2
    sixteenth = TICKS_PER_BEAT // 4
    out: list[tuple[int, int, int]] = []
    for bar in range(bars):
        bt = bar * 4 * TICKS_PER_BEAT
        # Kick on 1 + 3-and.
        out.append((bt, KICK, 100))
        out.append((bt + 2 * TICKS_PER_BEAT + sixteenth * 2, KICK, 92))
        # Snare on 2 + 4.
        out.append((bt + 1 * TICKS_PER_BEAT, SNARE, 108))
        out.append((bt + 3 * TICKS_PER_BEAT, SNARE, 108))
        # Splash on every +e (16th after each beat) — the rare-emphasis hook.
        for step in range(4):
            out.append((bt + step * TICKS_PER_BEAT + sixteenth, SPLASH, 85))
        # Ride bell on upbeats (beats 2, 4).
        out.append((bt + 1 * TICKS_PER_BEAT + eighth, RIDE_BELL, 92))
        out.append((bt + 3 * TICKS_PER_BEAT + eighth, RIDE_BELL, 90))
        # Open hi-hat on beat 1 of even bars (color), foot on +.
        if bar % 2 == 0:
            out.append((bt, HH_OPEN, 70))
        for step in range(4):
            out.append((bt + step * TICKS_PER_BEAT + eighth, HH_PEDAL, 45))
    return out


_FAMILIES: tuple[tuple[str, _GroovePattern], ...] = (
    ("crash_led", _crash_led),
    ("china_led", _china_led),
    ("ride_led", _ride_led),
    ("tom_fill_heavy", _tom_fill_heavy),
    ("splash_bell", _splash_bell),
)


def _groove_for_index(index: int) -> GrooveSpec:
    """Deterministic groove from ``index ∈ [0, N_GROOVES)``.

    Index decomposition: ``index = family * _GROOVES_PER_FAMILY
    + bpm_tier * len(_BARS_OPTIONS) + bars_tier``.

    With the F0-T4c B6c extension this is ``family * 10 + bpm_tier * 2 +
    bars_tier`` (was ``family * 6 + bpm_tier * 2 + bars_tier`` pre-amendment).
    """
    if not 0 <= index < N_GROOVES:
        raise ValueError(f"index {index} outside [0, {N_GROOVES})")
    family_idx = index // _GROOVES_PER_FAMILY
    sub_idx = index % _GROOVES_PER_FAMILY
    bpm_tier = sub_idx // len(_BARS_OPTIONS)
    bars_idx = sub_idx % len(_BARS_OPTIONS)
    family_name, generator = _FAMILIES[family_idx]
    bpm = _BPM_TIERS[bpm_tier]
    bars = _BARS_OPTIONS[bars_idx]
    events = generator(bars)
    name = f"rare-{family_name}-bpm{bpm}-bars{bars}"
    return GrooveSpec(name=name, bpm=bpm, events=events)


def generate_rare_emphasis_grooves(*, n: int = N_GROOVES) -> list[GrooveSpec]:
    """Return the deterministic list of rare-emphasis grooves (Layer B).

    Parameters
    ----------
    n
        Number of grooves to return. Default 50 (F0-T4c B6c Decision Lock
        CEO 2026-05-24; was 30 pre-amendment).
        Must satisfy ``0 < n <= 50``.

    Returns
    -------
    list[GrooveSpec]
        Grooves indexed ``[0, n)``, deterministic — same input ⇒ same output,
        byte-for-byte (no randomness in this layer; the jitter pipeline runs
        downstream).
    """
    if not 0 < n <= N_GROOVES:
        raise ValueError(f"n={n} outside (0, {N_GROOVES}]")
    return [_groove_for_index(i) for i in range(n)]
