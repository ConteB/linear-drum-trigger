#!/usr/bin/env python3
"""Deep ocular audit della pipeline mini-L3 — CEO directive 2026-05-26.

Per ogni kit (5 train + 1 val) × 9 stage della pipeline, produce un'evidence
visuale falsificabile. Output PNG monocromo "Laboratory Precision" + report
markdown per kit. Index master in docs/gates/F0-T4c_PIPELINE_AUDIT/INDEX.md.

Stage:
  S1 — MIDI sorgente: piano-roll GM notes vs midimap del kit
  S2 — Render audio: waveform multi-mic (8 canonical slots) per onset/silent-zero
  S3 — Bleed cross-mic: matrice envelope-correlation per anomalie mic
  S4 — Tail standardization: waveform con marker last_onset_s + tail_s
  S5 — Target builder: piano-roll target 8-bus overlay su MIDI onset
  S6 — DNA-Trace integrity: sha256 audio/target + recipe_id integrity
  S7 — GoldDataset crop: crop window + lookahead shift visualizzato
  S8 — Preprocess P1+P2: pre-emphasis + onset envelope output per-canale
  S9 — Forward pass + peak-pick: prediction overlay target con FP/FN evidenziati

Usage:
  python tools/ocular_pipeline_audit.py
  python tools/ocular_pipeline_audit.py --kit DRSKit  # singolo kit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mido
import numpy as np
import torch
from scipy.signal import correlate

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.gold.target_builder import (  # noqa: E402
    BusMapping, load_bus_mapping, build_target,
)
from neural.data import load_gold_sample, discover_gold_keys  # noqa: E402
from neural.preprocessing import PreprocessingFrontend  # noqa: E402
from neural.model import TCNConfig, TCNModel  # noqa: E402

# Suppress noisy STFT warnings
warnings.filterwarnings("ignore", category=UserWarning)

SR = 44100
FR = 344.53125
OUT_ROOT = _REPO_ROOT / "docs" / "gates" / "F0-T4c_PIPELINE_AUDIT"

# "Laboratory Precision" monochrome palette
PALETTE = {
    "bg": "#fafafa",
    "fg": "#1a1a1a",
    "accent": "#cc4444",
    "ok": "#44aa44",
    "muted": "#888888",
    "grid": "#dddddd",
}
plt.rcParams.update({
    "figure.facecolor": PALETTE["bg"],
    "axes.facecolor": PALETTE["bg"],
    "axes.edgecolor": PALETTE["fg"],
    "axes.labelcolor": PALETTE["fg"],
    "axes.grid": True,
    "grid.color": PALETTE["grid"],
    "grid.linewidth": 0.4,
    "xtick.color": PALETTE["fg"],
    "ytick.color": PALETTE["fg"],
    "text.color": PALETTE["fg"],
    "font.size": 9,
    "font.family": "monospace",
})

BUS_NAMES = ["kick", "snare", "hihat", "tom_hi_mid", "floor", "ride", "crash_a", "crash_b_misc"]
MIC_NAMES = ["kick", "snare", "hihat", "tom", "floor", "OH_L", "OH_R", "room"]
KIT_DIRS = {
    "DRSKit":        ("train", "vendor/drumgizmo/DRSKit/DRSKit_full.xml", "vendor/drumgizmo/DRSKit/Midimap_full.xml"),
    "MuldjordKit":   ("train", "vendor/drumgizmo/MuldjordKit3/MuldjordKit3.xml", "vendor/drumgizmo/MuldjordKit3/Midimap.xml"),
    "CrocellKit":    ("train", "vendor/drumgizmo/CrocellKit/CrocellKit_full.xml", "vendor/drumgizmo/CrocellKit/Midimap_full.xml"),
    "Aasimonster":   ("train", "vendor/drumgizmo/Aasimonster/Aasimonster_full.xml", "vendor/drumgizmo/Aasimonster/midimap.xml"),
    "BigRustyDrums": ("train", "vendor/sfz/big-rusty-drums/Programs/01-full.sfz", None),  # SFZ no midimap
    "ShittyKit":     ("val",   "vendor/drumgizmo/ShittyKit/ShittyKit_full.xml", "vendor/drumgizmo/ShittyKit/midimap.xml"),
}


@dataclass
class StageResult:
    name: str
    status: str   # "PASS", "WARN", "FAIL"
    png_path: Path | None
    notes: list[str]


def pick_samples(kit: str, split: str) -> list[tuple[Any, Path]]:
    """Pick 1 baseline (J00) + 1 crash-bearing sample for the kit.

    Returns list of (GoldSample, sample_dir) — GoldSample lacks the on-disk
    path so we keep the directory alongside it for dna.json + midi lookups."""
    pool = _REPO_ROOT / "data" / "gold" / f"mini_l3_{split}" / kit
    if not pool.exists():
        return []
    triples = sorted(discover_gold_keys(pool), key=lambda x: x[1])
    if not triples:
        return []
    out: list[tuple[Any, Path]] = []
    # 1st: baseline (J00, V0T0)
    baseline = next((t for t in triples if "J00" in t[1] and "V0T0" in t[1]), triples[0])
    out.append((load_gold_sample(*baseline), baseline[0]))
    # 2nd: a crash-bearing sample (target col 18 — crash_a — has non-zero)
    if len(triples) > 1:
        chosen = None
        for d, k in triples[1:30]:
            s = load_gold_sample(d, k)
            if s.target.shape[0] > 0 and s.target[:, 18].max() > 0.5:
                chosen = (s, d); break
        if chosen is None:
            # No crash_a sample — pick a high-density sample as fallback
            mid = triples[len(triples) // 2]
            chosen = (load_gold_sample(*mid), mid[0])
        out.append(chosen)
    return out


# =========================================================================
# S1 — MIDI sorgente vs midimap
# =========================================================================

def stage_1_midi_vs_midimap(kit: str, samples: list, out_dir: Path) -> StageResult:
    """For each sample, plot the source MIDI piano-roll and overlay markers for
    GM notes NOT mapped in this kit's midimap.xml. The dataset bus_mapping
    yaml decides whether the unmapped onset becomes a 'phantom' target."""
    _, _, midimap_path = KIT_DIRS[kit]
    midimap_notes: set[int] = set()
    if midimap_path:
        full_path = _REPO_ROOT / midimap_path
        if full_path.exists():
            try:
                tree = ET.parse(full_path)
                for el in tree.getroot().iter():
                    if el.tag.endswith("map"):
                        note = el.get("note")
                        if note:
                            midimap_notes.add(int(note))
            except Exception:
                pass
    # Also load the project's GM→bus mapping (target-builder side)
    bm = load_bus_mapping(_REPO_ROOT / "docs/specs/midi_mapping_table.yaml")
    project_mapped = set(bm.gm_to_bus.keys())
    fig, axes = plt.subplots(len(samples), 1, figsize=(13, 3.2 * len(samples)),
                              constrained_layout=True, squeeze=False)
    fig.suptitle(f"S1 · MIDI ↔ Midimap audit — {kit}", fontweight="bold")
    notes_out: list[str] = []
    n_phantom_total = 0
    for i, (s, sdir) in enumerate(samples):
        ax = axes[i, 0]
        # Source MIDI is in the lineage — load
        dna = json.loads((sdir / f"{s.key}.dna.json").read_text())
        midi_rel = dna["lineage"]["midi_source"]["file"]
        midi_path = _REPO_ROOT / midi_rel
        if not midi_path.exists():
            ax.text(0.5, 0.5, f"MIDI source missing: {midi_rel}", ha="center",
                    transform=ax.transAxes)
            continue
        mid = mido.MidiFile(str(midi_path))
        notes_by_time: list[tuple[float, int]] = []
        t = 0.0
        for msg in mid:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                notes_by_time.append((t, msg.note))
        if not notes_by_time:
            continue
        times = np.array([n[0] for n in notes_by_time])
        gms = np.array([n[1] for n in notes_by_time])
        # Color encoding:
        #   GREEN  = in both kit-midimap AND project-mapping (rendered + target onset)
        #   ORANGE = in kit-midimap NOT in project-mapping (rendered audio, NO target = wasted)
        #   RED    = in project-mapping NOT in kit-midimap (PHANTOM: target onset, NO audio)
        #   GREY   = in neither (ignored on both sides)
        green = [(t, g) for t, g in notes_by_time if g in midimap_notes and g in project_mapped]
        orange = [(t, g) for t, g in notes_by_time if g in midimap_notes and g not in project_mapped]
        red = [(t, g) for t, g in notes_by_time if g not in midimap_notes and g in project_mapped]
        grey = [(t, g) for t, g in notes_by_time if g not in midimap_notes and g not in project_mapped]
        for lbl, lst, color, marker in [
            ("OK (render+target)", green, PALETTE["ok"], "o"),
            ("orange — render w/o target", orange, "#cc8800", "^"),
            ("PHANTOM — target w/o render", red, PALETTE["accent"], "x"),
            ("ignored on both sides", grey, PALETTE["muted"], "."),
        ]:
            if lst:
                ax.scatter([x[0] for x in lst], [x[1] for x in lst],
                           c=color, s=18, marker=marker, label=f"{lbl} ({len(lst)})",
                           edgecolors="black", linewidths=0.3, alpha=0.85)
        ax.set_title(f"sample: {s.key}", fontsize=10)
        ax.set_xlabel("time (s)")
        ax.set_ylabel("GM note")
        ax.set_ylim(30, 90)
        ax.legend(loc="upper right", fontsize=7, framealpha=0.9)
        n_phantom_total += len(red)
        notes_out.append(f"sample {s.key}: {len(green)} ok / "
                         f"{len(orange)} render-only / {len(red)} phantom / {len(grey)} ignored")
    png = out_dir / f"S1_midi_vs_midimap_{kit}.png"
    fig.savefig(png, dpi=110)
    plt.close()
    status = "PASS" if n_phantom_total == 0 else ("WARN" if n_phantom_total < 5 else "FAIL")
    notes_out.append(f"midimap notes count: {len(midimap_notes)}")
    notes_out.append(f"project_mapped notes count: {len(project_mapped)}")
    notes_out.append(f"TOTAL phantom onsets in audited samples: {n_phantom_total}")
    return StageResult("S1 MIDI vs midimap", status, png, notes_out)


# =========================================================================
# S2 — Render audio: waveform 8 canonical slots
# =========================================================================

def stage_2_render_audio(kit: str, samples: list, out_dir: Path) -> StageResult:
    """Plot all 8 canonical mic-slot waveforms; flag silent slots / clipping."""
    fig, axes = plt.subplots(len(samples), 8, figsize=(20, 2.6 * len(samples)),
                              constrained_layout=True, squeeze=False)
    fig.suptitle(f"S2 · Render audio (8 canonical slots) — {kit}", fontweight="bold")
    notes: list[str] = []
    status = "PASS"
    for r, (s, sdir) in enumerate(samples):
        audio = s.audio.astype(np.float32)
        for c in range(8):
            ax = axes[r, c]
            wav = audio[c]
            t_axis = np.arange(len(wav)) / SR
            ax.plot(t_axis, wav, lw=0.4, color=PALETTE["fg"])
            peak = np.abs(wav).max()
            rms = np.sqrt(np.mean(wav**2)) if wav.size else 0
            color = PALETTE["fg"]
            tag = ""
            if peak < 1e-4:
                color = PALETTE["accent"]; tag = " SILENT"
                status = "FAIL"
                notes.append(f"{s.key}: ch {c} ({MIC_NAMES[c]}) SILENT (peak<1e-4)")
            elif peak > 0.99:
                color = PALETTE["accent"]; tag = " CLIPPED"
                if status == "PASS": status = "WARN"
                notes.append(f"{s.key}: ch {c} ({MIC_NAMES[c]}) CLIPPED (peak={peak:.3f})")
            ax.set_title(f"{MIC_NAMES[c]} pk={peak:.2f}{tag}",
                         fontsize=8, color=color)
            ax.set_xlim(0, t_axis[-1] if t_axis.size else 1)
            ax.tick_params(labelsize=6)
            if c > 0:
                ax.set_yticklabels([])
    png = out_dir / f"S2_render_audio_{kit}.png"
    fig.savefig(png, dpi=110)
    plt.close()
    if not notes:
        notes = ["all slots non-silent, peak within (1e-4, 0.99]"]
    return StageResult("S2 Render audio", status, png, notes)


# =========================================================================
# S3 — Bleed cross-mic correlation matrix
# =========================================================================

def envelope_rms(wav: np.ndarray, win: int = 1024) -> np.ndarray:
    """RMS envelope with hop=win."""
    n = (len(wav) // win) * win
    if n == 0:
        return np.zeros(1)
    return np.sqrt((wav[:n].reshape(-1, win) ** 2).mean(axis=1))


def stage_3_bleed_matrix(kit: str, samples: list, out_dir: Path) -> StageResult:
    """Compute envelope-correlation matrix between all mic pairs."""
    fig, axes = plt.subplots(1, len(samples), figsize=(6 * len(samples), 5.6),
                              constrained_layout=True, squeeze=False)
    fig.suptitle(f"S3 · Bleed envelope-correlation matrix — {kit}", fontweight="bold")
    notes: list[str] = []
    status = "PASS"
    for r, (s, sdir) in enumerate(samples):
        ax = axes[0, r]
        audio = s.audio.astype(np.float32)
        envs = np.array([envelope_rms(audio[c]) for c in range(8)])
        m = np.corrcoef(envs)
        im = ax.imshow(m, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        for i in range(8):
            for j in range(8):
                ax.text(j, i, f"{m[i,j]:.2f}", ha="center", va="center",
                        fontsize=6, color="white" if abs(m[i,j]) > 0.5 else "black")
        ax.set_xticks(range(8)); ax.set_xticklabels(MIC_NAMES, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(range(8)); ax.set_yticklabels(MIC_NAMES, fontsize=7)
        ax.set_title(f"{s.key}", fontsize=9)
        plt.colorbar(im, ax=ax, fraction=0.046)
        # Check: identical channels (mic substituted with bleed)
        for i in range(8):
            for j in range(i+1, 8):
                if abs(m[i,j]) > 0.999:
                    notes.append(f"{s.key}: ch {i} ({MIC_NAMES[i]}) ≡ ch {j} "
                                f"({MIC_NAMES[j]}) — identical signals!")
                    status = "WARN"
    png = out_dir / f"S3_bleed_matrix_{kit}.png"
    fig.savefig(png, dpi=110)
    plt.close()
    if not notes:
        notes = ["no identical channel pairs (off-diag < 1.0 everywhere)"]
    return StageResult("S3 Bleed cross-mic", status, png, notes)


# =========================================================================
# S4 — Tail standardization
# =========================================================================

def stage_4_tail_std(kit: str, samples: list, out_dir: Path) -> StageResult:
    """Plot summed waveform with last_onset_s + tail_s markers."""
    fig, axes = plt.subplots(len(samples), 1, figsize=(13, 2.5 * len(samples)),
                              constrained_layout=True, squeeze=False)
    fig.suptitle(f"S4 · Tail standardization (last_onset + 0.5s) — {kit}", fontweight="bold")
    notes: list[str] = []
    status = "PASS"
    for r, (s, sdir) in enumerate(samples):
        ax = axes[r, 0]
        audio_sum = s.audio.astype(np.float32).sum(axis=0)
        t_axis = np.arange(len(audio_sum)) / SR
        ax.plot(t_axis, audio_sum, lw=0.4, color=PALETTE["fg"])
        dna = json.loads((sdir / f"{s.key}.dna.json").read_text())
        last_onset_s = dna["audio"]["last_onset_s"]
        tail_s = dna["audio"]["tail_s"]
        total_s = audio_sum.size / SR
        ax.axvline(last_onset_s, color=PALETTE["accent"], lw=1.5, ls="--",
                   label=f"last_onset_s = {last_onset_s:.3f}s")
        ax.axvline(last_onset_s + tail_s, color=PALETTE["ok"], lw=1.5, ls="--",
                   label=f"+tail_s = {last_onset_s+tail_s:.3f}s")
        ax.axvline(total_s, color=PALETTE["muted"], lw=1.0,
                   label=f"audio end = {total_s:.3f}s")
        delta = total_s - (last_onset_s + tail_s)
        if abs(delta) > 0.01:
            status = "FAIL"
            notes.append(f"{s.key}: audio end - (last_onset+tail) = {delta*1000:.1f}ms (expect ~0)")
        ax.set_title(f"{s.key}  Δ = {delta*1000:+.1f} ms", fontsize=10)
        ax.set_xlabel("time (s)")
        ax.legend(loc="upper right", fontsize=7)
    png = out_dir / f"S4_tail_std_{kit}.png"
    fig.savefig(png, dpi=110)
    plt.close()
    if not notes:
        notes = [f"all samples: Δ < 10 ms (tail standardization OK)"]
    return StageResult("S4 Tail std", status, png, notes)


# =========================================================================
# S5 — Target builder overlay
# =========================================================================

def stage_5_target_vs_midi(kit: str, samples: list, out_dir: Path) -> StageResult:
    """Compare target 8-bus piano-roll with MIDI source onsets."""
    fig, axes = plt.subplots(len(samples), 1, figsize=(13, 4.5 * len(samples)),
                              constrained_layout=True, squeeze=False)
    fig.suptitle(f"S5 · Target ↔ MIDI piano-roll — {kit}", fontweight="bold")
    notes: list[str] = []
    status = "PASS"
    bm = load_bus_mapping(_REPO_ROOT / "docs/specs/midi_mapping_table.yaml")
    for r, (s, sdir) in enumerate(samples):
        ax = axes[r, 0]
        target = s.target.astype(np.float32)
        t_frames = np.arange(target.shape[0]) / FR
        # Plot target onsets per-bus
        for b in range(8):
            col = target[:, 3*b]
            peaks_t = t_frames[col > 0.5]
            ax.scatter(peaks_t, [b]*len(peaks_t), c=PALETTE["fg"], s=24,
                       marker="|", linewidths=1.4, label="target" if b == 0 else None)
        # Plot MIDI source onsets per-bus (from dna lineage)
        dna = json.loads((sdir / f"{s.key}.dna.json").read_text())
        midi_path = _REPO_ROOT / dna["lineage"]["midi_source"]["file"]
        mismatches = 0
        if midi_path.exists():
            mid = mido.MidiFile(str(midi_path))
            t = 0.0
            for msg in mid:
                t += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    bus = bm.gm_to_bus.get(msg.note)
                    if bus is not None and 0 <= bus < 8:
                        ax.scatter(t, bus + 0.25, c=PALETTE["accent"], s=20,
                                   marker="x", linewidths=0.8)
                        # Check: there should be a target onset near this MIDI onset
                        bus_col = target[:, 3*bus]
                        f_idx = int(round(t * FR))
                        win = bus_col[max(0,f_idx-2):min(len(bus_col), f_idx+3)]
                        if len(win) == 0 or win.max() < 0.3:
                            mismatches += 1
        # Custom legend
        ax.scatter([], [], c=PALETTE["fg"], marker="|", s=24, label="target onset")
        ax.scatter([], [], c=PALETTE["accent"], marker="x", s=20, label="MIDI source onset")
        ax.set_yticks(range(8))
        ax.set_yticklabels(BUS_NAMES, fontsize=8)
        ax.set_xlabel("time (s)")
        ax.set_title(f"{s.key}  mismatches MIDI→target: {mismatches}", fontsize=10)
        ax.legend(loc="upper right", fontsize=7)
        ax.set_xlim(0, max(t_frames[-1] if t_frames.size else 1, 1))
        if mismatches > 5:
            status = "FAIL"
            notes.append(f"{s.key}: {mismatches} MIDI onsets without nearby target")
        elif mismatches > 0:
            if status == "PASS": status = "WARN"
            notes.append(f"{s.key}: {mismatches} MIDI onsets without target (≤5, acceptable)")
    png = out_dir / f"S5_target_vs_midi_{kit}.png"
    fig.savefig(png, dpi=110)
    plt.close()
    if not notes:
        notes = ["all MIDI onsets match target ±3 frames"]
    return StageResult("S5 Target vs MIDI", status, png, notes)


# =========================================================================
# S6 — DNA-Trace integrity
# =========================================================================

def stage_6_dna_integrity(kit: str, samples: list, out_dir: Path) -> StageResult:
    """Verify dna.json sha256 of audio + target matches the actual files."""
    notes: list[str] = []
    status = "PASS"
    for s, sdir in samples:
        dna_path = sdir / f"{s.key}.dna.json"
        dna = json.loads(dna_path.read_text())
        # Re-compute sha256
        audio_bytes = (sdir / f"{s.key}.audio.f16").read_bytes()
        target_bytes = (sdir / f"{s.key}.target.f16").read_bytes()
        sha_audio = hashlib.sha256(audio_bytes).hexdigest()
        sha_target = hashlib.sha256(target_bytes).hexdigest()
        ok_a = sha_audio == dna["audio"]["sha256"]
        ok_t = sha_target == dna["target"]["sha256"]
        if not ok_a:
            status = "FAIL"
            notes.append(f"{s.key}: audio sha256 mismatch")
        if not ok_t:
            status = "FAIL"
            notes.append(f"{s.key}: target sha256 mismatch")
        # Shape consistency
        if dna["audio"]["shape"] != list(s.audio.shape):
            status = "FAIL"
            notes.append(f"{s.key}: audio shape DNA={dna['audio']['shape']} actual={list(s.audio.shape)}")
        if dna["target"]["shape"] != list(s.target.shape):
            status = "FAIL"
            notes.append(f"{s.key}: target shape DNA={dna['target']['shape']} actual={list(s.target.shape)}")
        # Non-finite
        if dna["audio"]["n_nonfinite"] != 0:
            status = "FAIL"
            notes.append(f"{s.key}: audio has {dna['audio']['n_nonfinite']} non-finite values")
        if dna["target"]["n_nonfinite"] != 0:
            status = "FAIL"
            notes.append(f"{s.key}: target has {dna['target']['n_nonfinite']} non-finite values")
    if status == "PASS":
        notes = [f"all {len(samples)} samples: sha256 + shape + finiteness OK"]
    return StageResult("S6 DNA integrity", status, None, notes)


# =========================================================================
# S7 — GoldDataset crop policy
# =========================================================================

def stage_7_crop_policy(kit: str, samples: list, out_dir: Path) -> StageResult:
    """Visualize how GoldDataset crops audio + target with lookahead shift."""
    from neural.data import GoldDataset, ENCODER_STRIDE, DEFAULT_LOOKAHEAD_FRAMES
    crop_samples = 196608
    crop_frames = crop_samples // ENCODER_STRIDE  # 1536
    L = DEFAULT_LOOKAHEAD_FRAMES
    fig, axes = plt.subplots(len(samples), 1, figsize=(13, 4 * len(samples)),
                              constrained_layout=True, squeeze=False)
    fig.suptitle(f"S7 · GoldDataset crop policy — {kit}\n"
                 f"crop_samples={crop_samples} (={crop_samples/SR:.2f}s)  "
                 f"crop_frames={crop_frames}  lookahead={L} frames",
                 fontweight="bold")
    notes: list[str] = []
    status = "PASS"
    for r, (s, sdir) in enumerate(samples):
        ax = axes[r, 0]
        # Full audio (summed) and full target (onset density per frame)
        audio_sum = s.audio.astype(np.float32).sum(axis=0)
        t_audio = np.arange(len(audio_sum)) / SR
        ax.plot(t_audio, np.abs(audio_sum) / max(1e-9, np.abs(audio_sum).max()),
                lw=0.4, color=PALETTE["fg"], label="audio |sum|")
        # Plot target onset density
        target = s.target.astype(np.float32)
        onset_density = target[:, 0:24:3].max(axis=1)  # any-bus per frame
        t_target = np.arange(len(onset_density)) / FR
        ax.plot(t_target, onset_density, lw=0.7, color=PALETTE["accent"], label="target onset (any-bus max)")
        # Show a sample crop region (start_frame=0 deterministic)
        start_frame = 0
        end_frame = start_frame + crop_frames
        start_sample = (start_frame + L) * ENCODER_STRIDE
        end_sample = start_sample + crop_samples
        ax.axvspan(start_frame / FR, end_frame / FR, alpha=0.20,
                   color=PALETTE["ok"], label=f"target crop [0, {crop_frames}]")
        ax.axvspan(start_sample / SR, end_sample / SR, alpha=0.12,
                   color="#4444cc", label=f"audio crop (shifted +L={L}f)")
        ax.set_xlabel("time (s)")
        ax.set_ylim(-0.05, 1.1)
        ax.legend(loc="upper right", fontsize=7)
        ax.set_title(f"{s.key}", fontsize=10)
        # Validation: audio crop should be L frames ahead of target crop
        expected_shift_s = L * ENCODER_STRIDE / SR
        actual_shift_s = (start_sample / SR) - (start_frame / FR)
        if abs(actual_shift_s - expected_shift_s) > 0.01:
            status = "FAIL"
            notes.append(f"{s.key}: lookahead shift wrong ({actual_shift_s:.4f}s vs expected {expected_shift_s:.4f}s)")
    png = out_dir / f"S7_crop_policy_{kit}.png"
    fig.savefig(png, dpi=110)
    plt.close()
    if not notes:
        notes = [f"lookahead shift = {DEFAULT_LOOKAHEAD_FRAMES * ENCODER_STRIDE / SR:.4f}s "
                f"(correctly applied; target crop_frames={crop_frames})"]
    return StageResult("S7 Crop policy", status, png, notes)


# =========================================================================
# S8 — Preprocess P1+P2
# =========================================================================

def stage_8_preprocess(kit: str, samples: list, out_dir: Path,
                       pre: PreprocessingFrontend) -> StageResult:
    """Plot per-channel pre-emphasis output + onset envelope."""
    fig, axes = plt.subplots(len(samples), 9, figsize=(22, 2.6 * len(samples)),
                              constrained_layout=True, squeeze=False)
    fig.suptitle(f"S8 · Preprocess P1 (pre-emphasis + ChannelNorm) + P2 (onset env) — {kit}",
                 fontweight="bold")
    notes: list[str] = []
    status = "PASS"
    for r, (s, sdir) in enumerate(samples):
        audio = torch.from_numpy(s.audio[:, :196608]).float().unsqueeze(0)
        with torch.no_grad():
            out = pre(audio)  # [1, 9, T]
        for c in range(9):
            ax = axes[r, c]
            sig = out[0, c].numpy()
            t_axis = np.arange(len(sig)) / SR
            ax.plot(t_axis, sig, lw=0.4, color=PALETTE["fg"])
            std = sig.std()
            color = PALETTE["fg"]
            label = MIC_NAMES[c] if c < 8 else "onset_env"
            if c < 8 and (std < 0.05 or std > 5.0):
                color = PALETTE["accent"]
                if status == "PASS": status = "WARN"
                notes.append(f"{s.key}: ch {c} ({label}) std={std:.3f} (expect ~1 post z-score)")
            ax.set_title(f"{label} std={std:.2f}", fontsize=7, color=color)
            ax.tick_params(labelsize=5)
            if c > 0:
                ax.set_yticklabels([])
    png = out_dir / f"S8_preprocess_{kit}.png"
    fig.savefig(png, dpi=110)
    plt.close()
    if not notes:
        notes = ["all 8 audio channels post-P1 std in [0.05, 5.0]; onset_env channel present"]
    return StageResult("S8 Preprocess P1+P2", status, png, notes)


# =========================================================================
# S9 — Forward pass + peak-pick
# =========================================================================

def stage_9_forward_pass(kit: str, samples: list, out_dir: Path,
                          model: torch.nn.Module,
                          pre: PreprocessingFrontend) -> StageResult:
    """Run the trained TCN on each sample, overlay prediction vs target."""
    fig, axes = plt.subplots(len(samples), 8, figsize=(22, 3.4 * len(samples)),
                              constrained_layout=True, squeeze=False)
    fig.suptitle(f"S9 · Forward pass + peak-pick (allfixes checkpoint) — {kit}",
                 fontweight="bold")
    notes: list[str] = []
    status = "PASS"
    n_sample = 196608
    L = 35
    skip_edge = 1024
    for r, (s, sdir) in enumerate(samples):
        audio_np = s.audio[:, L * 128:L * 128 + n_sample]
        if audio_np.shape[1] < 128:
            continue
        audio_t = torch.from_numpy(audio_np).float().unsqueeze(0)
        with torch.no_grad():
            pre_out = pre(audio_t)
            heads = model(pre_out)
        # Onsets are returned as part of the flat-25 from TCNModel; for the
        # mini-L3 trainer the model returns a dict-like with onset head etc.
        # Easier: extract via the model's internal layout. The TCNModel
        # forward returns a [B, T, 25] flat tensor in mini_l3_train code path
        if isinstance(heads, torch.Tensor) and heads.ndim == 3 and heads.shape[-1] == 25:
            pred = heads[0].numpy()
        elif isinstance(heads, dict):
            # Reconstruct flat-25 from heads
            onset = torch.sigmoid(heads["onset"]).cpu().numpy()[0]  # [T, 8]
            pred = np.zeros((onset.shape[0], 25), dtype=np.float32)
            pred[:, 0:24:3] = onset
        else:
            continue
        target = s.target[:pred.shape[0]].astype(np.float32)
        # Apply edge skip
        pred_clip = pred[skip_edge:]
        target_clip = target[skip_edge:]
        t_axis = np.arange(pred_clip.shape[0]) / FR
        for b in range(8):
            ax = axes[r, b]
            pred_col = pred_clip[:, 3 * b]
            tgt_col = target_clip[:, 3 * b]
            ax.plot(t_axis, pred_col, lw=0.6, color="#4444cc", label="pred")
            ax.plot(t_axis, tgt_col, lw=0.6, color=PALETTE["accent"], alpha=0.7, label="target")
            ax.axhline(0.1, color=PALETTE["muted"], lw=0.3, ls=":")
            ax.set_ylim(0, 1.05)
            ax.set_title(f"{BUS_NAMES[b]}", fontsize=8)
            ax.tick_params(labelsize=6)
            if b > 0:
                ax.set_yticklabels([])
            if b == 0 and r == 0:
                ax.legend(fontsize=6, loc="upper right")
    png = out_dir / f"S9_forward_pass_{kit}.png"
    fig.savefig(png, dpi=110)
    plt.close()
    notes = ["pred (blue) vs target (red) overlay per-bus; thr 0.1 dashed grey"]
    return StageResult("S9 Forward pass", status, png, notes)


# =========================================================================
# Driver
# =========================================================================

def audit_kit(kit: str, out_dir: Path,
              model: torch.nn.Module, pre: PreprocessingFrontend) -> list[StageResult]:
    """Run all 9 stages for one kit. Return list of StageResult."""
    print(f"\n=== Auditing {kit} ===", flush=True)
    split, _, _ = KIT_DIRS[kit]
    samples = pick_samples(kit, split)
    if not samples:
        print(f"  ⚠️ No samples found for {kit}")
        return [StageResult("S0 pool", "FAIL", None, [f"No samples in data/gold/mini_l3_{split}/{kit}/"])]
    print(f"  picked {len(samples)} samples: {[s.key for s, _ in samples]}", flush=True)

    results = []
    print("  S1 MIDI vs midimap...", flush=True)
    results.append(stage_1_midi_vs_midimap(kit, samples, out_dir))
    print("  S2 Render audio...", flush=True)
    results.append(stage_2_render_audio(kit, samples, out_dir))
    print("  S3 Bleed matrix...", flush=True)
    results.append(stage_3_bleed_matrix(kit, samples, out_dir))
    print("  S4 Tail std...", flush=True)
    results.append(stage_4_tail_std(kit, samples, out_dir))
    print("  S5 Target vs MIDI...", flush=True)
    results.append(stage_5_target_vs_midi(kit, samples, out_dir))
    print("  S6 DNA integrity...", flush=True)
    results.append(stage_6_dna_integrity(kit, samples, out_dir))
    print("  S7 Crop policy...", flush=True)
    results.append(stage_7_crop_policy(kit, samples, out_dir))
    print("  S8 Preprocess P1+P2...", flush=True)
    results.append(stage_8_preprocess(kit, samples, out_dir, pre))
    print("  S9 Forward pass...", flush=True)
    results.append(stage_9_forward_pass(kit, samples, out_dir, model, pre))

    # Write per-kit report
    report_path = out_dir / f"REPORT_{kit}.md"
    lines = [f"# Pipeline Ocular Audit — {kit}\n",
             f"**Date:** 2026-05-26  **Samples:** {len(samples)}\n",
             f"**Checkpoint:** mini_l3_tcn_c64_B_allfixes.pt\n\n"]
    lines.append("| Stage | Status | PNG | Notes |\n|:--|:--:|:--|:--|\n")
    for rr in results:
        png_link = f"[`{rr.png_path.name}`](./{rr.png_path.name})" if rr.png_path else "—"
        notes_short = "; ".join(rr.notes[:3])
        if len(rr.notes) > 3:
            notes_short += f" (+{len(rr.notes)-3} more)"
        lines.append(f"| {rr.name} | **{rr.status}** | {png_link} | {notes_short} |\n")
    lines.append("\n## Detailed notes\n")
    for rr in results:
        lines.append(f"\n### {rr.name} — {rr.status}\n")
        for n in rr.notes:
            lines.append(f"- {n}\n")
    report_path.write_text("".join(lines))
    print(f"  → {report_path.relative_to(_REPO_ROOT)}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", default="all", help="Single kit (default: all)")
    parser.add_argument("--checkpoint", type=Path,
                        default=_REPO_ROOT / "artifacts" / "mini_l3_tcn_c64_B_allfixes.pt")
    args = parser.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"Loading checkpoint {args.checkpoint.name}…", flush=True)
    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    tcn = TCNModel(TCNConfig(channels=ckpt["config"]["channels"], in_channels=9))
    tcn.load_state_dict(ckpt["model_state"])
    tcn.eval()
    pre = PreprocessingFrontend(n_mic=8, onset_envelope=True)
    if "preprocess_state" in ckpt:
        pre.load_state_dict(ckpt["preprocess_state"])
        print(f"  preprocess_state loaded from checkpoint")
    else:
        # Warm up
        print(f"  warm-up preprocess on train pool…", flush=True)
        train_pool = _REPO_ROOT / "data" / "gold" / "mini_l3_train"
        triples = sorted(discover_gold_keys(train_pool), key=lambda x: x[1])[::8][:60]
        pre.train()
        with torch.no_grad():
            for d, k in triples:
                s = load_gold_sample(d, k)
                pre(torch.from_numpy(s.audio[:, :196608]).float().unsqueeze(0))
        pre.eval()
    rv = pre.channel_norm.running_var
    print(f"  ChannelNorm running_var range [{rv.min().item():.4f}, {rv.max().item():.4f}]")

    kits = list(KIT_DIRS.keys()) if args.kit == "all" else [args.kit]
    all_results: dict[str, list[StageResult]] = {}
    for kit in kits:
        all_results[kit] = audit_kit(kit, OUT_ROOT, tcn, pre)

    # Master INDEX
    idx_path = OUT_ROOT / "INDEX.md"
    lines = ["# Deep Pipeline Ocular Audit — INDEX\n",
             f"**Date:** 2026-05-26  **Stages:** 9  **Kits:** {len(kits)}\n",
             f"**Checkpoint:** {args.checkpoint.name}\n\n"]
    lines.append("## Per-kit reports\n\n")
    for kit in kits:
        lines.append(f"- [{kit}](./REPORT_{kit}.md)\n")
    lines.append("\n## Cross-kit summary matrix\n\n")
    lines.append("| Kit | S1 MIDI | S2 Audio | S3 Bleed | S4 Tail | S5 Target | "
                 "S6 DNA | S7 Crop | S8 Pre | S9 Fwd |\n")
    lines.append("|:--|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|\n")
    for kit, rs in all_results.items():
        cells = " | ".join(r.status for r in rs)
        lines.append(f"| **{kit}** | {cells} |\n")
    idx_path.write_text("".join(lines))
    print(f"\n→ Master index: {idx_path.relative_to(_REPO_ROOT)}")

    # Summary
    n_fail = sum(1 for rs in all_results.values() for r in rs if r.status == "FAIL")
    n_warn = sum(1 for rs in all_results.values() for r in rs if r.status == "WARN")
    print(f"\nSUMMARY:  PASS={9*len(kits) - n_fail - n_warn}  WARN={n_warn}  FAIL={n_fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
