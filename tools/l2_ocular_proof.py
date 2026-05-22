#!/usr/bin/env python3
"""F0-T3 / Gate L2 — Ocular Proof artifact generator.

Picks one Sfizz sample and one DrumGizmo sample from the mini-batch and
produces, per sample, the four artifacts required by F0-T3:

    1. ``<key>.waveform.png``   — multi-mic waveform plot (one subplot per mic).
    2. ``<key>.target.png``     — flat-25 piano-roll heatmap with the MIDI
                                  ground-truth onsets overlaid as crosses, plus
                                  the continuous Hi-Hat opening head.
    3. ``<key>.integrity.txt``  — FP16 integrity report, DNA-Trace validation,
                                  and (for multi-mic samples) an envelope-RMS
                                  bleed correlation matrix.
    4. ``L2_INSPECTION_<date>.md`` — the master checklist that bundles the
                                     samples and gives the CEO a single page
                                     to sign.

All artifacts land under ``docs/gates/L2_OCULAR_PROOF/`` so they live next to
the gate document and are picked up by the linker (F0-T10).

The script is read-only of the Gold buffers — it never mutates a sample.

Usage:
    python tools/l2_ocular_proof.py
    python tools/l2_ocular_proof.py --gold-dir data/gold/mini_batch
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend — no display required
import matplotlib.pyplot as plt
import mido  # type: ignore[import-untyped]
import numpy as np
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.gold.gold_writer import (  # noqa: E402
    HIHAT_OPENING_COL,
    N_BUSES,
    R_TARGET_HZ,
    SAMPLE_RATE,
    TARGET_COLS,
)

_DEFAULT_GOLD_DIR = _REPO_ROOT / "data" / "gold" / "mini_batch"
_DEFAULT_OUT_DIR = _REPO_ROOT / "docs" / "gates" / "L2_OCULAR_PROOF"
_DEFAULT_MAPPING = _REPO_ROOT / "docs" / "specs" / "midi_mapping_table.yaml"
_DEFAULT_RECIPE_DIR = _REPO_ROOT / "recipes" / "mini_batch"

#: Onset Gaussian-smear standard deviation, ms (F0-T2a §3.5 / target_builder).
_SMEAR_MS = 3.0
#: Bus names (midi_mapping_table.yaml).
_BUS_NAMES = ("kick", "snare", "hihat", "tom_hi_mid",
              "floor_tom", "ride", "crash_a", "crash_b_misc")


def _load_sample(gold_dir: Path, key: str) -> tuple[np.ndarray, np.ndarray, dict]:
    """Read the ``audio.f16`` / ``target.f16`` / ``dna.json`` triple back."""
    dna = json.loads((gold_dir / f"{key}.dna.json").read_text())
    audio_shape = dna["audio"]["shape"]
    target_shape = dna["target"]["shape"]
    audio = (
        np.fromfile(gold_dir / f"{key}.audio.f16", dtype="<f2")
        .reshape(audio_shape[0], audio_shape[1])
        .astype(np.float32)
    )
    target = (
        np.fromfile(gold_dir / f"{key}.target.f16", dtype="<f2")
        .reshape(target_shape[0], target_shape[1])
        .astype(np.float32)
    )
    return audio, target, dna


def _envelope(signal: np.ndarray, window: int = 4410) -> np.ndarray:
    """Sliding-window RMS envelope of a 1-D signal."""
    n = len(signal)
    if n < window:
        window = max(1, n // 4)
    power = signal.astype(np.float64) ** 2
    cumsum = np.cumsum(power)
    rms = np.sqrt(np.maximum(0.0, (cumsum[window:] - cumsum[:-window]) / window))
    return rms


def _bleed_matrix(audio: np.ndarray) -> np.ndarray:
    """Pairwise Pearson correlation of mic envelopes — falsifies bleed (F0-T2c)."""
    n_mic = audio.shape[0]
    envs = [_envelope(audio[i]) for i in range(n_mic)]
    m = min(len(e) for e in envs)
    envs = np.stack([e[:m] for e in envs])
    return np.corrcoef(envs)


def _plot_waveforms(audio: np.ndarray, title: str, png_path: Path) -> None:
    n_mic, n_sample = audio.shape
    t = np.arange(n_sample) / SAMPLE_RATE
    fig, axes = plt.subplots(n_mic, 1, figsize=(11, 1.4 * n_mic + 0.6), sharex=True)
    if n_mic == 1:
        axes = [axes]
    peak = max(float(np.abs(audio).max()), 1e-6)
    for i, ax in enumerate(axes):
        ax.plot(t, audio[i], linewidth=0.5, color="#205080")
        ax.set_ylim(-peak * 1.05, peak * 1.05)
        ax.set_ylabel(f"mic{i}", fontsize=9)
        ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel("time (s)")
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(png_path, dpi=110)
    plt.close(fig)


def _plot_target(
    target: np.ndarray,
    midi_onsets: list[tuple[float, int]],  # (time_s, bus)
    bus_mapping: dict,
    title: str,
    png_path: Path,
) -> None:
    n_frame = target.shape[0]
    t = np.arange(n_frame) / R_TARGET_HZ
    fig, axes = plt.subplots(
        N_BUSES + 1, 1,
        figsize=(11, 0.7 * (N_BUSES + 1) + 0.8),
        sharex=True,
        gridspec_kw={"height_ratios": [1] * N_BUSES + [1.2]},
    )

    smear_window_s = _SMEAR_MS / 1000.0 * 4  # ±4 sigma
    for bus in range(N_BUSES):
        ax = axes[bus]
        onset_col = 3 * bus
        ax.plot(t, target[:, onset_col], color="#205080", linewidth=0.8)
        ax.set_ylim(-0.05, 1.1)
        ax.set_ylabel(_BUS_NAMES[bus], fontsize=8, rotation=0,
                      ha="right", va="center")
        ax.set_yticks([])
        # Overlay MIDI ground-truth onsets — a cross at the exact time
        bus_onsets = [t_s for (t_s, b) in midi_onsets if b == bus]
        if bus_onsets:
            ax.scatter(bus_onsets, [1.05] * len(bus_onsets),
                       marker="x", s=22, color="#c03030", linewidths=1.0,
                       label=f"MIDI onsets (n={len(bus_onsets)})")
            ax.legend(loc="upper right", fontsize=6, framealpha=0.8)
        ax.grid(True, alpha=0.2)

    ax_hh = axes[N_BUSES]
    ax_hh.plot(t, target[:, HIHAT_OPENING_COL], color="#208050", linewidth=0.9)
    ax_hh.set_ylim(-0.05, 1.1)
    ax_hh.set_ylabel("HH open\n(continuous)", fontsize=8, rotation=0,
                     ha="right", va="center")
    ax_hh.set_yticks([0.0, 0.5, 1.0])
    ax_hh.set_xlabel("time (s)")
    ax_hh.grid(True, alpha=0.2)

    fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(png_path, dpi=110)
    plt.close(fig)


def _check_alignment(
    target: np.ndarray,
    midi_onsets: list[tuple[float, int]],
    tol_ms: float = _SMEAR_MS,
) -> tuple[int, int, float]:
    """For each MIDI onset, check the smeared probability peaks within ±tol_ms.

    Returns (n_checked, n_within_tol, max_drift_ms).
    """
    if not midi_onsets:
        return 0, 0, 0.0

    frame_period_s = 1.0 / R_TARGET_HZ
    tol_frames = max(1, int(round(tol_ms / 1000.0 / frame_period_s)))

    n_checked = 0
    n_within = 0
    max_drift_ms = 0.0
    for time_s, bus in midi_onsets:
        onset_col = 3 * bus
        expected_frame = int(round(time_s * R_TARGET_HZ))
        lo = max(0, expected_frame - tol_frames)
        hi = min(target.shape[0], expected_frame + tol_frames + 1)
        if hi <= lo:
            continue
        n_checked += 1
        window = target[lo:hi, onset_col]
        if window.size == 0 or float(window.max()) < 0.5:
            continue
        peak_frame = lo + int(np.argmax(window))
        drift_frames = peak_frame - expected_frame
        drift_ms = abs(drift_frames) * frame_period_s * 1000.0
        if drift_ms <= tol_ms + 1e-6:
            n_within += 1
        max_drift_ms = max(max_drift_ms, drift_ms)
    return n_checked, n_within, max_drift_ms


def _midi_onsets(midi_path: Path, gm_to_bus: dict[int, int]) -> list[tuple[float, int]]:
    """Extract (time_s, bus) tuples for every drum note in ``midi_path``."""
    mf = mido.MidiFile(str(midi_path))
    onsets: list[tuple[float, int]] = []
    time_s = 0.0
    for msg in mf:
        time_s += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            bus = gm_to_bus.get(msg.note)
            if bus is not None:
                onsets.append((time_s, bus))
    return onsets


def _integrity_report(
    audio: np.ndarray,
    target: np.ndarray,
    dna: dict,
    bleed: np.ndarray | None,
    align: tuple[int, int, float],
) -> str:
    lines: list[str] = []
    render = dna["lineage"]["render"]
    lines.append("=" * 70)
    lines.append(f"sample key: {dna['key']}")
    lines.append(f"engine: {render['engine']}  kit: {render['kit']}  "
                 f"mic_config: {render['mic_config']}")
    lines.append(f"recipe_id: {dna['recipe_id']}")
    lines.append("=" * 70)
    lines.append("")
    lines.append("[FP16 INTEGRITY — audio]")
    a32 = audio  # already float32 cast
    lines.append(f"  shape:             {audio.shape}  (expected [n_mic,n_sample])")
    lines.append(f"  duration_s:        {audio.shape[1]/SAMPLE_RATE:.4f}")
    lines.append(f"  any non-finite:    {bool(~np.isfinite(a32).all())}")
    lines.append(f"  peak |x|:          {float(np.abs(a32).max()):.5f}  (must be in (0,1])")
    lines.append(f"  RMS (overall):     {float(np.sqrt((a32**2).mean())):.5f}")
    lines.append(f"  silent channels:   "
                 f"{int(sum(np.abs(a32[i]).max() < 1e-6 for i in range(audio.shape[0])))} of {audio.shape[0]}")
    lines.append("")
    lines.append("[FP16 INTEGRITY — target]")
    lines.append(f"  shape:             {target.shape}  (expected [n_frame, 25])")
    lines.append(f"  any non-finite:    {bool(~np.isfinite(target).all())}")
    lines.append(f"  onset cols range:  [{float(target[:, 0::3][:, :8].min()):.3f}, "
                 f"{float(target[:, 0::3][:, :8].max()):.3f}]  (must be [0,1])")
    lines.append(f"  velocity cols rng: [{float(target[:, 1::3][:, :8].min()):.3f}, "
                 f"{float(target[:, 1::3][:, :8].max()):.3f}]")
    lines.append(f"  HH continuous rng: [{float(target[:, HIHAT_OPENING_COL].min()):.3f}, "
                 f"{float(target[:, HIHAT_OPENING_COL].max()):.3f}]  (must be [0,1])")
    lines.append("")
    lines.append("[DNA-TRACE LINEAGE]")
    a_shape = dna["audio"]["shape"]
    t_shape = dna["target"]["shape"]
    lines.append(f"  audio_shape (dna): {a_shape}  vs measured {list(audio.shape)}  "
                 f"-> {'OK' if a_shape == list(audio.shape) else 'MISMATCH'}")
    lines.append(f"  target_shape (dna):{t_shape}  vs measured {list(target.shape)} "
                 f"-> {'OK' if t_shape == list(target.shape) else 'MISMATCH'}")
    lines.append(f"  audio  non-finite (dna): {dna['audio']['n_nonfinite']}")
    lines.append(f"  target non-finite (dna): {dna['target']['n_nonfinite']}")
    lines.append(f"  audio_sha256:      {dna['audio']['sha256'][:24]}…")
    lines.append(f"  target_sha256:     {dna['target']['sha256'][:24]}…")
    lines.append(f"  recipe_sha256:     {dna['recipe_sha256'][:24]}…")
    lines.append(f"  generated_at:      {dna['generated_at']}")
    lines.append("")
    lines.append("[ALIGNMENT — MIDI vs target onset peaks, ±3 ms]")
    n_checked, n_within, max_drift = align
    if n_checked == 0:
        lines.append("  (no MIDI onsets in range)")
    else:
        lines.append(f"  onsets checked:    {n_checked}")
        lines.append(f"  within ±3 ms:      {n_within} / {n_checked}  "
                     f"({100.0*n_within/n_checked:.1f} %)")
        lines.append(f"  worst-case drift:  {max_drift:.2f} ms  "
                     f"(<= one frame period {1000.0/R_TARGET_HZ:.2f} ms is expected)")
    lines.append("")
    if bleed is not None:
        lines.append("[BLEED — envelope-RMS correlation between mics]")
        lines.append("       " + " ".join(f"mic{j}" for j in range(bleed.shape[0])))
        for i in range(bleed.shape[0]):
            row = " ".join(f"{bleed[i,j]:+5.2f}" for j in range(bleed.shape[1]))
            lines.append(f"  mic{i}  {row}")
        offdiag = bleed[~np.eye(bleed.shape[0], dtype=bool)]
        lines.append(f"  off-diagonal max:  {float(offdiag.max()):+.3f}  "
                     f"(non-trivial > 0.3 == bleed present, F0-T2c)")
    lines.append("=" * 70)
    return "\n".join(lines) + "\n"


def _load_gm_to_bus(mapping_path: Path) -> dict[int, int]:
    raw = yaml.safe_load(mapping_path.read_text())
    return {note: bus_id - 1 for note, bus_id in raw["forward_gm_to_bus"].items()}


def _resolve_midi_path(dna: dict, recipe_dir: Path) -> Path | None:
    """Look up the recipe's MIDI file from its DNA-recorded recipe_id."""
    for recipe_path in recipe_dir.glob("*.yaml"):
        data = yaml.safe_load(recipe_path.read_text())
        if data.get("recipe_id") == dna["recipe_id"]:
            return _REPO_ROOT / data["midi_source"]["file"]
    return None


def _select_samples(gold_dirs: list[Path]) -> dict[str, tuple[str, Path]]:
    """Pick one Sfizz key and one DrumGizmo key, scanning every ``gold_dirs``."""
    chosen: dict[str, tuple[str, Path]] = {}
    for gold_dir in gold_dirs:
        for p in sorted(gold_dir.glob("*.dna.json")):
            dna = json.loads(p.read_text())
            engine = dna["lineage"]["render"]["engine"]
            if engine in chosen:
                continue
            chosen[engine] = (dna["key"], gold_dir)
        if "sfizz" in chosen and "drumgizmo" in chosen:
            break
    return chosen


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gold-dir", type=Path, action="append",
                   help="repeatable — scan multiple Gold sample directories")
    p.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
    p.add_argument("--mapping", type=Path, default=_DEFAULT_MAPPING)
    p.add_argument("--recipe-dir", type=Path, default=_DEFAULT_RECIPE_DIR)
    args = p.parse_args()

    gold_dirs = args.gold_dir or [_DEFAULT_GOLD_DIR]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    gm_to_bus = _load_gm_to_bus(args.mapping)

    chosen = _select_samples(gold_dirs)
    if not chosen:
        print(f"FATAL: no Gold samples in {gold_dirs}", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for engine, (key, gold_dir) in chosen.items():
        audio, target, dna = _load_sample(gold_dir, key)
        midi_path = _resolve_midi_path(dna, args.recipe_dir)
        onsets: list[tuple[float, int]] = []
        if midi_path and midi_path.is_file():
            onsets = _midi_onsets(midi_path, gm_to_bus)

        wave_png = args.out_dir / f"{key}.waveform.png"
        target_png = args.out_dir / f"{key}.target.png"
        report_txt = args.out_dir / f"{key}.integrity.txt"

        _plot_waveforms(audio, f"{key} — waveform ({audio.shape[0]} mic)", wave_png)
        _plot_target(target, onsets, gm_to_bus,
                     f"{key} — flat-25 target + MIDI ground truth", target_png)

        bleed = _bleed_matrix(audio) if audio.shape[0] >= 2 else None
        align = _check_alignment(target, onsets)
        report_txt.write_text(_integrity_report(audio, target, dna, bleed, align))

        rows.append({
            "engine": engine,
            "key": key,
            "n_mic": audio.shape[0],
            "audio_s": audio.shape[1] / SAMPLE_RATE,
            "wave_png": wave_png,
            "target_png": target_png,
            "report_txt": report_txt,
            "align_n_checked": align[0],
            "align_n_within": align[1],
            "align_max_drift_ms": align[2],
            "bleed_offdiag_max": (
                float(bleed[~np.eye(bleed.shape[0], dtype=bool)].max())
                if bleed is not None else None
            ),
        })
        print(f"  [{engine:9s}] {key}  -> {wave_png.name}, {target_png.name}, {report_txt.name}")

    # ---- master checklist ----
    today = dt.date.today().isoformat()
    md = args.out_dir / f"L2_INSPECTION_{today}.md"
    lines = [
        "---",
        f"title: L2 Ocular Proof — inspection {today}",
        "owner: F0-T3",
        f"date: {today}",
        "scope: F0",
        "status: DRAFT",
        "---",
        "",
        f"# Gate L2 — Ocular Proof ({today})",
        "",
        "Gate `L2` per `F0-T3`: ispezione manuale del mini-batch Gold prodotto",
        "da `tools/run_mini_batch.py` (F0-T2e). DoD del task — checklist firmata e",
        "registrata in [`REGISTRO_AVANZAMENTO.md`](../../../04_INTELLIGENCE/REGISTRO_AVANZAMENTO.md).",
        "",
        "## Campioni ispezionati",
        "",
        "| # | Engine | Sample key | mic | durata | drift max | bleed max off-diag |",
        "| :-- | :-- | :-- | :--: | :--: | :--: | :--: |",
    ]
    for i, r in enumerate(rows, 1):
        drift = f"{r['align_max_drift_ms']:.2f} ms" if r["align_n_checked"] else "—"
        bleed = (f"+{r['bleed_offdiag_max']:.2f}" if r["bleed_offdiag_max"] is not None
                 else "n/a (mono/stereo)")
        lines.append(
            f"| {i} | `{r['engine']}` | `{r['key']}` | {r['n_mic']} | "
            f"{r['audio_s']:.2f} s | {drift} | {bleed} |"
        )

    lines += [
        "",
        "## Checklist L2",
        "",
        "*Per ogni campione vai al PNG e al `.integrity.txt` corrispondenti e firma.*",
        "",
    ]
    for i, r in enumerate(rows, 1):
        lines += [
            f"### Campione {i} — `{r['key']}` ({r['engine']})",
            "",
            f"- Waveform multi-mic: `{r['wave_png'].name}`",
            f"- Target piano-roll:  `{r['target_png'].name}`",
            f"- Integrity report:   `{r['report_txt'].name}`",
            "",
            "- [ ] **Waveform multi-mic coerente** (nessun canale silenzioso ingiustificato; ampiezze in range; nessun click anomalo).",
            "- [ ] **Allineamento target ↔ MIDI ±3 ms** "
            f"({r['align_n_within']} / {r['align_n_checked']} onsets entro tolleranza; drift max {r['align_max_drift_ms']:.2f} ms).",
            "- [ ] **Integrità FP16** (nessun NaN/inf, peak ∈ (0,1], onset/HH in [0,1] — vedi `.integrity.txt`).",
            "- [ ] **DNA-Trace lineage** (audio/target shape match; sha256 presenti; recipe_sha256 traccia la lineage — vedi `.integrity.txt`).",
        ]
        if r["bleed_offdiag_max"] is not None:
            verdict = "presente" if r["bleed_offdiag_max"] > 0.3 else "ASSENTE"
            lines.append(
                f"- [ ] **Bleed multi-mic** falsificabile via envelope-RMS correlation: "
                f"off-diagonal max **+{r['bleed_offdiag_max']:.2f}** → bleed **{verdict}**."
            )
        lines.append("")

    lines += [
        "## Decisione del CEO",
        "",
        "- [ ] **L2 SUPERATO** — sblocca lo spend RENDER (F1 + F2-T1).",
        "- [ ] **L2 NON SUPERATO** — annotare causa e ri-pianificare F0-T2 a valle.",
        "",
        f"**Data firma:** ____________________  **Firma CEO:** ____________________",
        "",
    ]
    md.write_text("\n".join(lines))
    print(f"\n  master checklist: {md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
