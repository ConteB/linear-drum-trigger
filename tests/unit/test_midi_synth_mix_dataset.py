"""Layer-1 oracles for ``midi_synth.mix_dataset``.

The orchestrator must:

* compose the 70/15/15 mix from a synthetic GMD fixture + the deterministic
  rare/chaos generators;
* write 200 MIDI files (or whatever the requested counts sum to) plus a
  manifest.json;
* shuffle reproducibly per ``master_seed``;
* fail loud on missing GMD index, insufficient eligible rows, or output
  conflicts.

The GMD side is exercised against a fixture written by the test (a tiny CSV
+ a few real MIDI files copied from the rare-emphasis generator) — we don't
rely on the actual GMD download here.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from data_engineering.midi_synth._writer import write_events_to_midi
from data_engineering.midi_synth.mix_dataset import (
    DEFAULT_MASTER_SEED,
    MANIFEST_VERSION,
    MixDatasetError,
    MixManifestEntry,
    build_mix_dataset,
)
from data_engineering.midi_synth.rare_emphasis import generate_rare_emphasis_grooves


def _make_gmd_fixture(root: Path, n_grooves: int = 20) -> Path:
    """Create a fake GMD ``groove/`` directory with ``n_grooves`` MIDI files
    + a matching ``info.csv``. Reuses rare-emphasis grooves as fake GMD MIDIs."""
    groove_root = root / "groove"
    groove_root.mkdir(parents=True)
    grooves = generate_rare_emphasis_grooves(n=min(n_grooves, 30))
    rows: list[dict[str, str]] = []
    for i, g in enumerate(grooves):
        drummer = f"drummer{(i % 3) + 1}"
        session = f"session{(i % 2) + 1}"
        midi_rel = f"{drummer}/{session}/{i}_{g.name}_120_beat_4-4.mid"
        midi_path = groove_root / midi_rel
        write_events_to_midi(g, midi_path)
        rows.append({
            "drummer": drummer,
            "session": f"{drummer}/{session}",
            "id": f"{drummer}/{session}/{i}",
            "style": "rock/groove",
            "bpm": "120",
            "beat_type": "beat",
            "time_signature": "4-4",
            "midi_filename": midi_rel,
            "audio_filename": midi_rel.replace(".mid", ".wav"),
            "duration": "3.5",
            "split": "train",
        })
    # Pad with non-matching rows (3-4 time sig, eval split) — must be skipped.
    rows.append({
        "drummer": "drummer1", "session": "drummer1/session3",
        "id": "drummer1/session3/skip-time",
        "style": "rock", "bpm": "120", "beat_type": "beat",
        "time_signature": "3-4",
        "midi_filename": "drummer1/session3/skip.mid",
        "audio_filename": "drummer1/session3/skip.wav",
        "duration": "3.5", "split": "train",
    })
    rows.append({
        "drummer": "drummer2", "session": "drummer2/session1",
        "id": "drummer2/session1/skip-split",
        "style": "rock", "bpm": "120", "beat_type": "beat",
        "time_signature": "4-4",
        "midi_filename": "drummer2/session1/skip2.mid",
        "audio_filename": "drummer2/session1/skip2.wav",
        "duration": "3.5", "split": "test",
    })
    csv_path = groove_root / "info.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return groove_root


# ----------------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------------


def test_happy_path_writes_all_files(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=20)
    out = tmp_path / "mix"
    manifest = build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=out,
        n_gmd=10,
        n_rare=5,
        n_chaos=5,
    )
    assert len(manifest) == 20
    # All referenced MIDI files exist.
    for entry in manifest:
        assert (out / entry.rel_path).exists(), entry.rel_path


def test_manifest_json_is_written(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=10)
    out = tmp_path / "mix"
    build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=out,
        n_gmd=5,
        n_rare=2,
        n_chaos=2,
    )
    data = json.loads((out / "manifest.json").read_text())
    assert data["manifest_version"] == MANIFEST_VERSION
    assert data["counts"] == {"gmd": 5, "rare": 2, "chaos": 2, "total": 9}
    assert len(data["entries"]) == 9
    sources = {e["source"] for e in data["entries"]}
    assert sources == {"gmd", "rare", "chaos"}


def test_default_master_seed_constant() -> None:
    # CEO directive 2026-05-23, fine giornata.
    assert DEFAULT_MASTER_SEED == 20260524


# ----------------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------------


def test_shuffled_order_deterministic_same_seed(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=15)
    a = build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=tmp_path / "a",
        n_gmd=10, n_rare=3, n_chaos=3,
        master_seed=42,
    )
    b = build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=tmp_path / "b",
        n_gmd=10, n_rare=3, n_chaos=3,
        master_seed=42,
    )
    # Same order ⇒ same rel_paths in the same positions.
    assert [e.rel_path for e in a] == [e.rel_path for e in b]


def test_different_seed_produces_different_order(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=15)
    a = build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=tmp_path / "a",
        n_gmd=10, n_rare=3, n_chaos=3,
        master_seed=42,
    )
    b = build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=tmp_path / "b",
        n_gmd=10, n_rare=3, n_chaos=3,
        master_seed=43,
    )
    assert [e.rel_path for e in a] != [e.rel_path for e in b]


# ----------------------------------------------------------------------------
# Filtering: time_signature != 4-4 and split != train are skipped
# ----------------------------------------------------------------------------


def test_skips_non_4_4_and_non_train(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=20)
    manifest = build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=tmp_path / "mix",
        n_gmd=20, n_rare=0, n_chaos=0,
    )
    # The fixture has 2 skip rows on top of 20 grooves → eligible == 20.
    # If filtering broke we'd see the skip-time / skip-split paths in entries.
    rel_paths = [e.label for e in manifest]
    assert not any("skip-time" in p for p in rel_paths)
    assert not any("skip-split" in p for p in rel_paths)


def test_insufficient_eligible_raises(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=5)
    with pytest.raises(MixDatasetError, match="eligible"):
        build_mix_dataset(
            gmd_root=gmd_root,
            output_dir=tmp_path / "mix",
            n_gmd=10, n_rare=0, n_chaos=0,
        )


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------


def test_rejects_missing_info_csv(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(MixDatasetError, match="info.csv"):
        build_mix_dataset(
            gmd_root=tmp_path / "empty",
            output_dir=tmp_path / "mix",
            n_gmd=1, n_rare=0, n_chaos=0,
        )


def test_rejects_existing_output_dir(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=10)
    (tmp_path / "mix").mkdir()
    with pytest.raises(MixDatasetError, match="already exists"):
        build_mix_dataset(
            gmd_root=gmd_root,
            output_dir=tmp_path / "mix",
            n_gmd=5, n_rare=0, n_chaos=0,
        )


def test_overwrite_clears_existing(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=10)
    out = tmp_path / "mix"
    out.mkdir()
    (out / "stale.txt").write_text("stale")
    manifest = build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=out,
        n_gmd=5, n_rare=2, n_chaos=2,
        overwrite=True,
    )
    assert len(manifest) == 9
    assert not (out / "stale.txt").exists()


def test_rejects_negative_counts(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=5)
    with pytest.raises(MixDatasetError, match="non-negative"):
        build_mix_dataset(
            gmd_root=gmd_root,
            output_dir=tmp_path / "mix",
            n_gmd=-1, n_rare=0, n_chaos=0,
        )


def test_rejects_zero_total(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=5)
    with pytest.raises(MixDatasetError, match="at least one source"):
        build_mix_dataset(
            gmd_root=gmd_root,
            output_dir=tmp_path / "mix",
            n_gmd=0, n_rare=0, n_chaos=0,
        )


def test_rejects_n_rare_above_30(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=5)
    with pytest.raises(MixDatasetError, match="n_rare"):
        build_mix_dataset(
            gmd_root=gmd_root,
            output_dir=tmp_path / "mix",
            n_gmd=0, n_rare=31, n_chaos=0,
        )


def test_rejects_n_chaos_above_30(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=5)
    with pytest.raises(MixDatasetError, match="n_chaos"):
        build_mix_dataset(
            gmd_root=gmd_root,
            output_dir=tmp_path / "mix",
            n_gmd=0, n_rare=0, n_chaos=31,
        )


def test_filename_prefixes_are_globally_unique(tmp_path: Path) -> None:
    """The 4-digit ``{global_idx:04d}_`` prefix must be unique across all
    sources — otherwise the Gold barcode encoder (orchestrate._digit_token)
    extracts the same digit-run and 600 entries collide on ~10 keys."""
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=12)
    manifest = build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=tmp_path / "mix",
        n_gmd=10,
        n_rare=5,
        n_chaos=5,
    )
    # Every rel_path's filename starts with a 4-digit prefix.
    prefixes: list[str] = []
    for entry in manifest:
        name = entry.rel_path.split("/", 1)[1]  # strip "source/" prefix
        head4 = name[:4]
        assert head4.isdigit(), f"rel_path {entry.rel_path} missing 4-digit prefix"
        prefixes.append(head4)
    # All 20 prefixes must be distinct.
    assert len(set(prefixes)) == len(prefixes), f"duplicate prefixes: {prefixes}"


def test_manifest_entry_type(tmp_path: Path) -> None:
    gmd_root = _make_gmd_fixture(tmp_path / "gmd", n_grooves=5)
    manifest = build_mix_dataset(
        gmd_root=gmd_root,
        output_dir=tmp_path / "mix",
        n_gmd=2, n_rare=1, n_chaos=1,
    )
    assert all(isinstance(e, MixManifestEntry) for e in manifest)
    assert all(e.order_idx == i for i, e in enumerate(manifest))
