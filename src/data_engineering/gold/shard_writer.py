"""WebDataset shard writer — pack-on-fill, atomic rotation (F0-T5 §3, §6).

Packs the F0-T2a §3.1 sample triples (``{key}.audio.f16`` / ``.target.f16`` /
``.dna.json``) into WebDataset tar shards of locked size (F0-T5 §3). Rotation
is atomic — a partial shard never appears as final on disk: the writer first
emits ``gold-{split}-{index:06d}.tar.tmp``, hashes it, then atomically renames
to the final name (POSIX ``os.rename``). Resume is supported via the per-split
``manifest.json``: orphan ``.tmp`` files from a previous interrupted run are
removed at construction time and the shard index resumes from
``manifest.n_shard``.

Tar bytes are deterministic (ENGINEERING_STANDARDS §1): file timestamps and
ownership are normalised so the same recipe matrix on the same seed yields
byte-identical shards. Tar is not compressed (F0-T5 §5.4) — CPU at training
time is more expensive than intra-region Blob bandwidth.

Critical module — mutation kill-rate gate >= 90 % (TESTING_DOCTRINE §3). The
writer fails loud with :class:`ShardWriterError` on any contract violation;
it never leaves an inconsistent shard or manifest on disk
(ENGINEERING_STANDARDS §6).

Spec: ``docs/methodology/F0-T5_GOLD_SHARDING_SPEC.md``.
"""
from __future__ import annotations

import hashlib
import json
import os
import tarfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

#: Locked shard size — 1 GB exact (F0-T5 §3, §9; Decision Lock 2026-05-23).
TARGET_SHARD_BYTES = 1 << 30  # 1 073 741 824

#: ``manifest.json`` schema version (F0-T5 §5.5) — bumped on breaking changes.
MANIFEST_VERSION = "1.0"

#: Allowed Gold splits (F0-T2a §3.6 — Holdout is real data, not Gold).
Split = Literal["train", "val"]
_ALLOWED_SPLITS: tuple[str, ...] = ("train", "val")

#: Maximum shard index — 6 zero-padded digits give 1 000 000 distinct shards,
#: comfortable headroom over the ~1500 expected at 1.5 TB (F0-T5 §5.1, §4.3).
_MAX_SHARD_INDEX = 999_999

#: I/O chunk for the post-flush sha256 of the finalised shard.
_SHA_CHUNK_BYTES = 1 << 20  # 1 MB

#: Sample-triple extensions per the F0-T2a §3.1 contract.
_AUDIO_EXT = "audio.f16"
_TARGET_EXT = "target.f16"
_DNA_EXT = "dna.json"

#: Fixed metadata used in tar entries — anchors bit-for-bit determinism
#: (ENGINEERING_STANDARDS §1). The choice of ``mtime = 0`` makes the tar
#: header reproducible across machines and runs.
_TAR_MTIME = 0
_TAR_MODE = 0o644
_TAR_UNAME = ""
_TAR_GNAME = ""


class ShardWriterError(RuntimeError):
    """Raised when the shard pipeline cannot complete an operation."""


@dataclass(frozen=True)
class ShardRecord:
    """Manifest entry for one finalised shard (F0-T5 §5.5).

    Attributes:
        index: Zero-based shard index — matches the ``%06d`` slot in the
            filename.
        filename: Final tar filename, ``gold-{split}-{index:06d}.tar``.
        n_sample: Number of sample triples packed in this shard.
        n_bytes: Final tar file size on disk, in bytes (post-rename).
        sha256: SHA-256 hex digest of the final tar bytes — for integrity
            verification post-pull (``dvc pull`` round-trip).
        key_range: ``(first_key, last_key)`` lexicographic bounds of the sample
            keys packed in this shard (F0-T5 §5.5).
    """

    index: int
    filename: str
    n_sample: int
    n_bytes: int
    sha256: str
    key_range: tuple[str, str]


@dataclass(frozen=True)
class ShardManifest:
    """Per-split manifest packaged with the Gold shards (F0-T5 §5.5).

    Attributes:
        manifest_version: Schema version — see :data:`MANIFEST_VERSION`.
        split: ``"train"`` or ``"val"`` (F0-T2a §3.6).
        generated_at: ISO-8601 UTC timestamp of the last manifest write.
        recipe_matrix_seed: Seed of the F2-T1 recipe pre-shuffle — anchors
            the deterministic order in which samples were consumed.
        target_shard_bytes: The size threshold the writer rotated on.
        tail_s: Standardised audio tail length (F0-T2a §3.8) — recorded here
            so downstream readers know the duration policy of the dataset.
        n_shard: Number of finalised shards (== ``len(shards)``).
        n_sample: Total number of sample triples across all shards.
        total_bytes: Sum of finalised shard byte sizes.
        shards: One :class:`ShardRecord` per finalised shard, in index order.
    """

    manifest_version: str
    split: Split
    generated_at: str
    recipe_matrix_seed: int
    target_shard_bytes: int
    tail_s: float
    n_shard: int
    n_sample: int
    total_bytes: int
    shards: list[ShardRecord]


def shard_name(split: Split, index: int) -> str:
    """Return the canonical shard filename for ``(split, index)`` (F0-T5 §5.1).

    Args:
        split: ``"train"`` or ``"val"``.
        index: Zero-based shard index in ``[0, 999_999]``.

    Returns:
        ``f"gold-{split}-{index:06d}.tar"`` — six zero-padded digits keep
        lexicographic order == numeric order.

    Raises:
        ShardWriterError: If ``split`` is not allowed or ``index`` is outside
            ``[0, 999_999]``.
    """
    if split not in _ALLOWED_SPLITS:
        raise ShardWriterError(
            f"split must be one of {_ALLOWED_SPLITS!r}, got {split!r}"
        )
    if not 0 <= index <= _MAX_SHARD_INDEX:
        raise ShardWriterError(
            f"shard index must be in [0, {_MAX_SHARD_INDEX}], got {index}"
        )
    return f"gold-{split}-{index:06d}.tar"


def _sample_triple_paths(sample_dir: Path, key: str) -> tuple[Path, Path, Path]:
    """Resolve the three sample files for ``key`` under ``sample_dir``."""
    audio = sample_dir / f"{key}.{_AUDIO_EXT}"
    target = sample_dir / f"{key}.{_TARGET_EXT}"
    dna = sample_dir / f"{key}.{_DNA_EXT}"
    for path in (audio, target, dna):
        if not path.is_file():
            raise ShardWriterError(
                f"sample triple incomplete: missing {path.name} for key {key!r}"
            )
    return audio, target, dna


def _sha256_of_file(path: Path) -> str:
    """Return the SHA-256 hex digest of ``path``, streaming in 1 MB chunks."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_SHA_CHUNK_BYTES), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _add_deterministic(tar: tarfile.TarFile, src: Path, arcname: str) -> None:
    """Append ``src`` to ``tar`` under ``arcname`` with normalised metadata.

    Strips timestamps and ownership from the tar header so two runs that
    produce the same input bytes also produce identical tar bytes
    (ENGINEERING_STANDARDS §1).
    """
    info = tar.gettarinfo(str(src), arcname=arcname)
    if info is None:  # pragma: no cover — gettarinfo only returns None on stat failure
        raise ShardWriterError(f"cannot stat {src} for tar inclusion")
    info.mtime = _TAR_MTIME
    info.uid = 0
    info.gid = 0
    info.uname = _TAR_UNAME
    info.gname = _TAR_GNAME
    info.mode = _TAR_MODE
    info.pax_headers = {}
    with src.open("rb") as f:
        tar.addfile(info, fileobj=f)


def _read_manifest_or_none(out_dir: Path) -> ShardManifest | None:
    """Read ``manifest.json`` for resume; return ``None`` if absent."""
    path = out_dir / "manifest.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShardWriterError(
            f"manifest.json at {path} is unreadable or malformed: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise ShardWriterError(f"manifest.json at {path} is not a JSON object")
    try:
        shards = [
            ShardRecord(
                index=int(r["index"]),
                filename=str(r["filename"]),
                n_sample=int(r["n_sample"]),
                n_bytes=int(r["n_bytes"]),
                sha256=str(r["sha256"]),
                key_range=(str(r["key_range"][0]), str(r["key_range"][1])),
            )
            for r in raw["shards"]
        ]
        return ShardManifest(
            manifest_version=str(raw["manifest_version"]),
            split=raw["split"],
            generated_at=str(raw["generated_at"]),
            recipe_matrix_seed=int(raw["recipe_matrix_seed"]),
            target_shard_bytes=int(raw["target_shard_bytes"]),
            tail_s=float(raw["tail_s"]),
            n_shard=int(raw["n_shard"]),
            n_sample=int(raw["n_sample"]),
            total_bytes=int(raw["total_bytes"]),
            shards=shards,
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ShardWriterError(
            f"manifest.json at {path} has a malformed entry: {exc}"
        ) from exc


def _manifest_to_dict(manifest: ShardManifest) -> dict[str, Any]:
    """Serialise a :class:`ShardManifest` to a JSON-ready dict."""
    return {
        "manifest_version": manifest.manifest_version,
        "split": manifest.split,
        "generated_at": manifest.generated_at,
        "recipe_matrix_seed": manifest.recipe_matrix_seed,
        "target_shard_bytes": manifest.target_shard_bytes,
        "tail_s": manifest.tail_s,
        "n_shard": manifest.n_shard,
        "n_sample": manifest.n_sample,
        "total_bytes": manifest.total_bytes,
        "shards": [
            {**asdict(record), "key_range": list(record.key_range)}
            for record in manifest.shards
        ],
    }


class ShardWriter:
    """Pack-on-fill WebDataset shard writer (F0-T5 §3, §6).

    Append sample triples with :meth:`add_sample` and the writer rotates a new
    ``.tar`` shard whenever the running byte budget crosses
    ``target_shard_bytes`` (F0-T5 §3). On rotation:

    * the buffered triples are sorted lexicographically by key — deterministic
      tar bytes (F0-T5 §5.2);
    * file metadata is normalised (mtime/uid/gid/mode — see
      :func:`_add_deterministic`);
    * the tar is written to ``gold-{split}-{index:06d}.tar.tmp``;
    * its SHA-256 is computed and the file is atomically renamed to the final
      name (POSIX ``os.rename``);
    * the manifest is updated on disk (also via ``.tmp`` + rename).

    Resume: when the writer is constructed on a directory that already holds a
    ``manifest.json``, the prior shard records are loaded, the next index
    resumes from ``manifest.n_shard``, and any orphan ``*.tar.tmp`` files from
    an interrupted run are removed.

    The writer is **not** thread-safe — one writer per ``(out_dir, split)``,
    one producer thread.
    """

    def __init__(
        self,
        out_dir: str | Path,
        split: Split,
        *,
        recipe_matrix_seed: int,
        tail_s: float = 0.5,
        target_shard_bytes: int = TARGET_SHARD_BYTES,
    ) -> None:
        """Construct (or resume) a shard writer for ``(out_dir, split)``.

        Args:
            out_dir: Destination directory — created if absent.
            split: ``"train"`` or ``"val"`` (F0-T2a §3.6).
            recipe_matrix_seed: Seed used by F2-T1 to pre-shuffle the recipe
                matrix; recorded in the manifest for reproducibility.
            tail_s: Standardised audio tail length (F0-T2a §3.8) — recorded
                in the manifest. Defaults to the LOCKED value 0.5.
            target_shard_bytes: Pack-on-fill threshold; defaults to
                :data:`TARGET_SHARD_BYTES`. Smaller values are allowed for
                tests but never below 1 byte.

        Raises:
            ShardWriterError: On a malformed argument (split / threshold /
                tail_s), or a corrupt pre-existing manifest.
        """
        if split not in _ALLOWED_SPLITS:
            raise ShardWriterError(
                f"split must be one of {_ALLOWED_SPLITS!r}, got {split!r}"
            )
        if not isinstance(target_shard_bytes, int) or target_shard_bytes <= 0:
            raise ShardWriterError(
                f"target_shard_bytes must be a positive int, got {target_shard_bytes!r}"
            )
        if tail_s < 0.0:
            raise ShardWriterError(f"tail_s must be >= 0, got {tail_s}")

        self._out_dir = Path(out_dir)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._split: Split = split
        self._recipe_matrix_seed = recipe_matrix_seed
        self._tail_s = float(tail_s)
        self._target_shard_bytes = target_shard_bytes

        # Cleanup orphan .tmp files from previous interrupted runs (F0-T5 §6).
        for orphan in self._out_dir.glob(f"gold-{split}-*.tar.tmp"):
            orphan.unlink()

        # Resume from a previous manifest if present.
        existing = _read_manifest_or_none(self._out_dir)
        self._records: list[ShardRecord] = []
        self._seen_keys: set[str] = set()
        self._next_index = 0
        if existing is not None:
            if existing.split != split:
                raise ShardWriterError(
                    f"manifest at {self._out_dir} is for split "
                    f"{existing.split!r}, not {split!r}"
                )
            self._records = list(existing.shards)
            self._next_index = existing.n_shard

        # Open-shard buffer — paths only, not file contents (RAM cap stays
        # tiny even with a 1 GB target shard).
        self._pending: list[tuple[str, Path, Path, Path]] = []
        self._pending_bytes = 0
        self._closed = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def split(self) -> Split:
        """The split this writer packs (immutable after construction)."""
        return self._split

    @property
    def n_shard_committed(self) -> int:
        """Number of shards finalised on disk so far."""
        return len(self._records)

    @property
    def n_sample_committed(self) -> int:
        """Number of sample triples already packed into finalised shards."""
        return sum(r.n_sample for r in self._records)

    @property
    def n_sample_pending(self) -> int:
        """Triples accumulated in the still-open shard, not yet flushed."""
        return len(self._pending)

    def add_sample(self, key: str, sample_dir: str | Path) -> None:
        """Queue the ``{key}.{audio.f16,target.f16,dna.json}`` triple.

        Pack-on-fill: when the queued byte budget crosses
        ``target_shard_bytes``, :meth:`add_sample` calls :meth:`_rotate` and
        the next call opens a fresh shard.

        Args:
            key: WebDataset sample key — the DNA barcode (dot-free, F0-T2a §4.1).
            sample_dir: Directory holding the sample's three files.

        Raises:
            ShardWriterError: If the writer is closed, the key is empty or
                contains a dot, any of the three files is missing, or the
                key has already been packed in this writer instance.
        """
        if self._closed:
            raise ShardWriterError("ShardWriter is closed — open a new one to write more")
        if not isinstance(key, str) or not key:
            raise ShardWriterError("key must be a non-empty string")
        if "." in key:
            raise ShardWriterError(
                f"key {key!r} must not contain '.' — reserved by WebDataset"
            )
        if key in self._seen_keys:
            raise ShardWriterError(
                f"duplicate key {key!r} — refusing to pack twice in the same writer"
            )

        audio, target, dna = _sample_triple_paths(Path(sample_dir), key)
        triple_bytes = audio.stat().st_size + target.stat().st_size + dna.stat().st_size

        self._pending.append((key, audio, target, dna))
        self._pending_bytes += triple_bytes
        self._seen_keys.add(key)

        if self._pending_bytes >= self._target_shard_bytes:
            self._rotate()

    def close(self) -> ShardManifest:
        """Flush any remaining pending samples and write the final manifest.

        Idempotent: a second :meth:`close` returns the same manifest without
        rewriting it. ``close`` is the only call site that emits a manifest
        with a fresh ``generated_at`` — :meth:`_rotate` keeps the manifest
        up to date for crash-recovery, but it is :meth:`close` that seals
        the writer.

        Returns:
            The :class:`ShardManifest` describing every shard finalised by
            this writer (and any resumed from a previous run).
        """
        if not self._closed:
            if self._pending:
                self._rotate()
            self._write_manifest()
            self._closed = True
        return self._build_manifest()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _rotate(self) -> None:
        """Flush the open shard to disk and update the manifest atomically."""
        if not self._pending:
            return

        # Lexicographic order inside the tar -> deterministic bytes (F0-T5 §5.2).
        self._pending.sort(key=lambda triple: triple[0])
        keys = [triple[0] for triple in self._pending]

        final_name = shard_name(self._split, self._next_index)
        final_path = self._out_dir / final_name
        tmp_path = self._out_dir / f"{final_name}.tmp"

        # PAX_FORMAT supports long names cleanly; with the normalised header
        # produced by _add_deterministic the output is bit-stable.
        with tarfile.open(tmp_path, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for key, audio, target, dna in self._pending:
                _add_deterministic(tar, audio, f"{key}.{_AUDIO_EXT}")
                _add_deterministic(tar, target, f"{key}.{_TARGET_EXT}")
                _add_deterministic(tar, dna, f"{key}.{_DNA_EXT}")

        n_bytes = tmp_path.stat().st_size
        sha = _sha256_of_file(tmp_path)
        # POSIX rename is atomic on the same filesystem.
        os.rename(tmp_path, final_path)

        record = ShardRecord(
            index=self._next_index,
            filename=final_name,
            n_sample=len(self._pending),
            n_bytes=n_bytes,
            sha256=sha,
            key_range=(keys[0], keys[-1]),
        )
        self._records.append(record)
        self._next_index += 1
        self._pending = []
        self._pending_bytes = 0

        # Crash-recovery checkpoint — keep the manifest in step with the disk.
        self._write_manifest()

    def _build_manifest(self) -> ShardManifest:
        """Snapshot the current state into a :class:`ShardManifest`."""
        return ShardManifest(
            manifest_version=MANIFEST_VERSION,
            split=self._split,
            generated_at=datetime.now(UTC).isoformat(),
            recipe_matrix_seed=self._recipe_matrix_seed,
            target_shard_bytes=self._target_shard_bytes,
            tail_s=self._tail_s,
            n_shard=len(self._records),
            n_sample=sum(r.n_sample for r in self._records),
            total_bytes=sum(r.n_bytes for r in self._records),
            shards=list(self._records),
        )

    def _write_manifest(self) -> None:
        """Atomically write ``manifest.json`` (``.tmp`` + rename)."""
        manifest = self._build_manifest()
        path = self._out_dir / "manifest.json"
        tmp = self._out_dir / "manifest.json.tmp"
        tmp.write_text(
            json.dumps(_manifest_to_dict(manifest), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp, path)
