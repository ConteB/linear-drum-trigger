"""F0-T4c B6b — scan a Gold pool and emit per-bus `pos_weight` tuple.

Reads every Gold sample under ``--pool-root``, counts how many frames carry an
onset (target column ``3b`` > ``--onset-threshold``) per bus ``b ∈ [0, 8)``,
then computes

    density[b] = positives[b] / total_frames
    pos_weight[b] = min(POS_WEIGHT_CAP, (1 - density[b]) / max(density[b], 1e-6))

(POS_WEIGHT_CAP = 1000 — see :data:`neural.loss.POS_WEIGHT_CAP`).

Output:

* **stdout** — a Python literal ready to paste into ``LossConfig(pos_weight=...)``;
* **JSON** at ``--out`` — full density + pos_weight + bus labels + sample counts,
  deterministic byte-for-byte (sorted keys, fixed precision).

Per-sample frame counts are also recorded; samples whose target is shorter than
``--min-frames`` are skipped (defensive — empty/tiny samples skew density).

Usage::

    python tools/scan_density.py \
        --pool-root data/gold/mix_2026-05-24 \
        --out artifacts/mix_2026-05-24_density.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

import numpy as np

# Make ``src/`` importable when this script is run from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.gold.dna_trace import validate_dna_json  # noqa: E402
from data_engineering.gold.gold_writer import TARGET_COLS  # noqa: E402
from neural.loss import N_BUSES, POS_WEIGHT_CAP  # noqa: E402

#: Canonical bus labels — must match F0-T2a §3.3 / midi_mapping_table.yaml.
BUS_LABELS: tuple[str, ...] = (
    "kick",
    "snare",
    "hihat",
    "tom_hi_mid",
    "floor_tom",
    "ride",
    "crash_a",
    "crash_b_misc",
)


def _iter_targets(pool_root: Path) -> Iterable[tuple[str, np.ndarray]]:
    """Yield ``(key, target_array)`` pairs from every Gold sample under ``pool_root``.

    Validates the DNA integrity block — fails loud (``ValueError``) on tamper.
    """
    for dna_path in sorted(pool_root.rglob("*.dna.json")):
        key = dna_path.name[: -len(".dna.json")]
        target_path = dna_path.parent / f"{key}.target.f16"
        audio_path = dna_path.parent / f"{key}.audio.f16"
        if not target_path.is_file() or not audio_path.is_file():
            raise FileNotFoundError(
                f"incomplete triple for key {key!r} under {dna_path.parent}"
            )
        dna = json.loads(dna_path.read_text(encoding="utf-8"))
        t_shape = dna["target"]["shape"]
        a_shape = dna["audio"]["shape"]
        if len(t_shape) != 2 or t_shape[1] != TARGET_COLS:
            raise ValueError(f"{key}: malformed target shape {t_shape}")
        target = np.fromfile(target_path, dtype="<f2").reshape(t_shape)
        audio = np.fromfile(audio_path, dtype="<f2").reshape(a_shape)
        # Integrity check (sha256 + non-finite count must match dna.json).
        validate_dna_json(dna, audio=audio, target=target)
        yield key, target.astype(np.float32, copy=False)


def scan_density(
    pool_root: Path,
    *,
    onset_threshold: float = 0.5,
    min_frames: int = 16,
) -> dict[str, object]:
    """Compute per-bus density and pos_weight on ``pool_root``.

    Returns a dict with the schema below; also suitable as the JSON payload of
    :func:`write_report`.
    """
    if not pool_root.is_dir():
        raise FileNotFoundError(f"pool_root not a directory: {pool_root}")

    n_frame_total = 0
    n_pos_per_bus = np.zeros(N_BUSES, dtype=np.int64)
    sample_index: list[dict[str, object]] = []
    n_skipped = 0

    for key, target in _iter_targets(pool_root):
        if target.shape[0] < min_frames:
            n_skipped += 1
            continue
        onset = target[:, 0:24:3]  # [n_frame, 8]
        pos = (onset > onset_threshold).sum(axis=0).astype(np.int64)
        n_pos_per_bus += pos
        n_frame_total += target.shape[0]
        sample_index.append({
            "key": key,
            "n_frame": int(target.shape[0]),
            "positives_per_bus": pos.tolist(),
        })

    if n_frame_total == 0:
        raise ValueError(
            f"scan_density: no usable samples under {pool_root} "
            f"(min_frames={min_frames}, skipped={n_skipped})"
        )

    density = n_pos_per_bus / n_frame_total  # float64
    # Per-bus pos_weight = (1 - density) / max(density, 1e-6), capped.
    pos_weight = np.minimum(
        POS_WEIGHT_CAP,
        (1.0 - density) / np.maximum(density, 1e-6),
    )

    payload: dict[str, object] = {
        "pool_root": str(pool_root),
        "onset_threshold": onset_threshold,
        "min_frames": min_frames,
        "n_samples_used": len(sample_index),
        "n_samples_skipped": n_skipped,
        "n_frame_total": int(n_frame_total),
        "pos_weight_cap": POS_WEIGHT_CAP,
        "bus_labels": list(BUS_LABELS),
        "positives_per_bus": n_pos_per_bus.tolist(),
        "density_per_bus": [round(float(d), 6) for d in density],
        "pos_weight_per_bus": [round(float(w), 1) for w in pos_weight],
        "samples": sample_index,
    }
    return payload


def write_report(payload: dict[str, object], out: Path) -> None:
    """Persist the report deterministically (sorted keys, trailing newline)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def format_paste_literal(payload: dict[str, object]) -> str:
    """Return a one-line Python literal ready to paste into ``LossConfig(...)``."""
    weights = payload["pos_weight_per_bus"]
    assert isinstance(weights, list)
    return "pos_weight=(" + ", ".join(f"{w}" for w in weights) + ")"


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F0-T4c B6b — scan Gold pool, emit per-bus pos_weight."
    )
    parser.add_argument("--pool-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path,
                        help="JSON output path")
    parser.add_argument("--onset-threshold", type=float, default=0.5)
    parser.add_argument("--min-frames", type=int, default=16)
    args = parser.parse_args(argv)

    payload = scan_density(
        args.pool_root,
        onset_threshold=args.onset_threshold,
        min_frames=args.min_frames,
    )
    write_report(payload, args.out)
    print(f"[scan_density] wrote report → {args.out}")
    print(f"[scan_density] bus labels:   {payload['bus_labels']}")
    print(f"[scan_density] density:      {payload['density_per_bus']}")
    print(f"[scan_density] pos_weight:   {payload['pos_weight_per_bus']}")
    print(f"[scan_density] paste-ready:  {format_paste_literal(payload)}")
    print(f"[scan_density] n_samples_used={payload['n_samples_used']} "
          f"n_samples_skipped={payload['n_samples_skipped']} "
          f"n_frame_total={payload['n_frame_total']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
