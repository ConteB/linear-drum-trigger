"""MIDI jitter pipeline (F0-T15-pre LOCKED — DOSSIER §3.1).

Implements the four pre-render augmentation voices ratified by Decision Lock
CEO 2026-05-23:

* **Time Jittering** — gaussian onset shift σ=2 ms, clipped to ±5 ms. Note
  *durations* are preserved (the corresponding ``note_off`` shifts by the same
  delta as its ``note_on``); this keeps the F0-T2a §3.3 target builder
  consistent under jitter (the matching ``note_on/note_off`` pair never
  changes its length, only its position on the timeline).
* **Flam artifacts** — 5% of notes get a paired companion 15–25 ms before the
  original (uniform), with velocity ≈ 0.6× the original. Inserted notes share
  the same pitch and a half-length duration.
* **Velocity Jittering** — additive gaussian σ=8, clip [1, 127]. Applied to
  every ``note_on``.
* **Ghost Masking** — notes with ``velocity ≤ 40`` are multiplied by a uniform
  factor in [0.3, 1.0]. Stacked *after* Velocity Jittering.
* **Global Gain Shift** — a single per-track factor sampled uniformly from
  [0.5, 2.0], applied to every ``note_on`` velocity (after Ghost Masking).
* **Component Dropping** — 10% of (bus, 2-second zone) cells are removed,
  with the **groove-skeleton clause**: in any zone where both the kick and the
  snare voices have notes, at least one of them survives.

The transform is **idempotent on variant 0** (the baseline branch): the RNG
is still derived from the master seed for replay determinism, but every
voice is bypassed. This keeps the recipe-matrix invariant — every (MIDI,
variant) pair goes through the same code path.

Fail-loud (ENGINEERING_STANDARDS §6): malformed MIDI raises
:class:`MidiAugmentError` and *no partial output* is ever returned.
"""
from __future__ import annotations

import io
from collections.abc import Callable
from typing import TYPE_CHECKING

import mido  # type: ignore[import-untyped]
import numpy as np

from .seed import derive_jitter_seed

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Resolver mapping ``abs_tick -> ticks_per_second`` under the file's tempo
#: map. Built once per :func:`apply_midi_jitter` call and passed to the voices
#: that need millisecond ↔ tick conversion.
TicksPerSecondFn = Callable[[int], float]

#: GM drum note for the bass drum (``kick``) — bus 0 in the mapping table.
KICK_NOTE: int = 36
#: GM drum note for the acoustic snare — bus 1 in the mapping table.
SNARE_NOTE: int = 38

#: Time Jittering — gaussian standard deviation, in milliseconds.
TIME_JITTER_SIGMA_MS: float = 2.0
#: Time Jittering — symmetric clip, in milliseconds.
TIME_JITTER_CLIP_MS: float = 5.0

#: Flam probability — fraction of notes that get an artificial companion.
FLAM_PROBABILITY: float = 0.05
#: Flam distance — interval between the original and the companion, in ms.
FLAM_DISTANCE_MIN_MS: float = 15.0
FLAM_DISTANCE_MAX_MS: float = 25.0
#: Flam velocity factor — the companion is softer than the original.
FLAM_VELOCITY_FACTOR: float = 0.6

#: Velocity Jittering — gaussian standard deviation (additive on the 7-bit
#: MIDI velocity scale).
VELOCITY_JITTER_SIGMA: float = 8.0
#: MIDI velocity bounds (a velocity of 0 is a ``note_off`` in some contracts,
#: so we clip to 1 to keep ``note_on`` semantics).
VELOCITY_MIN: int = 1
VELOCITY_MAX: int = 127

#: Ghost Masking — notes ≤ this velocity are candidate ghost notes.
GHOST_THRESHOLD: int = 40
#: Ghost Masking — uniform attenuation range.
GHOST_FACTOR_MIN: float = 0.3
GHOST_FACTOR_MAX: float = 1.0

#: Global Gain Shift — uniform multiplier range applied to every velocity.
GAIN_SHIFT_MIN: float = 0.5
GAIN_SHIFT_MAX: float = 2.0

#: Component Dropping — drop probability per (bus, 2-second zone) cell.
COMPONENT_DROP_PROBABILITY: float = 0.10
#: Component Dropping — zone width, in seconds.
COMPONENT_DROP_ZONE_S: float = 2.0


class MidiAugmentError(ValueError):
    """Raised when a MIDI file or jitter parameter cannot yield a valid output."""


def apply_midi_jitter(
    midi: mido.MidiFile,
    *,
    variant_idx: int,
    master_seed: int,
    source_midi_id: str,
) -> mido.MidiFile:
    """Apply the F0-T15-pre jitter pipeline to ``midi``.

    Args:
        midi: The source MIDI file (drum track expected, GM mapping). The
            input is **not mutated** — a fresh :class:`mido.MidiFile` is
            returned every call.
        variant_idx: 0 for the baseline (identity transform — RNG derived but
            no voice applied), 1..k for the jittered branches.
        master_seed: The run-level seed (F2-T1 ``recipe_matrix_seed``).
        source_midi_id: Stable identifier for the source MIDI; feeds
            :func:`derive_jitter_seed`.

    Returns:
        A new :class:`mido.MidiFile` with the jitter applied. The
        ``ticks_per_beat`` is preserved; tempo metadata is preserved.

    Raises:
        MidiAugmentError: On malformed MIDI (negative ticks, ``note_on``
            without matching ``note_off`` on the same channel/pitch, unknown
            tempo before the first event).
    """
    if not isinstance(midi, mido.MidiFile):
        raise MidiAugmentError(
            f"midi: expected mido.MidiFile, got {type(midi).__name__}"
        )

    seed = derive_jitter_seed(master_seed, source_midi_id, variant_idx)
    rng = np.random.default_rng(seed)

    # 1. Flatten the input into (abs_tick, channel, kind, note, velocity)
    #    tuples; we work in absolute tick space because every jitter voice
    #    needs symmetric access to a note's ``note_on`` and its matching
    #    ``note_off``. We re-emit deltas at the very end.
    events, tempo_map, passthrough = _flatten_to_absolute(midi)

    if variant_idx == 0:
        # Baseline branch: identity. We still derive the seed and walk the
        # event list for the round-trip invariant ``flatten ∘ unflatten ==
        # identity`` (catches bugs in the codec early).
        return _build_midi(events, tempo_map, midi.ticks_per_beat, passthrough)

    ticks_per_second_fn = _ticks_per_second_resolver(tempo_map, midi.ticks_per_beat)

    # 2. Time Jittering (and Flam insertion). Time-domain first: subsequent
    #    voices operate on velocities, which are not invalidated by an
    #    onset shift.
    events = _time_jitter(events, rng, ticks_per_second_fn)
    events = _insert_flams(events, rng, ticks_per_second_fn)

    # 3. Velocity Jittering (additive gauss) -> Ghost Masking -> Global Gain
    #    Shift. Applied in a single pass over `note_on` events, in the order
    #    fixed by the spec.
    events = _velocity_jitter(events, rng)
    events = _ghost_masking(events, rng)
    events = _global_gain_shift(events, rng)

    # 4. Component Dropping (last — removes notes outright; running it before
    #    velocity voices would waste RNG draws on doomed notes).
    events = _component_drop(events, rng, ticks_per_second_fn)

    return _build_midi(events, tempo_map, midi.ticks_per_beat, passthrough)


# ----------------------------------------------------------------------------
# Internals — event-stream codec
# ----------------------------------------------------------------------------


def _flatten_to_absolute(
    midi: mido.MidiFile,
) -> tuple[
    list[dict[str, int]],
    list[tuple[int, int]],
    list[tuple[int, mido.Message | mido.MetaMessage]],
]:
    """Flatten ``midi`` into a sorted list of absolute-tick drum events.

    Returns ``(events, tempo_map, passthrough)`` where:

    * ``events`` is a list of dicts ``{abs_tick_on, abs_tick_off, channel,
      note, velocity}`` — one entry per matched ``(note_on, note_off)`` pair.
    * ``tempo_map`` is a list of ``(abs_tick, tempo_us_per_beat)`` pairs,
      sorted by tick; the first entry covers tick 0 (defaulted to 500_000 /
      120 BPM if the source omits a ``set_tempo``).
    * ``passthrough`` is a list of ``(abs_tick, msg)`` for every non-note,
      non-tempo message (``control_change`` incl. the **CC#4 hi-hat pedal**,
      pitchwheel, program_change, other meta). F0-T19 §7b: the continuous
      hi-hat opening head reads CC#4 from the rendered MIDI, so CC#4 **must**
      survive jitter — before this it was silently dropped.
    """
    if not midi.tracks:
        raise MidiAugmentError("midi: must have at least one track")

    events: list[dict[str, int]] = []
    tempo_map: list[tuple[int, int]] = []
    passthrough: list[tuple[int, mido.Message | mido.MetaMessage]] = []
    # `note_on` waiting for its matching `note_off`, keyed by (track, channel,
    # note) — `track` keeps two tracks with overlapping channels distinct.
    pending: dict[tuple[int, int, int], tuple[int, int]] = {}

    for track_idx, track in enumerate(midi.tracks):
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if abs_tick < 0:
                raise MidiAugmentError(
                    f"midi: negative absolute tick on track {track_idx}: {abs_tick}"
                )
            if msg.is_meta and msg.type == "set_tempo":
                tempo_map.append((abs_tick, int(msg.tempo)))
                continue
            if msg.is_meta and msg.type == "end_of_track":
                continue  # synthesized fresh in _build_midi
            if msg.type == "note_on" and msg.velocity > 0:
                key = (track_idx, msg.channel, msg.note)
                pending[key] = (abs_tick, msg.velocity)
                continue
            if msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                key = (track_idx, msg.channel, msg.note)
                start = pending.pop(key, None)
                if start is None:
                    # Orphan `note_off` — silently skipped (some MIDI editors
                    # emit them for safety). The recipe-matrix runner will
                    # report the file if it is widely malformed.
                    continue
                events.append(
                    {
                        "abs_tick_on": start[0],
                        "abs_tick_off": abs_tick,
                        "channel": msg.channel,
                        "note": msg.note,
                        "velocity": start[1],
                    }
                )
                continue
            # Everything else (CC#4 + other CC, pitchwheel, program_change,
            # non-tempo meta): preserve verbatim at this absolute tick (F0-T19).
            passthrough.append((abs_tick, msg))

    if pending:
        raise MidiAugmentError(
            f"midi: {len(pending)} note_on event(s) without matching note_off"
        )

    if not tempo_map or tempo_map[0][0] > 0:
        tempo_map.insert(0, (0, 500_000))  # default 120 BPM

    tempo_map.sort(key=lambda pair: pair[0])
    events.sort(key=lambda evt: (evt["abs_tick_on"], evt["note"], evt["channel"]))
    passthrough.sort(key=lambda pair: pair[0])
    return events, tempo_map, passthrough


def _ticks_per_second_resolver(
    tempo_map: list[tuple[int, int]], ticks_per_beat: int
) -> TicksPerSecondFn:
    """Return a function ``abs_tick -> ticks_per_second`` for jitter math.

    The MIDI tempo map is piecewise-constant; we expose a tiny resolver
    instead of a precomputed table because the jitter voices only need a
    handful of lookups per note.
    """

    def _resolve(abs_tick: int) -> float:
        active_tempo_us = tempo_map[0][1]
        for tick, tempo_us in tempo_map:
            if tick <= abs_tick:
                active_tempo_us = tempo_us
            else:
                break
        # ticks_per_beat ticks / beat · 1e6 us / s ÷ tempo_us / beat
        #   = ticks_per_beat × 1e6 / tempo_us  (ticks per second)
        return ticks_per_beat * 1_000_000.0 / active_tempo_us

    return _resolve


def _build_midi(
    events: list[dict[str, int]],
    tempo_map: list[tuple[int, int]],
    ticks_per_beat: int,
    passthrough: list[tuple[int, mido.Message | mido.MetaMessage]] | None = None,
) -> mido.MidiFile:
    """Rebuild a single-track :class:`mido.MidiFile` from absolute events.

    ``passthrough`` messages (CC#4 hi-hat pedal etc., F0-T19 §7b) are re-emitted
    at their absolute tick with sort-kind 3 — after the note events at the same
    tick (intra-tick order is immaterial to the continuous, step-held head).
    """
    out = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    out.tracks.append(track)

    # (abs_tick, kind, payload). kind sort: 0 = tempo, 1 = note_off,
    # 2 = note_on — ensures tempo lands at the right tick and note_off goes
    # before note_on at the same tick.
    timed: list[tuple[int, int, mido.MetaMessage | mido.Message]] = []
    for tick, tempo_us in tempo_map:
        timed.append(
            (tick, 0, mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))
        )
    for evt in events:
        timed.append(
            (
                evt["abs_tick_on"],
                2,
                mido.Message(
                    "note_on",
                    channel=evt["channel"],
                    note=evt["note"],
                    velocity=evt["velocity"],
                ),
            )
        )
        timed.append(
            (
                evt["abs_tick_off"],
                1,
                mido.Message(
                    "note_off",
                    channel=evt["channel"],
                    note=evt["note"],
                    velocity=64,
                ),
            )
        )
    for abs_tick, msg in passthrough or []:
        timed.append((abs_tick, 3, msg))
    timed.sort(key=lambda item: (item[0], item[1]))

    prev = 0
    for abs_tick, _, message in timed:
        track.append(message.copy(time=abs_tick - prev))
        prev = abs_tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    return out


# ----------------------------------------------------------------------------
# Jitter voices
# ----------------------------------------------------------------------------


def _time_jitter(
    events: list[dict[str, int]],
    rng: np.random.Generator,
    ticks_per_second_fn: TicksPerSecondFn,
) -> list[dict[str, int]]:
    """Apply gaussian onset shift (σ=2 ms, clip ±5 ms), preserving durations."""
    if not events:
        return events
    n = len(events)
    shifts_ms = rng.normal(0.0, TIME_JITTER_SIGMA_MS, size=n)
    shifts_ms = np.clip(shifts_ms, -TIME_JITTER_CLIP_MS, TIME_JITTER_CLIP_MS)

    new_events: list[dict[str, int]] = []
    for evt, shift_ms in zip(events, shifts_ms, strict=True):
        tps = ticks_per_second_fn(evt["abs_tick_on"])
        shift_ticks = int(round(shift_ms / 1000.0 * tps))
        new_on = max(0, evt["abs_tick_on"] + shift_ticks)
        # Preserve the note duration: shift `note_off` by the actual applied
        # delta (after the max(0, ...) clamp at the start of the file).
        delta = new_on - evt["abs_tick_on"]
        new_off = max(new_on + 1, evt["abs_tick_off"] + delta)
        new_evt = dict(evt)
        new_evt["abs_tick_on"] = new_on
        new_evt["abs_tick_off"] = new_off
        new_events.append(new_evt)
    new_events.sort(key=lambda e: (e["abs_tick_on"], e["note"], e["channel"]))
    return new_events


def _insert_flams(
    events: list[dict[str, int]],
    rng: np.random.Generator,
    ticks_per_second_fn: TicksPerSecondFn,
) -> list[dict[str, int]]:
    """Add a companion note 15–25 ms before each of the 5% selected notes."""
    if not events:
        return events
    selection = rng.random(size=len(events)) < FLAM_PROBABILITY
    distances_ms = rng.uniform(FLAM_DISTANCE_MIN_MS, FLAM_DISTANCE_MAX_MS, size=len(events))

    inserted: list[dict[str, int]] = []
    for evt, do_flam, dist_ms in zip(events, selection, distances_ms, strict=True):
        if not do_flam:
            continue
        tps = ticks_per_second_fn(evt["abs_tick_on"])
        dist_ticks = int(round(dist_ms / 1000.0 * tps))
        comp_on = max(0, evt["abs_tick_on"] - dist_ticks)
        # Half the original duration, but at least 1 tick — and capped so the
        # companion never overlaps the original onset.
        original_len = max(1, evt["abs_tick_off"] - evt["abs_tick_on"])
        comp_off = min(comp_on + max(1, original_len // 2), evt["abs_tick_on"])
        # Companion velocity ≈ 0.6× original, clipped to MIDI bounds.
        comp_vel = int(round(evt["velocity"] * FLAM_VELOCITY_FACTOR))
        comp_vel = max(VELOCITY_MIN, min(VELOCITY_MAX, comp_vel))
        inserted.append(
            {
                "abs_tick_on": comp_on,
                "abs_tick_off": comp_off,
                "channel": evt["channel"],
                "note": evt["note"],
                "velocity": comp_vel,
            }
        )

    if not inserted:
        return events
    merged = events + inserted
    merged.sort(key=lambda e: (e["abs_tick_on"], e["note"], e["channel"]))
    return merged


def _velocity_jitter(
    events: list[dict[str, int]], rng: np.random.Generator
) -> list[dict[str, int]]:
    """Additive gaussian velocity perturbation σ=8, clipped to [1, 127]."""
    if not events:
        return events
    deltas = rng.normal(0.0, VELOCITY_JITTER_SIGMA, size=len(events))
    for evt, delta in zip(events, deltas, strict=True):
        new_vel = int(round(evt["velocity"] + delta))
        evt["velocity"] = max(VELOCITY_MIN, min(VELOCITY_MAX, new_vel))
    return events


def _ghost_masking(
    events: list[dict[str, int]], rng: np.random.Generator
) -> list[dict[str, int]]:
    """Attenuate ``velocity ≤ 40`` notes by a uniform factor in [0.3, 1.0]."""
    if not events:
        return events
    factors = rng.uniform(GHOST_FACTOR_MIN, GHOST_FACTOR_MAX, size=len(events))
    for evt, factor in zip(events, factors, strict=True):
        if evt["velocity"] <= GHOST_THRESHOLD:
            new_vel = int(round(evt["velocity"] * factor))
            evt["velocity"] = max(VELOCITY_MIN, min(VELOCITY_MAX, new_vel))
    return events


def _global_gain_shift(
    events: list[dict[str, int]], rng: np.random.Generator
) -> list[dict[str, int]]:
    """Multiply every velocity by a single per-track factor in [0.5, 2.0]."""
    if not events:
        return events
    factor = float(rng.uniform(GAIN_SHIFT_MIN, GAIN_SHIFT_MAX))
    for evt in events:
        new_vel = int(round(evt["velocity"] * factor))
        evt["velocity"] = max(VELOCITY_MIN, min(VELOCITY_MAX, new_vel))
    return events


def _component_drop(
    events: list[dict[str, int]],
    rng: np.random.Generator,
    ticks_per_second_fn: TicksPerSecondFn,
) -> list[dict[str, int]]:
    """Drop 10% of (note, 2-second zone) cells, preserving the groove skeleton.

    The skeleton clause (F0-T15-pre §4.1, DOSSIER §3.1): in any 2-second zone
    where both the kick and the snare voices have at least one note, at
    least one of them survives. Otherwise the groove disintegrates and the
    target carries an onset the audio cannot evidence.
    """
    if not events:
        return events

    # Group events by (note, zone_idx). The zone_idx is computed from
    # `abs_tick_on` using the tempo at that tick — zones are 2 s of *wall*
    # time, not tick-fixed, which matches "groove-time" intuitively.
    cells: dict[tuple[int, int], list[int]] = {}
    for idx, evt in enumerate(events):
        tps = ticks_per_second_fn(evt["abs_tick_on"])
        zone_idx = int(evt["abs_tick_on"] / (tps * COMPONENT_DROP_ZONE_S))
        cells.setdefault((evt["note"], zone_idx), []).append(idx)

    # Decide which cells to drop. We draw once per cell, in a stable order
    # (sorted keys) so the RNG consumption is deterministic.
    drop_decisions = {}
    for cell_key in sorted(cells):
        drop_decisions[cell_key] = bool(rng.random() < COMPONENT_DROP_PROBABILITY)

    # Skeleton clause: in any zone with both KICK and SNARE present, if both
    # are slated for dropping, keep the one with the *lower* draw — i.e. veto
    # one of the drops. We re-draw the veto choice deterministically to keep
    # bit-replay.
    zones_with_kick = {key[1] for key in cells if key[0] == KICK_NOTE}
    zones_with_snare = {key[1] for key in cells if key[0] == SNARE_NOTE}
    risky_zones = sorted(zones_with_kick & zones_with_snare)
    for zone_idx in risky_zones:
        kick_drop = drop_decisions.get((KICK_NOTE, zone_idx), False)
        snare_drop = drop_decisions.get((SNARE_NOTE, zone_idx), False)
        if kick_drop and snare_drop:
            # Veto the kick drop by default — kick is more rhythmically load-
            # bearing in most grooves. Single draw used so the choice is
            # auditable (`rng.random() < 0.5` would still be deterministic
            # but harder to reason about; the fixed rule is clearer).
            drop_decisions[(KICK_NOTE, zone_idx)] = False

    dropped_indices: set[int] = set()
    for cell_key, indices in cells.items():
        if drop_decisions[cell_key]:
            dropped_indices.update(indices)

    return [evt for idx, evt in enumerate(events) if idx not in dropped_indices]


# ----------------------------------------------------------------------------
# Diagnostics (used by acceptance tests / Ocular Proof)
# ----------------------------------------------------------------------------


def midi_to_event_list(midi: mido.MidiFile) -> list[tuple[int, int, int]]:
    """Helper: return ``(abs_tick_on, note, velocity)`` tuples sorted by tick.

    Public because the acceptance harness and the recipe-matrix builder both
    want a stable, comparable view of a MIDI without re-parsing.
    """
    events, _, _ = _flatten_to_absolute(midi)
    return [(e["abs_tick_on"], e["note"], e["velocity"]) for e in events]


def midi_bytes(midi: mido.MidiFile) -> bytes:
    """Helper: serialise a :class:`mido.MidiFile` to its on-disk bytes.

    Used by determinism tests — two MIDI files are byte-identical iff their
    serialised forms match (mido's structural equality is not defined).
    """
    buf = io.BytesIO()
    midi.save(file=buf)
    return buf.getvalue()


def iter_note_events(events: Iterable[dict[str, int]]) -> Iterable[dict[str, int]]:
    """Trivial alias so external callers can iterate without importing dict shape."""
    yield from events
