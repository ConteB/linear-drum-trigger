#!/usr/bin/env python3
"""T1-E ablation step — apply the audio_augment pipeline to the mix Gold.

Walks ``data/gold/mix_2026-05-24/``, runs variant 1 of
:func:`data_engineering.audio_augment.apply_audio_augmentation` on every
sample's audio, and writes the augmented triple to
``data/gold/mix_2026-05-24_aug/``. The target.f16 and dna.json files are
copied unchanged (the augmentation is audio-only — the labels stay valid
by construction, R1 guard).

Output keys *match* the input keys, so the T1-B trainer can be pointed
at the augmented pool with the same deterministic holdout split.

Usage:
    PYTHONPATH=src .venv/bin/python tools/t1e_apply_audio_aug.py \
        --in  data/gold/mix_2026-05-24 \
        --out data/gold/mix_2026-05-24_aug \
        --master-seed 20260524
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from data_engineering.audio_augment import (  # noqa: E402
    AudioAugmentError,
    apply_audio_augmentation,
)


def _load_audio(path: Path, n_mic: int = 8) -> np.ndarray:
    """Load ``audio.f16`` raw little-endian into ``[n_mic, n_sample]``."""
    buf = np.frombuffer(path.read_bytes(), dtype=np.float16)
    if buf.size % n_mic != 0:
        raise ValueError(
            f"{path}: byte count {buf.nbytes} not divisible by n_mic*2={n_mic*2}"
        )
    return buf.reshape(n_mic, -1).astype(np.float16, copy=True)


def _save_audio(audio: np.ndarray, path: Path) -> None:
    """Write the float16 audio buffer back (little-endian raw)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    audio.astype(np.float16, copy=False).tobytes()
    path.write_bytes(audio.astype(np.float16, copy=False).tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--in", dest="in_dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--master-seed", type=int, default=20260524)
    parser.add_argument("--variant", type=int, default=1,
                        help="variant_idx for the audio_augment pipeline "
                              "(default 1; 0 would be identity)")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--noise-db-fs", type=float, default=-50.0)
    parser.add_argument("--gain-range-db", type=float, nargs=2,
                        default=[-6.0, 6.0])
    parser.add_argument("--mic-balance-range-db", type=float, nargs=2,
                        default=[-3.0, 3.0])
    args = parser.parse_args()

    if not args.in_dir.exists():
        print(f"FATAL: in_dir {args.in_dir} does not exist", file=sys.stderr)
        return 1
    if args.out.exists():
        if not args.overwrite:
            print(f"FATAL: out_dir {args.out} already exists (pass --overwrite)",
                  file=sys.stderr)
            return 1
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)

    dna_paths = sorted(args.in_dir.glob("*.dna.json"))
    if not dna_paths:
        print(f"FATAL: no *.dna.json found in {args.in_dir}", file=sys.stderr)
        return 1

    print(f"[T1-E] in       = {args.in_dir}")
    print(f"[T1-E] out      = {args.out}")
    print(f"[T1-E] samples  = {len(dna_paths)}")
    print(f"[T1-E] variant  = {args.variant} "
          f"(master_seed={args.master_seed})")

    n_ok = 0
    n_fail = 0
    started = time.monotonic()
    for i, dna_path in enumerate(dna_paths):
        key = dna_path.name.removesuffix(".dna.json")
        audio_in = args.in_dir / f"{key}.audio.f16"
        target_in = args.in_dir / f"{key}.target.f16"
        if not audio_in.exists() or not target_in.exists():
            print(f"  ✗ [{i+1}/{len(dna_paths)}] {key}: triple incomplete",
                  flush=True)
            n_fail += 1
            continue

        try:
            audio = _load_audio(audio_in)
            augmented = apply_audio_augmentation(
                audio,
                sample_key=key,
                variant_idx=args.variant,
                master_seed=args.master_seed,
                noise_db_fs=args.noise_db_fs,
                gain_range_db=tuple(args.gain_range_db),
                mic_balance_range_db=tuple(args.mic_balance_range_db),
            )
        except (AudioAugmentError, ValueError) as exc:
            print(f"  ✗ [{i+1}/{len(dna_paths)}] {key}: "
                  f"{type(exc).__name__}: {exc}", flush=True)
            n_fail += 1
            continue

        # Write the augmented audio + copy target unchanged.
        audio_out_path = args.out / f"{key}.audio.f16"
        _save_audio(augmented, audio_out_path)
        shutil.copy2(target_in, args.out / f"{key}.target.f16")

        # Recompute the audio sha256 + non-finite count and patch the DNA.
        # The renderer pipeline relies on these for `validate_dna_json` —
        # leaving them stale would trip the validator at load time.
        audio_bytes = audio_out_path.read_bytes()
        new_sha = hashlib.sha256(audio_bytes).hexdigest()
        n_nonfinite = int((~np.isfinite(augmented.astype(np.float32))).sum())
        dna = json.loads(dna_path.read_text())
        dna.setdefault("audio", {})["sha256"] = new_sha
        dna["audio"]["n_nonfinite"] = n_nonfinite
        # Mark the augmentation lineage (DOSSIER §3.6) for traceability.
        dna.setdefault("lineage", {})["audio_augment"] = {
            "variant_idx": args.variant,
            "master_seed": args.master_seed,
            "noise_db_fs": args.noise_db_fs,
            "gain_range_db": list(args.gain_range_db),
            "mic_balance_range_db": list(args.mic_balance_range_db),
        }
        (args.out / f"{key}.dna.json").write_text(
            json.dumps(dna, indent=2, sort_keys=True), encoding="utf-8"
        )
        n_ok += 1

        if (i + 1) % args.log_every == 0:
            elapsed = time.monotonic() - started
            rate = (i + 1) / max(elapsed, 1e-9)
            eta = (len(dna_paths) - (i + 1)) / max(rate, 1e-9)
            print(f"  [{i+1}/{len(dna_paths)}] OK · {rate:.1f} sample/s · "
                  f"ETA {eta:.1f} s", flush=True)

    elapsed = time.monotonic() - started
    print("=" * 72)
    print(f"DONE — {n_ok} OK, {n_fail} failed, elapsed {elapsed:.1f} s")
    print(f"        output: {args.out}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
