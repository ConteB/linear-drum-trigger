#!/usr/bin/env python3
"""Build a joint Gold dataset (baseline ∪ augmented) for T1-E follow-up #2.

Uses symlinks (no extra disk space) — every sample of ``--pool-a`` is
exposed as-is, every sample of ``--pool-b`` is exposed with a ``-AUG``
suffix added to the filename basename (so the two collide-free keys
live side by side in the joint directory).

The DNA's ``key`` field is *not* mutated — :func:`load_gold_sample`
trusts the filename, not the embedded key.

Usage:
    PYTHONPATH=src .venv/bin/python tools/t1f_build_joint_dataset.py \
        --pool-a data/gold/mix_2026-05-24 \
        --pool-b data/gold/mix_2026-05-24_aug_v2 \
        --out    data/gold/mix_2026-05-24_joint \
        --suffix-b -AUG
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def _link(src: Path, dst: Path) -> None:
    """Create a relative symlink ``dst -> src`` (idempotent)."""
    if dst.exists() or dst.is_symlink():
        return
    rel_src = src.resolve()
    dst.symlink_to(rel_src)


def _bucket_files(pool: Path) -> dict[str, list[Path]]:
    """Group every ``.{audio.f16|target.f16|dna.json}`` of ``pool`` by key."""
    out: dict[str, list[Path]] = {}
    for f in pool.glob("*.*"):
        name = f.name
        for ext in (".dna.json", ".audio.f16", ".target.f16"):
            if name.endswith(ext):
                key = name.removesuffix(ext)
                out.setdefault(key, []).append(f)
                break
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pool-a", type=Path, required=True,
                   help="Primary Gold pool (no suffix)")
    p.add_argument("--pool-b", type=Path, required=True,
                   help="Augmented Gold pool (filename basename gets --suffix-b)")
    p.add_argument("--out", type=Path, required=True,
                   help="Joint pool directory")
    p.add_argument("--suffix-b", default="-AUG",
                   help="Suffix added to pool-b filenames (default '-AUG')")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()

    for pool in (args.pool_a, args.pool_b):
        if not pool.exists():
            print(f"FATAL: pool {pool} does not exist", file=sys.stderr)
            return 1

    if args.out.exists():
        if not args.overwrite:
            print(f"FATAL: --out {args.out} exists (pass --overwrite)",
                  file=sys.stderr)
            return 1
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)

    # Pool A — straight symlink.
    a_buckets = _bucket_files(args.pool_a)
    for _key, files in a_buckets.items():
        for f in files:
            _link(f, args.out / f.name)
    n_a = len(a_buckets)

    # Pool B — symlink with suffix.
    b_buckets = _bucket_files(args.pool_b)
    for key, files in b_buckets.items():  # noqa: B007 — key used in inner loop
        for f in files:
            # Replace the key inside the filename with key+suffix while
            # keeping the trailing extension(s).
            for ext in (".dna.json", ".audio.f16", ".target.f16"):
                if f.name.endswith(ext):
                    new_name = f"{key}{args.suffix_b}{ext}"
                    _link(f, args.out / new_name)
                    break
    n_b = len(b_buckets)

    print(f"joint pool : {args.out}")
    print(f"  from {args.pool_a}: {n_a} sample (as-is)")
    print(f"  from {args.pool_b}: {n_b} sample (suffix '{args.suffix_b}')")
    print(f"  total      : {n_a + n_b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
