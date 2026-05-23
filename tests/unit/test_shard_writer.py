"""Layer-1 unit oracles for the WebDataset shard writer (F0-T5).

Cover the F0-T5 §3 / §5 / §6 contract: shard naming, pack-on-fill rotation,
deterministic tar bytes, atomicity (``.tmp`` + rename), manifest schema,
SHA-256 integrity, resume from a prior manifest, and orphan ``.tmp`` cleanup.

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3).
"""
from __future__ import annotations

import json
import tarfile
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from data_engineering.gold.shard_writer import (
    MANIFEST_VERSION,
    TARGET_SHARD_BYTES,
    ShardManifest,
    ShardWriter,
    ShardWriterError,
    shard_name,
)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def sample_factory(tmp_path: Path) -> Callable[..., Path]:
    """Factory that writes a fresh sample triple into ``tmp_path/samples``."""
    samples = tmp_path / "samples"
    samples.mkdir()

    def _make(key: str, *, audio_bytes: int = 1024, target_bytes: int = 256) -> Path:
        (samples / f"{key}.audio.f16").write_bytes(b"A" * audio_bytes)
        (samples / f"{key}.target.f16").write_bytes(b"T" * target_bytes)
        (samples / f"{key}.dna.json").write_text(
            json.dumps({"key": key}), encoding="utf-8"
        )
        return samples

    return _make


def _add_samples(
    writer: ShardWriter, sample_dir: Path, keys: Iterable[str]
) -> list[str]:
    """Helper: push every key in ``keys`` through ``writer``."""
    pushed = list(keys)
    for k in pushed:
        writer.add_sample(k, sample_dir)
    return pushed


def _key(i: int, engine: str = "DGZ") -> str:
    """Generate a contract-shaped barcode key for tests."""
    return f"GMD{i:03d}-V0T0-{engine}-R0-L1-NONE"


# --------------------------------------------------------------------------
# shard_name — F0-T5 §5.1
# --------------------------------------------------------------------------
def test_shard_name_uses_six_padded_digits() -> None:
    """The naming pattern is ``gold-{split}-{index:06d}.tar`` (F0-T5 §5.1)."""
    assert shard_name("train", 0) == "gold-train-000000.tar"
    assert shard_name("val", 42) == "gold-val-000042.tar"
    assert shard_name("train", 999_999) == "gold-train-999999.tar"


def test_shard_name_rejects_unknown_split() -> None:
    """Only ``train`` / ``val`` are valid Gold splits (F0-T2a §3.6)."""
    with pytest.raises(ShardWriterError, match="split"):
        shard_name("holdout", 0)  # type: ignore[arg-type]


def test_shard_name_rejects_out_of_range_index() -> None:
    """Indices outside ``[0, 999_999]`` violate the naming pattern."""
    with pytest.raises(ShardWriterError, match="index"):
        shard_name("train", -1)
    with pytest.raises(ShardWriterError, match="index"):
        shard_name("train", 1_000_000)


# --------------------------------------------------------------------------
# ShardWriter — construction
# --------------------------------------------------------------------------
def test_writer_rejects_unknown_split(tmp_path: Path) -> None:
    """Construction fails loud on an invalid split."""
    with pytest.raises(ShardWriterError, match="split"):
        ShardWriter(tmp_path / "out", "holdout", recipe_matrix_seed=42)  # type: ignore[arg-type]


def test_writer_rejects_non_positive_target_bytes(tmp_path: Path) -> None:
    """A zero / negative threshold cannot drive pack-on-fill — fail loud."""
    with pytest.raises(ShardWriterError, match="target_shard_bytes"):
        ShardWriter(
            tmp_path / "out", "train",
            recipe_matrix_seed=42, target_shard_bytes=0,
        )
    with pytest.raises(ShardWriterError, match="target_shard_bytes"):
        ShardWriter(
            tmp_path / "out", "train",
            recipe_matrix_seed=42, target_shard_bytes=-1,
        )


def test_writer_rejects_negative_tail_s(tmp_path: Path) -> None:
    """``tail_s`` is a duration; negative values are nonsense — fail loud."""
    with pytest.raises(ShardWriterError, match="tail_s"):
        ShardWriter(
            tmp_path / "out", "train",
            recipe_matrix_seed=42, tail_s=-0.1,
        )


def test_writer_creates_out_dir(tmp_path: Path) -> None:
    """The destination directory is created if absent (no surprise crash)."""
    out = tmp_path / "shards" / "nested"
    ShardWriter(out, "train", recipe_matrix_seed=42)
    assert out.is_dir()


# --------------------------------------------------------------------------
# add_sample — argument validation & file checks
# --------------------------------------------------------------------------
def test_add_rejects_empty_key(tmp_path: Path, sample_factory) -> None:
    """An empty key is malformed — fail loud."""
    sample_factory(_key(0))  # exists but unused
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    with pytest.raises(ShardWriterError, match="key"):
        w.add_sample("", tmp_path / "samples")


def test_add_rejects_dotted_key(tmp_path: Path, sample_factory) -> None:
    """Dots in keys break WebDataset's extension splitting (F0-T2a §3.1)."""
    sample_factory(_key(0))
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    with pytest.raises(ShardWriterError, match="reserved"):
        w.add_sample("GMD.001-V0T0-DGZ-R0-L1-NONE", tmp_path / "samples")


def test_add_rejects_duplicate_key(tmp_path: Path, sample_factory) -> None:
    """Packing the same key twice in one writer is a bug — fail loud."""
    sample_dir = sample_factory(_key(0))
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    w.add_sample(_key(0), sample_dir)
    with pytest.raises(ShardWriterError, match="duplicate"):
        w.add_sample(_key(0), sample_dir)


def test_add_rejects_incomplete_triple(tmp_path: Path) -> None:
    """A sample missing one of the three files is incomplete — fail loud."""
    samples = tmp_path / "samples"
    samples.mkdir()
    key = _key(0)
    (samples / f"{key}.audio.f16").write_bytes(b"A" * 100)
    (samples / f"{key}.target.f16").write_bytes(b"T" * 50)
    # dna.json missing on purpose
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    with pytest.raises(ShardWriterError, match="missing"):
        w.add_sample(key, samples)


def test_add_after_close_fails_loud(tmp_path: Path, sample_factory) -> None:
    """A closed writer rejects further adds — no silent extension."""
    sample_dir = sample_factory(_key(0))
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    w.add_sample(_key(0), sample_dir)
    w.close()
    with pytest.raises(ShardWriterError, match="closed"):
        w.add_sample(_key(1), sample_dir)


# --------------------------------------------------------------------------
# Pack-on-fill rotation — F0-T5 §3
# --------------------------------------------------------------------------
def test_pack_on_fill_rotates_at_threshold(tmp_path: Path, sample_factory) -> None:
    """Crossing ``target_shard_bytes`` triggers a rotation; everything below
    a single threshold stays in one shard (F0-T5 §3)."""
    out = tmp_path / "out"
    samples = sample_factory(_key(0))
    for i in range(1, 6):
        sample_factory(_key(i))

    # Each triple is ~1280 logical bytes; threshold 2500 -> rotate after 2 fit.
    w = ShardWriter(out, "train", recipe_matrix_seed=42, target_shard_bytes=2500)
    _add_samples(w, samples, [_key(i) for i in range(6)])
    manifest = w.close()

    # 6 samples, ~7 KB each on disk (overhead), threshold 2500 -> at least
    # 6 shards. Important property: every sample appears in exactly one shard
    # and the total bytes on disk match the manifest sum.
    assert manifest.n_sample == 6
    assert manifest.n_shard >= 2
    on_disk = sorted(
        f.stat().st_size for f in out.glob("gold-train-*.tar")
    )
    assert sum(on_disk) == manifest.total_bytes


def test_close_emits_a_partial_final_shard(tmp_path: Path, sample_factory) -> None:
    """A trailing shard below the threshold is still flushed on close."""
    samples = sample_factory(_key(0))
    for i in range(1, 3):
        sample_factory(_key(i))
    w = ShardWriter(
        tmp_path / "out", "train",
        recipe_matrix_seed=42, target_shard_bytes=TARGET_SHARD_BYTES,  # huge
    )
    _add_samples(w, samples, [_key(i) for i in range(3)])
    manifest = w.close()
    assert manifest.n_shard == 1
    assert manifest.n_sample == 3


def test_close_with_no_samples_emits_empty_manifest(tmp_path: Path) -> None:
    """A writer that never received an add still produces a valid manifest."""
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    manifest = w.close()
    assert manifest.n_shard == 0
    assert manifest.n_sample == 0
    assert manifest.total_bytes == 0
    assert manifest.shards == []


def test_close_is_idempotent(tmp_path: Path, sample_factory) -> None:
    """Two ``close`` calls return the same manifest content (modulo timestamp)."""
    sample_dir = sample_factory(_key(0))
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    w.add_sample(_key(0), sample_dir)
    first = w.close()
    second = w.close()
    assert first.n_shard == second.n_shard == 1
    assert first.shards == second.shards


# --------------------------------------------------------------------------
# Tar bytes — determinism & ordering
# --------------------------------------------------------------------------
def test_tar_lists_three_files_per_sample_in_lex_order(
    tmp_path: Path, sample_factory
) -> None:
    """Each tar entry is ``{key}.{ext}`` with sorted lex keys (F0-T5 §5.2)."""
    sample_dir = sample_factory(_key(2))
    sample_factory(_key(0))
    sample_factory(_key(1))
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    # Insert OUT OF ORDER on purpose — the writer must sort them at flush.
    _add_samples(w, sample_dir, [_key(2), _key(0), _key(1)])
    w.close()

    tar_path = next((tmp_path / "out").glob("gold-train-*.tar"))
    with tarfile.open(tar_path, "r") as tar:
        names = tar.getnames()
    # Three files per sample, sorted by key.
    assert names == [
        f"{_key(0)}.audio.f16", f"{_key(0)}.target.f16", f"{_key(0)}.dna.json",
        f"{_key(1)}.audio.f16", f"{_key(1)}.target.f16", f"{_key(1)}.dna.json",
        f"{_key(2)}.audio.f16", f"{_key(2)}.target.f16", f"{_key(2)}.dna.json",
    ]


def test_tar_bytes_are_deterministic(tmp_path: Path, sample_factory) -> None:
    """Two runs on identical input -> bit-identical tar bytes (ENG_STD §1).

    The whole point of the normalised tar header in ``_add_deterministic``:
    timestamps and ownership do not leak into the bytes the model trains on.
    """
    for i in range(3):
        sample_factory(_key(i))
    sample_dir = tmp_path / "samples"

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    for out in (out_a, out_b):
        w = ShardWriter(out, "train", recipe_matrix_seed=42)
        _add_samples(w, sample_dir, [_key(i) for i in range(3)])
        w.close()

    bytes_a = (out_a / "gold-train-000000.tar").read_bytes()
    bytes_b = (out_b / "gold-train-000000.tar").read_bytes()
    assert bytes_a == bytes_b


def test_tar_content_is_preserved(tmp_path: Path, sample_factory) -> None:
    """The bytes inside the tar match the source files (round-trip)."""
    sample_dir = sample_factory(
        _key(0), audio_bytes=4096, target_bytes=512,
    )
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    w.add_sample(_key(0), sample_dir)
    w.close()

    tar_path = next((tmp_path / "out").glob("gold-train-*.tar"))
    with tarfile.open(tar_path, "r") as tar:
        member = tar.getmember(f"{_key(0)}.audio.f16")
        extracted = tar.extractfile(member)
        assert extracted is not None
        assert extracted.read() == b"A" * 4096


# --------------------------------------------------------------------------
# Atomicity — F0-T5 §6
# --------------------------------------------------------------------------
def test_finalised_shards_have_no_tmp_extension(
    tmp_path: Path, sample_factory
) -> None:
    """After close, only ``*.tar`` exists — every ``.tmp`` is renamed or gone."""
    for i in range(4):
        sample_factory(_key(i))
    sample_dir = tmp_path / "samples"

    w = ShardWriter(
        tmp_path / "out", "train",
        recipe_matrix_seed=42, target_shard_bytes=5000,
    )
    _add_samples(w, sample_dir, [_key(i) for i in range(4)])
    w.close()

    out = tmp_path / "out"
    assert not list(out.glob("*.tmp"))
    assert all(p.name.endswith(".tar") or p.name == "manifest.json" for p in out.iterdir())


def test_orphan_tmp_files_cleaned_on_construction(tmp_path: Path) -> None:
    """An orphan ``.tmp`` from a crashed run is removed at construction (§6)."""
    out = tmp_path / "out"
    out.mkdir()
    orphan = out / "gold-train-000007.tar.tmp"
    orphan.write_bytes(b"abandoned")

    ShardWriter(out, "train", recipe_matrix_seed=42)
    assert not orphan.exists()


def test_orphan_other_split_tmp_is_untouched(tmp_path: Path) -> None:
    """A writer for ``train`` never touches ``val`` orphans (split isolation)."""
    out = tmp_path / "out"
    out.mkdir()
    val_orphan = out / "gold-val-000001.tar.tmp"
    val_orphan.write_bytes(b"other split")

    ShardWriter(out, "train", recipe_matrix_seed=42)
    assert val_orphan.exists()


# --------------------------------------------------------------------------
# Manifest — F0-T5 §5.5
# --------------------------------------------------------------------------
def test_manifest_records_writer_state(tmp_path: Path, sample_factory) -> None:
    """Manifest captures seed, target bytes, tail policy, totals (F0-T5 §5.5)."""
    for i in range(3):
        sample_factory(_key(i))
    sample_dir = tmp_path / "samples"

    w = ShardWriter(
        tmp_path / "out", "val",
        recipe_matrix_seed=7777, tail_s=0.5, target_shard_bytes=3000,
    )
    _add_samples(w, sample_dir, [_key(i) for i in range(3)])
    manifest = w.close()

    assert manifest.manifest_version == MANIFEST_VERSION
    assert manifest.split == "val"
    assert manifest.recipe_matrix_seed == 7777
    assert manifest.target_shard_bytes == 3000
    assert manifest.tail_s == 0.5
    assert manifest.n_sample == 3
    assert manifest.n_shard >= 1


def test_manifest_record_sha256_matches_tar(
    tmp_path: Path, sample_factory
) -> None:
    """``sha256`` in each record is the SHA-256 of the final tar bytes."""
    import hashlib
    for i in range(2):
        sample_factory(_key(i))
    sample_dir = tmp_path / "samples"

    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    _add_samples(w, sample_dir, [_key(i) for i in range(2)])
    manifest = w.close()

    for record in manifest.shards:
        tar_path = tmp_path / "out" / record.filename
        sha = hashlib.sha256(tar_path.read_bytes()).hexdigest()
        assert record.sha256 == sha


def test_manifest_record_key_range_is_lex_first_last(
    tmp_path: Path, sample_factory
) -> None:
    """``key_range`` is ``(min_key, max_key)`` of the shard (F0-T5 §5.5)."""
    for i in range(3):
        sample_factory(_key(i))
    sample_dir = tmp_path / "samples"

    w = ShardWriter(
        tmp_path / "out", "train",
        recipe_matrix_seed=42, target_shard_bytes=TARGET_SHARD_BYTES,  # one shard
    )
    _add_samples(w, sample_dir, [_key(i) for i in range(3)])
    manifest = w.close()

    assert manifest.shards[0].key_range == (_key(0), _key(2))


def test_manifest_json_is_written_to_disk(tmp_path: Path, sample_factory) -> None:
    """``close`` lays down ``manifest.json`` with the schema fields."""
    sample_dir = sample_factory(_key(0))
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    w.add_sample(_key(0), sample_dir)
    w.close()

    path = tmp_path / "out" / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["manifest_version"] == MANIFEST_VERSION
    assert raw["split"] == "train"
    assert raw["recipe_matrix_seed"] == 42
    assert raw["n_shard"] == 1
    assert raw["n_sample"] == 1
    assert raw["shards"][0]["index"] == 0
    assert raw["shards"][0]["filename"] == "gold-train-000000.tar"


# --------------------------------------------------------------------------
# Resume — F0-T5 §6
# --------------------------------------------------------------------------
def test_resume_picks_up_from_existing_manifest(
    tmp_path: Path, sample_factory
) -> None:
    """A second writer on the same dir resumes the shard index (F0-T5 §6)."""
    for i in range(4):
        sample_factory(_key(i))
    sample_dir = tmp_path / "samples"

    # First session — force one shard per sample with a 1-byte threshold.
    w1 = ShardWriter(
        tmp_path / "out", "train",
        recipe_matrix_seed=42, target_shard_bytes=1,
    )
    _add_samples(w1, sample_dir, [_key(0), _key(1)])
    w1.close()
    assert w1.n_shard_committed == 2

    # Second session resumes from manifest.n_shard.
    w2 = ShardWriter(
        tmp_path / "out", "train",
        recipe_matrix_seed=42, target_shard_bytes=1,
    )
    assert w2.n_shard_committed == 2  # resumed from manifest
    _add_samples(w2, sample_dir, [_key(2), _key(3)])
    manifest = w2.close()

    # New shards take indices 2 and 3; prior 0 and 1 are intact.
    filenames = sorted(p.name for p in (tmp_path / "out").glob("gold-train-*.tar"))
    assert filenames == [
        "gold-train-000000.tar",
        "gold-train-000001.tar",
        "gold-train-000002.tar",
        "gold-train-000003.tar",
    ]
    assert manifest.n_sample == 4
    assert manifest.n_shard == 4


def test_resume_rejects_mismatched_split(tmp_path: Path, sample_factory) -> None:
    """A manifest written for ``train`` cannot be reopened as ``val``."""
    sample_dir = sample_factory(_key(0))
    w = ShardWriter(tmp_path / "out", "train", recipe_matrix_seed=42)
    w.add_sample(_key(0), sample_dir)
    w.close()
    with pytest.raises(ShardWriterError, match="split"):
        ShardWriter(tmp_path / "out", "val", recipe_matrix_seed=42)


def test_resume_rejects_malformed_manifest(tmp_path: Path) -> None:
    """A corrupt ``manifest.json`` fails loud, never silently overwritten."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "manifest.json").write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ShardWriterError, match="manifest.json"):
        ShardWriter(out, "train", recipe_matrix_seed=42)


# --------------------------------------------------------------------------
# Layer-2 property (Hypothesis) — determinism + budget invariants
# --------------------------------------------------------------------------
@settings(deadline=None, max_examples=12)
@given(
    keys_int=st.lists(
        st.integers(min_value=0, max_value=99),
        unique=True, min_size=1, max_size=10,
    )
)
def test_property_writer_is_deterministic_across_runs(
    keys_int: list[int], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """For any input list, two independent writers produce identical bytes."""
    keys = [_key(i) for i in keys_int]

    def _run(label: str) -> bytes:
        root = tmp_path_factory.mktemp(f"hyp_{label}")
        samples = root / "samples"
        samples.mkdir()
        for k in keys:
            (samples / f"{k}.audio.f16").write_bytes(b"A" * 1024)
            (samples / f"{k}.target.f16").write_bytes(b"T" * 256)
            (samples / f"{k}.dna.json").write_text("{}", encoding="utf-8")
        out = root / "out"
        w = ShardWriter(out, "train", recipe_matrix_seed=42)
        # Insert in input order; sort happens inside _rotate.
        for k in keys:
            w.add_sample(k, samples)
        w.close()
        return (out / "gold-train-000000.tar").read_bytes()

    assert _run("a") == _run("b")


@settings(deadline=None, max_examples=8)
@given(
    keys_int=st.lists(
        st.integers(min_value=0, max_value=199),
        unique=True, min_size=2, max_size=15,
    ),
    target_kib=st.integers(min_value=2, max_value=32),
)
def test_property_each_sample_appears_in_exactly_one_shard(
    keys_int: list[int],
    target_kib: int,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Pack-on-fill never drops or duplicates a sample (F0-T5 §3 invariant)."""
    keys = [_key(i) for i in keys_int]
    root = tmp_path_factory.mktemp("hyp_unique")
    samples = root / "samples"
    samples.mkdir()
    for k in keys:
        (samples / f"{k}.audio.f16").write_bytes(b"A" * 1024)
        (samples / f"{k}.target.f16").write_bytes(b"T" * 256)
        (samples / f"{k}.dna.json").write_text("{}", encoding="utf-8")

    out = root / "out"
    w = ShardWriter(
        out, "train",
        recipe_matrix_seed=42, target_shard_bytes=target_kib * 1024,
    )
    for k in keys:
        w.add_sample(k, samples)
    manifest: ShardManifest = w.close()

    # Every key shows up exactly once across all shards.
    seen: list[str] = []
    for record in manifest.shards:
        tar_path = out / record.filename
        with tarfile.open(tar_path, "r") as tar:
            for name in tar.getnames():
                if name.endswith(".audio.f16"):
                    seen.append(name[: -len(".audio.f16")])
    assert sorted(seen) == sorted(keys)
    assert manifest.n_sample == len(keys)
