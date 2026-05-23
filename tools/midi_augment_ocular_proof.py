#!/usr/bin/env python3
"""F0-T16-pre — Ocular Proof of the MIDI augmentation pipeline.

Generates a side-by-side piano-roll PNG of one mini-batch MIDI, comparing the
baseline (variant 0) to k=2 jittered variants. The visual ratifies, at a
glance, that:

* baseline is event-identical to the source,
* jittered branches actually move/insert/drop notes within the locked envelopes
  (Time σ=2 ms / clip ±5 ms, Flam 15-25 ms companion, Velocity gauss σ=8 +
  Ghost + Gain, Component drop 10 % / 2 s with skeleton clause).

Outputs:

* ``docs/gates/F0-T16-pre_OCULAR_PROOF/midi_jitter_groove_NN.png`` — one
  4-panel piano-roll per mini-batch MIDI selected.

Run:  ``python tools/midi_augment_ocular_proof.py``
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import mido  # type: ignore[import-untyped]  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.midi_augment.jitter import (  # noqa: E402
    apply_midi_jitter,
    midi_to_event_list,
)

_MINI_BATCH = _REPO_ROOT / "bronze" / "gmd" / "mini"
_OUT_DIR = _REPO_ROOT / "docs" / "gates" / "F0-T16-pre_OCULAR_PROOF"

#: Which mini-batch grooves to render — keep the proof small and reproducible.
_SELECTION = ("groove_00", "groove_05")
#: Variants compared: baseline + 2 jittered.
_VARIANTS = (0, 1, 2)
_MASTER_SEED = 4242


def _plot_one(
    ax,  # type: ignore[no-untyped-def]
    title: str,
    events: list[tuple[int, int, int]],
    *,
    color: str,
) -> None:
    """Plot one panel: scatter of (abs_tick_on, note) sized by velocity."""
    if not events:
        ax.set_title(f"{title}\n(empty)")
        return
    ticks = [e[0] for e in events]
    notes = [e[1] for e in events]
    vels = [max(8, e[2]) for e in events]  # marker floor for visibility
    ax.scatter(ticks, notes, s=vels, color=color, alpha=0.8, edgecolors="black")
    ax.set_title(f"{title}  —  {len(events)} events")
    ax.set_xlabel("abs_tick (480 tpb)")
    ax.set_ylabel("MIDI note")
    ax.set_ylim(34, 54)
    ax.grid(True, alpha=0.3)


def _render_proof(midi_path: Path) -> Path:
    src = mido.MidiFile(str(midi_path))
    source_midi_id = str(midi_path.relative_to(_REPO_ROOT))
    src_events = midi_to_event_list(src)

    fig, axes = plt.subplots(1, 1 + len(_VARIANTS), figsize=(18, 4), sharey=True)
    _plot_one(axes[0], f"SOURCE  {midi_path.name}", src_events, color="black")
    palette = ["#2a9d8f", "#e76f51", "#264653"]
    for col_idx, variant_idx in enumerate(_VARIANTS):
        out = apply_midi_jitter(
            src,
            variant_idx=variant_idx,
            master_seed=_MASTER_SEED,
            source_midi_id=source_midi_id,
        )
        out_events = midi_to_event_list(out)
        label = "BASELINE (v=0)" if variant_idx == 0 else f"JITTERED (v={variant_idx})"
        _plot_one(
            axes[col_idx + 1],
            label,
            out_events,
            color=palette[col_idx % len(palette)],
        )
    fig.suptitle(
        f"F0-T16-pre — MIDI augmentation Ocular Proof  ({midi_path.name})",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUT_DIR / f"midi_jitter_{midi_path.stem}.png"
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def main() -> None:
    if not _MINI_BATCH.exists():
        sys.exit(
            "mini-batch fixtures missing — regenerate with "
            "`python tools/gen_mini_batch_fixtures.py`"
        )
    print(f"F0-T16-pre Ocular Proof — master_seed={_MASTER_SEED}")
    for stem in _SELECTION:
        midi_path = _MINI_BATCH / f"{stem}.mid"
        if not midi_path.exists():
            print(f"  SKIP  {stem} (missing)")
            continue
        out_path = _render_proof(midi_path)
        print(f"  OK    {stem} -> {out_path.relative_to(_REPO_ROOT)}")

    # Also print a short event-level diff for the report.
    src_path = _MINI_BATCH / f"{_SELECTION[0]}.mid"
    src = mido.MidiFile(str(src_path))
    source_midi_id = str(src_path.relative_to(_REPO_ROOT))
    baseline = midi_to_event_list(
        apply_midi_jitter(
            src,
            variant_idx=0,
            master_seed=_MASTER_SEED,
            source_midi_id=source_midi_id,
        )
    )
    for variant_idx in (1, 2):
        jittered = midi_to_event_list(
            apply_midi_jitter(
                src,
                variant_idx=variant_idx,
                master_seed=_MASTER_SEED,
                source_midi_id=source_midi_id,
            )
        )
        # Count notes added/dropped vs baseline (rough — multiset diff).
        bcount = {(n, v): 0 for _, n, v in baseline}
        for _, n, v in baseline:
            bcount[(n, v)] = bcount.get((n, v), 0) + 1
        jcount: dict[tuple[int, int], int] = {}
        for _, n, v in jittered:
            jcount[(n, v)] = jcount.get((n, v), 0) + 1
        added = sum(max(0, jcount.get(k, 0) - bcount.get(k, 0)) for k in jcount)
        dropped = sum(max(0, bcount.get(k, 0) - jcount.get(k, 0)) for k in bcount)
        print(
            f"  v={variant_idx}  baseline={len(baseline):3d}  "
            f"jittered={len(jittered):3d}  added~={added}  dropped~={dropped}"
        )


if __name__ == "__main__":
    main()
