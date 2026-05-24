"""Gold sample loader — FP16 triple → ``[8, n_sample]`` audio + ``[n_frame, 25]`` target.

Reads a Gold sample triple (``audio.f16`` / ``target.f16`` / ``dna.json``) written
by the F0-T2d writer and:

1. Maps the input channels onto the 8 canonical slots per F0-T4a §4 (semantic
   mapping for ``mono`` / ``solo_stereo`` / ``glyn_johns`` / ``multitrack_full``).
2. Validates the integrity block in ``dna.json`` against the actual buffers
   (delegates to :func:`~data_engineering.gold.dna_trace.validate_dna_json`).
3. Supplies a fixed-length crop window (sample-aligned to a multiple of the
   encoder stride 128) for training, so each training step sees the same
   ``[B, 8, crop_samples]`` shape.

The crop length is in *samples*; the corresponding target slice is
``crop_samples / 128`` frames, by construction.

Spec: ``docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`` §3, §4, §9.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from data_engineering.gold.dna_trace import validate_dna_json
from data_engineering.gold.gold_writer import (
    HIHAT_OPENING_COL,
    R_TARGET_HZ,
    SAMPLE_RATE,
    TARGET_COLS,
)
from data_engineering.gold.mic_standardize import CANONICAL_SLOTS

#: Total encoder stride — F0-T4a §3 (4× Conv1d stride [4,4,4,2], Π = 128).
ENCODER_STRIDE = 128

#: Total receptive field of the trunk + encoder, in frames (F0-T4a §3.2).
#: Diagnostica T1-DIAG-A 2026-05-23 misurò ~1024 frame effettivi sul training
#: pattern attuale (dilatazioni 1..128 saturano oltre).
RECEPTIVE_FIELD_FRAMES = 1024

#: Default look-ahead in frames — F0-T4c B1 amendment (Decision Lock CEO 2026-05-24).
#: ``ceil(0.100 s × 344.53 Hz) = 35`` frame = ~100 ms PDC (F0-T4a §5).
#: Era ``0`` (strict-causal) prima della diagnostica T1-DIAG-A.
DEFAULT_LOOKAHEAD_FRAMES = 35

#: Minimum crop_samples that satisfies ``crop_frames + lookahead ≥ RF`` —
#: F0-T4c B2 amendment (Decision Lock CEO 2026-05-24). Computed from
#: ``(RECEPTIVE_FIELD_FRAMES + DEFAULT_LOOKAHEAD_FRAMES) × ENCODER_STRIDE``.
MIN_CROP_SAMPLES = (RECEPTIVE_FIELD_FRAMES + DEFAULT_LOOKAHEAD_FRAMES) * ENCODER_STRIDE
#: → 135_552 samples ≈ 3.07 s @ 44.1 kHz.

#: F0-T4a §4 — channel-to-slot mapping per mic configuration.
#:
#: For each mic_config the tuple gives the destination slot index of each input
#: channel, in the order the channels appear in the ``audio.f16`` buffer
#: (F0-T2a §2.3 + F0-T4a §4). Slots not listed are zero-filled.
CANONICAL_SLOT_MAP: dict[str, tuple[int, ...]] = {
    # mono: single mix → slot 0 (kick). Falls back to positional copy.
    "mono": (0,),
    # solo_stereo: mix_L → slot 5 (oh_L), mix_R → slot 6 (oh_R).
    "solo_stereo": (5, 6),
    # glyn_johns: kick → 0, snare → 1, oh_L → 5, oh_R → 6.
    "glyn_johns": (0, 1, 5, 6),
    # multitrack_full: kick/snare/hihat/tom/floor/oh_L/oh_R/room → 0..7.
    "multitrack_full": (0, 1, 2, 3, 4, 5, 6, 7),
}


class GoldDataError(ValueError):
    """Raised when a Gold sample triple cannot be loaded or is inconsistent."""


@dataclass(frozen=True)
class GoldSample:
    """A loaded, canonicalised Gold sample.

    Attributes:
        key: The DNA barcode (the triple's filename stem, minus ``.audio``).
        audio: ``[8, n_sample]`` float32 buffer on the 8 canonical slots.
        target: ``[n_frame, 25]`` float32 flat-25 target.
        mic_config: The recorded mic configuration (``mono`` / ``solo_stereo`` /
            ``glyn_johns`` / ``multitrack_full``).
        engine: The render engine (``sfizz`` / ``drumgizmo``) — useful for splits.
    """

    key: str
    audio: np.ndarray  # [8, n_sample] float32
    target: np.ndarray  # [n_frame, 25] float32
    mic_config: str
    engine: str


def _apply_canonical_slots(
    audio_raw: np.ndarray, mic_config: str
) -> np.ndarray:
    """Place ``audio_raw``'s channels onto the 8 canonical slots (F0-T4a §4)."""
    if mic_config not in CANONICAL_SLOT_MAP:
        raise GoldDataError(
            f"unknown mic_config {mic_config!r}; expected one of "
            f"{sorted(CANONICAL_SLOT_MAP)}"
        )
    slots = CANONICAL_SLOT_MAP[mic_config]
    n_mic = audio_raw.shape[0]
    if n_mic != len(slots):
        raise GoldDataError(
            f"mic_config {mic_config!r} expects {len(slots)} channel(s), "
            f"got audio with {n_mic}"
        )
    out = np.zeros((CANONICAL_SLOTS, audio_raw.shape[1]), dtype=audio_raw.dtype)
    for src, dst in enumerate(slots):
        out[dst] = audio_raw[src]
    return out


def load_gold_sample(triple_dir: Path | str, key: str) -> GoldSample:
    """Load and canonicalise a Gold sample triple from ``triple_dir/{key}.*``.

    Performs the F0-T2a §3.7 integrity check (sha256 + non-finite count match
    the recorded ``dna.json``) before returning. Fails loud
    (ENGINEERING_STANDARDS §6).

    Args:
        triple_dir: Directory containing ``{key}.audio.f16`` / ``.target.f16`` /
            ``.dna.json``.
        key: The DNA barcode key.

    Returns:
        A :class:`GoldSample` with audio canonicalised to ``[8, n_sample]``
        float32 and target as ``[n_frame, 25]`` float32.

    Raises:
        GoldDataError: On missing files, malformed ``dna.json``, integrity
            mismatch, or shape/contract violation.
    """
    triple_dir = Path(triple_dir)
    dna_path = triple_dir / f"{key}.dna.json"
    audio_path = triple_dir / f"{key}.audio.f16"
    target_path = triple_dir / f"{key}.target.f16"
    for p in (dna_path, audio_path, target_path):
        if not p.is_file():
            raise GoldDataError(f"missing Gold sample file: {p}")

    dna = json.loads(dna_path.read_text(encoding="utf-8"))
    a_shape = dna["audio"]["shape"]
    t_shape = dna["target"]["shape"]
    if len(a_shape) != 2 or len(t_shape) != 2:
        raise GoldDataError(f"{key}: dna.json shapes must be 2-D")
    if t_shape[1] != TARGET_COLS:
        raise GoldDataError(
            f"{key}: target second axis must be {TARGET_COLS} (flat-25), "
            f"got {t_shape[1]}"
        )

    audio_raw = np.fromfile(audio_path, dtype="<f2").reshape(a_shape)
    target_raw = np.fromfile(target_path, dtype="<f2").reshape(t_shape)
    # F0-T2d integrity check — fail loud if the on-disk buffers were touched.
    validate_dna_json(dna, audio=audio_raw, target=target_raw)

    mic_config = dna["lineage"]["render"]["mic_config"]
    engine = dna["lineage"]["render"]["engine"]
    audio_8 = _apply_canonical_slots(audio_raw, mic_config)

    return GoldSample(
        key=key,
        audio=audio_8.astype(np.float32, copy=False),
        target=target_raw.astype(np.float32, copy=False),
        mic_config=mic_config,
        engine=engine,
    )


def discover_gold_keys(root: Path | str) -> list[tuple[Path, str]]:
    """Discover ``(triple_dir, key)`` pairs under ``root`` (sorted, deterministic)."""
    out: list[tuple[Path, str]] = []
    for dna in sorted(Path(root).rglob("*.dna.json")):
        key = dna.name[: -len(".dna.json")]
        out.append((dna.parent, key))
    return out


class GoldDataset(Dataset[dict[str, torch.Tensor]]):
    """In-memory PyTorch :class:`Dataset` over a fixed list of Gold samples.

    Designed for the F0-T4b mini-prototype: the 12-sample mini-batch fits in
    RAM (≈ 200 MB float32). Each ``__getitem__`` returns a *random* fixed-length
    crop (deterministic per ``(index, epoch)`` when a generator is provided), so
    every training step sees the same ``[8, crop_samples]`` audio and
    ``[crop_frames, 25]`` target shape.

    The crop length is given in *samples* and must be a multiple of the encoder
    stride 128 — this keeps the target slice frame-aligned with the audio crop
    (F0-T4a §3, n_frame = n_sample / 128).
    """

    def __init__(
        self,
        samples: Sequence[GoldSample],
        *,
        crop_samples: int,
        rng: np.random.Generator | None = None,
        lookahead_frames: int = DEFAULT_LOOKAHEAD_FRAMES,
        allow_short_crop: bool = False,
    ) -> None:
        # F0-T4c B1+B2 (Decision Lock CEO 2026-05-24):
        # - ``lookahead_frames`` defaults to ``DEFAULT_LOOKAHEAD_FRAMES`` (= 35)
        #   so the strict-causal training of T1-DIAG-A cannot recur silently.
        # - ``crop_samples`` is rejected fail-loud below ``MIN_CROP_SAMPLES``
        #   because samples shorter than the receptive field force the model to
        #   learn from left-pad zeros (the bug isolated in T1-DIAG-A). The
        #   ``allow_short_crop`` escape hatch is reserved for explicit ablation
        #   tests; do NOT use in production training.
        if not samples:
            raise GoldDataError("GoldDataset requires at least one sample")
        if crop_samples <= 0 or crop_samples % ENCODER_STRIDE != 0:
            raise GoldDataError(
                f"crop_samples must be a positive multiple of {ENCODER_STRIDE}, "
                f"got {crop_samples}"
            )
        if not allow_short_crop and crop_samples < MIN_CROP_SAMPLES:
            raise GoldDataError(
                f"crop_samples={crop_samples} < MIN_CROP_SAMPLES={MIN_CROP_SAMPLES} "
                f"(= (RECEPTIVE_FIELD_FRAMES + DEFAULT_LOOKAHEAD_FRAMES) × "
                f"ENCODER_STRIDE). Crops shorter than the receptive field force "
                f"the model to learn from left-pad zeros (T1-DIAG-A bug, F0-T4c "
                f"B2). Use allow_short_crop=True only for ablation."
            )
        if lookahead_frames < 0:
            raise GoldDataError(
                f"lookahead_frames must be >= 0, got {lookahead_frames}"
            )
        crop_frames = crop_samples // ENCODER_STRIDE
        # With look-ahead L, the audio window must extend L frames past the
        # target window — so each sample must have at least
        # (crop_frames + L) * ENCODER_STRIDE audio samples and (crop_frames)
        # target frames (the target stays its original length, what shifts is
        # which audio frames feed each target frame).
        min_audio_samples = (crop_frames + lookahead_frames) * ENCODER_STRIDE
        for s in samples:
            if s.audio.shape[1] < min_audio_samples:
                raise GoldDataError(
                    f"sample {s.key!r} has {s.audio.shape[1]} samples "
                    f"< min_audio_samples {min_audio_samples} "
                    f"(crop_frames={crop_frames} + lookahead={lookahead_frames})"
                )
            if s.target.shape[0] < crop_frames:
                raise GoldDataError(
                    f"sample {s.key!r} has {s.target.shape[0]} frames "
                    f"< crop_frames {crop_frames}"
                )
        self.samples = list(samples)
        self.crop_samples = crop_samples
        self.crop_frames = crop_frames
        self.lookahead_frames = lookahead_frames
        self.rng = rng if rng is not None else np.random.default_rng(0)

    def __len__(self) -> int:  # pragma: no cover — trivial
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        s = self.samples[index]
        # Look-ahead semantics: the strict-causal model sees ``L`` extra audio
        # frames past the target window's end, so output[t] depends on
        # input[<= t + L] — equivalent to running the same causal stack with
        # ``L`` samples of latency. Implementation: shift the audio crop
        # forward by ``L * ENCODER_STRIDE`` samples; the target crop stays at
        # its original frame range.
        L = self.lookahead_frames  # noqa: N806
        total_audio_frames = s.audio.shape[1] // ENCODER_STRIDE
        max_target_start_frame = (
            min(s.target.shape[0], total_audio_frames - L) - self.crop_frames
        )
        if max_target_start_frame < 0:
            raise GoldDataError(
                f"sample {s.key!r} too short for crop_frames={self.crop_frames} "
                f"+ lookahead={L}"
            )
        start_frame = int(self.rng.integers(0, max_target_start_frame + 1))
        end_frame = start_frame + self.crop_frames
        # Audio window is shifted forward by ``L`` frames.
        start_sample = (start_frame + L) * ENCODER_STRIDE
        end_sample = start_sample + self.crop_samples

        audio = s.audio[:, start_sample:end_sample]
        target = s.target[start_frame:end_frame]
        return {
            "audio": torch.from_numpy(audio).contiguous(),  # [8, crop_samples]
            "target": torch.from_numpy(target).contiguous(),  # [crop_frames, 25]
            "key": _str_to_uint8_tensor(s.key),  # for diagnostics
        }


#: Fixed padded length for the per-sample ``key`` tensor — keeps the default
#: PyTorch collate happy when the batch mixes different key lengths (e.g.
#: the joint dataset has plain keys and ``-AUG``-suffixed keys side by side).
_KEY_TENSOR_LEN: int = 64


def _str_to_uint8_tensor(s: str) -> torch.Tensor:
    """Encode a short string as a fixed-length uint8 tensor.

    The string is UTF-8 encoded and right-padded with ``\\0`` to
    :data:`_KEY_TENSOR_LEN` bytes; raises if the encoded form is longer.
    A fixed length lets ``torch.utils.data.default_collate`` stack
    heterogeneously-named samples in the same batch.
    """
    raw = s.encode("utf-8")
    if len(raw) > _KEY_TENSOR_LEN:
        raise ValueError(
            f"key {s!r} encodes to {len(raw)} bytes > _KEY_TENSOR_LEN "
            f"({_KEY_TENSOR_LEN}) — bump the constant or shorten the key"
        )
    padded = raw + b"\x00" * (_KEY_TENSOR_LEN - len(raw))
    return torch.tensor(list(padded), dtype=torch.uint8)


def load_pool(
    pool_root: Path | str = "data/gold/L2_pool",
    *,
    keys: Iterable[str] | None = None,
) -> list[GoldSample]:
    """Load every Gold sample under ``pool_root`` (or a chosen subset).

    Args:
        pool_root: The root directory (default: the F0-T2e mini-batch pool).
        keys: Optional iterable of barcode keys; if given, only those are loaded.

    Returns:
        A list of :class:`GoldSample`, sorted by key.
    """
    triples = discover_gold_keys(pool_root)
    if keys is not None:
        wanted = set(keys)
        triples = [(d, k) for d, k in triples if k in wanted]
    return [load_gold_sample(d, k) for d, k in sorted(triples, key=lambda x: x[1])]


# Re-exports for callers that want the spec-locked constants without grabbing
# data_engineering.gold directly.
__all__ = [
    "CANONICAL_SLOTS",
    "CANONICAL_SLOT_MAP",
    "DEFAULT_LOOKAHEAD_FRAMES",
    "ENCODER_STRIDE",
    "HIHAT_OPENING_COL",
    "MIN_CROP_SAMPLES",
    "R_TARGET_HZ",
    "RECEPTIVE_FIELD_FRAMES",
    "SAMPLE_RATE",
    "TARGET_COLS",
    "GoldDataError",
    "GoldDataset",
    "GoldSample",
    "discover_gold_keys",
    "load_gold_sample",
    "load_pool",
]
