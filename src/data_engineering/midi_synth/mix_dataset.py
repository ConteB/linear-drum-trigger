"""Mix-dataset orchestrator — 140 GMD + 30 rare + 30 chaos (R&D, 2026-05-23).

Composes three sources into a single shuffled MIDI roster, written to disk for
``generate_local_rnd_dataset.py`` to consume:

* **GMD (Magenta Groove)** — 140 real human grooves sampled deterministically
  from ``info.csv``, filtered to ``time_signature=4-4`` and ``split=train``
  (the test/eval splits stay untouched for honest evaluation).
* **Rare emphasis** — 30 synthetic grooves with crash/china/ride/tom over-
  represented (see :mod:`midi_synth.rare_emphasis`).
* **Chaos** — 30 synthetic Machine-Gun Chaos grooves (see
  :mod:`midi_synth.chaos_generator`).

The output is a flat directory of 200 ``.mid`` files plus a JSON manifest
that records (a) the source of every entry, (b) the master seed, and (c) the
shuffled order — enough to bit-reproduce the dataset later.

Failure modes (fail-loud per ENGINEERING_STANDARDS §6):

* ``MixDatasetError`` — GMD info.csv missing / corrupt, requested counts
  exceed availability, output dir conflict, etc.
"""
from __future__ import annotations

import csv
import dataclasses
import json
import random
import shutil
import sys
from pathlib import Path
from typing import Final

from ._writer import write_events_to_midi
from .chaos_generator import generate_chaos_grooves
from .rare_emphasis import generate_rare_emphasis_grooves

#: Default master seed for the mix (CEO 2026-05-23, fine giornata).
DEFAULT_MASTER_SEED: Final[int] = 20260524

#: Default mix proportions (Decision CEO 2026-05-23 — "70/15/15").
DEFAULT_N_GMD: Final[int] = 140
DEFAULT_N_RARE: Final[int] = 30
DEFAULT_N_CHAOS: Final[int] = 30

#: Manifest version — bump on schema changes.
MANIFEST_VERSION: Final[str] = "1.0"


class MixDatasetError(ValueError):
    """Raised on malformed inputs / impossible mixes."""


@dataclasses.dataclass(frozen=True)
class MixManifestEntry:
    """One row of the mix manifest."""

    #: Shuffled position (0-indexed).
    order_idx: int
    #: Source layer: ``"gmd"`` | ``"rare"`` | ``"chaos"``.
    source: str
    #: Relative path under the output directory.
    rel_path: str
    #: Human label (for GMD this is the drummer/session id; for synth, the
    #: groove name from the generator).
    label: str

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def _read_gmd_index(gmd_root: Path) -> list[dict[str, str]]:
    """Parse ``gmd_root/info.csv`` and return rows as dicts.

    GMD root layout: ``<gmd_root>/info.csv`` + ``<gmd_root>/drummerN/...``.
    """
    csv_path = gmd_root / "info.csv"
    if not csv_path.exists():
        raise MixDatasetError(f"GMD info.csv not found at {csv_path}")
    with csv_path.open("r", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    if not rows:
        raise MixDatasetError(f"GMD info.csv is empty: {csv_path}")
    return rows


#: Maximum GMD groove duration in seconds (Decision 2026-05-24, R&D session).
#: Filter keeps the multi-mic DrumGizmo render under the OrbStack memory
#: budget (7.8 GB shared with macOS). Longer grooves go on Azure F2-T1.
GMD_MAX_DURATION_S: float = 6.0


def _select_gmd_subset(
    rows: list[dict[str, str]],
    *,
    n: int,
    rng: random.Random,
    gmd_root: Path,
    max_duration_s: float = GMD_MAX_DURATION_S,
) -> list[tuple[str, Path]]:
    """Filter + sample ``n`` GMD rows. Returns ``(label, midi_path)`` pairs.

    Filters:
    * ``time_signature == "4-4"`` (the only signature the target builder
      supports today).
    * ``split == "train"`` (test/eval stays untouched for honest evaluation).
    * ``duration <= max_duration_s`` — DrumGizmo multi-mic memory budget
      (the GMD p75 is ~38 s, far above the OrbStack envelope; the long-tail
      grooves will be picked up on Azure F2-T1 with no memory constraint).
    * the referenced MIDI file actually exists on disk.
    """
    eligible: list[tuple[str, Path]] = []
    for row in rows:
        if row.get("time_signature") != "4-4":
            continue
        if row.get("split") != "train":
            continue
        dur_str = row.get("duration") or "0"
        try:
            duration = float(dur_str)
        except ValueError:
            continue
        if duration > max_duration_s:
            continue
        midi_rel = row.get("midi_filename")
        if not midi_rel:
            continue
        midi_path = gmd_root / midi_rel
        if not midi_path.exists():
            continue
        label = row.get("id") or midi_rel
        eligible.append((label, midi_path))
    if len(eligible) < n:
        raise MixDatasetError(
            f"GMD has only {len(eligible)} eligible grooves "
            f"(4-4 + train + duration<={max_duration_s}s + on-disk), need {n}"
        )
    # Deterministic sort + sample.
    eligible.sort(key=lambda pair: pair[0])
    sampled = rng.sample(eligible, k=n)
    sampled.sort(key=lambda pair: pair[0])
    return sampled


def _slug(label: str) -> str:
    """Make a filename-safe slug from an arbitrary label."""
    cleaned = label.replace("/", "_").replace(" ", "_").replace(":", "_")
    # mido/DrumGizmo are tolerant but keep ASCII for cross-platform.
    return "".join(c for c in cleaned if c.isalnum() or c in "._-")


def build_mix_dataset(
    *,
    gmd_root: Path,
    output_dir: Path,
    n_gmd: int = DEFAULT_N_GMD,
    n_rare: int = DEFAULT_N_RARE,
    n_chaos: int = DEFAULT_N_CHAOS,
    master_seed: int = DEFAULT_MASTER_SEED,
    overwrite: bool = False,
) -> list[MixManifestEntry]:
    """Compose the 70/15/15 mix and write everything under ``output_dir``.

    Output layout::

        output_dir/
        ├── manifest.json          # this function's return value, serialised
        ├── gmd/                   # n_gmd copies of GMD MIDI files (renamed)
        ├── rare/                  # n_rare synthetic MIDI files
        └── chaos/                 # n_chaos synthetic MIDI files

    Parameters
    ----------
    gmd_root
        Path to the unzipped Magenta GMD ``groove/`` directory (containing
        ``info.csv`` and ``drummerN/`` subdirs).
    output_dir
        Destination directory. Will be created. Existing content blocks the
        run unless ``overwrite=True``.
    n_gmd, n_rare, n_chaos
        Per-source counts. Must each be non-negative; sum must be > 0.
    master_seed
        Seed for the GMD subset sampling and the final shuffle. The chaos
        generator uses its own seed (decoupled — same chaos grooves even if
        the mix seed changes).
    overwrite
        If True, ``output_dir`` is removed first.

    Returns
    -------
    list[MixManifestEntry]
        Manifest entries in shuffled order (also persisted to
        ``output_dir/manifest.json``).
    """
    if min(n_gmd, n_rare, n_chaos) < 0:
        raise MixDatasetError("per-source counts must be non-negative")
    total = n_gmd + n_rare + n_chaos
    if total == 0:
        raise MixDatasetError("at least one source must contribute")
    if n_rare > 30:
        raise MixDatasetError(f"n_rare={n_rare} exceeds available 30")
    if n_chaos > 30:
        raise MixDatasetError(f"n_chaos={n_chaos} exceeds available 30")

    if output_dir.exists():
        if not overwrite:
            raise MixDatasetError(
                f"output_dir {output_dir} already exists (pass overwrite=True)"
            )
        shutil.rmtree(output_dir)

    gmd_dir = output_dir / "gmd"
    rare_dir = output_dir / "rare"
    chaos_dir = output_dir / "chaos"
    for d in (gmd_dir, rare_dir, chaos_dir):
        d.mkdir(parents=True)

    # 1. GMD subset.
    rng = random.Random(master_seed)
    gmd_pairs: list[tuple[str, Path]] = []
    if n_gmd > 0:
        rows = _read_gmd_index(gmd_root)
        gmd_pairs = _select_gmd_subset(rows, n=n_gmd, rng=rng, gmd_root=gmd_root)

    # Filenames carry a 4-digit global sequence prefix. The Gold barcode
    # encoder (``orchestrate._digit_token``) extracts the *first* digit-run of
    # the MIDI filename for the ``midisrc`` segment; without a globally-unique
    # numeric prefix, GMD filenames like ``drummer1_session1_42.mid`` all
    # collide on ``001`` and 600 recipe entries overwrite themselves into
    # ~20 unique keys. With ``{global_idx:04d}_...`` prefix the token is the
    # last 3 digits of the 4-digit pad → unique across the 0-999 range
    # (we cap at 200 grooves total, so collisions are impossible by design).
    global_idx = 0

    gmd_entries: list[tuple[str, str, str]] = []  # (source, label, rel_path)
    for label, src_path in gmd_pairs:
        slug = _slug(label)
        dst_rel = f"gmd/{global_idx:04d}_{slug}.mid"
        dst_path = output_dir / dst_rel
        shutil.copy2(src_path, dst_path)
        gmd_entries.append(("gmd", label, dst_rel))
        global_idx += 1

    # 2. Rare emphasis.
    rare_entries: list[tuple[str, str, str]] = []
    if n_rare > 0:
        rare_grooves = generate_rare_emphasis_grooves(n=n_rare)
        for groove in rare_grooves:
            slug = _slug(groove.name)
            dst_rel = f"rare/{global_idx:04d}_{slug}.mid"
            write_events_to_midi(groove, output_dir / dst_rel)
            rare_entries.append(("rare", groove.name, dst_rel))
            global_idx += 1

    # 3. Chaos.
    chaos_entries: list[tuple[str, str, str]] = []
    if n_chaos > 0:
        chaos_grooves = generate_chaos_grooves(n=n_chaos)
        for groove in chaos_grooves:
            slug = _slug(groove.name)
            dst_rel = f"chaos/{global_idx:04d}_{slug}.mid"
            write_events_to_midi(groove, output_dir / dst_rel)
            chaos_entries.append(("chaos", groove.name, dst_rel))
            global_idx += 1

    # 4. Shuffle deterministically — same master_seed reproducible.
    all_entries = gmd_entries + rare_entries + chaos_entries
    shuffler = random.Random(master_seed ^ 0xC0FFEE)
    shuffler.shuffle(all_entries)

    manifest: list[MixManifestEntry] = [
        MixManifestEntry(order_idx=i, source=src, rel_path=path, label=label)
        for i, (src, label, path) in enumerate(all_entries)
    ]

    manifest_payload = {
        "manifest_version": MANIFEST_VERSION,
        "master_seed": master_seed,
        "counts": {
            "gmd": n_gmd,
            "rare": n_rare,
            "chaos": n_chaos,
            "total": total,
        },
        "entries": [e.to_dict() for e in manifest],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n"
    )
    return manifest


# ----------------------------------------------------------------------------
# CLI entry — for one-shot generation from the shell.
# ----------------------------------------------------------------------------


def _cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build the 70/15/15 mix dataset.")
    parser.add_argument("--gmd-root", required=True, type=Path,
                        help="Path to unzipped GMD groove/ directory")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Where to write the 200 MIDI files + manifest.json")
    parser.add_argument("--n-gmd", type=int, default=DEFAULT_N_GMD)
    parser.add_argument("--n-rare", type=int, default=DEFAULT_N_RARE)
    parser.add_argument("--n-chaos", type=int, default=DEFAULT_N_CHAOS)
    parser.add_argument("--master-seed", type=int, default=DEFAULT_MASTER_SEED)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = build_mix_dataset(
            gmd_root=args.gmd_root,
            output_dir=args.output_dir,
            n_gmd=args.n_gmd,
            n_rare=args.n_rare,
            n_chaos=args.n_chaos,
            master_seed=args.master_seed,
            overwrite=args.overwrite,
        )
    except MixDatasetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(manifest)} entries → {args.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
