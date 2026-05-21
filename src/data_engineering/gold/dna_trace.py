"""DNA-Trace — sample lineage barcode + ``dna.json`` "Libretto Sanitario".

SKELETON / CONTRACT INTERFACE.  Public types/constants are LOCKED here for the
F0-T9b test harness; the logic is owned by **F0-T2d** and raises
:class:`NotImplementedError`.

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §4.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from data_engineering.gold.recipe import Recipe

#: ``dna.json`` schema version (F0-T2a §4.2).
DNA_VERSION = "1.0"

#: Ordered barcode segments (F0-T2a §4.1).
BARCODE_SEGMENTS: tuple[str, ...] = (
    "midisrc",
    "midialt",
    "engine",
    "reverb",
    "audioalt",
    "saboteur",
)


class DnaTraceError(ValueError):
    """Raised on a malformed barcode key or an inconsistent ``dna.json``."""


@dataclass(frozen=True)
class Barcode:
    """The six-segment DNA barcode (F0-T2a §4.1).

    Segments are joined by ``-`` to form the WebDataset sample ``key``. The key
    is dot-free by construction so it survives WebDataset's extension splitting
    (F0-T2a §3.1).
    """

    midisrc: str
    midialt: str
    engine: str
    reverb: str
    audioalt: str
    saboteur: str


def encode_barcode(barcode: Barcode) -> str:
    """Encode a :class:`Barcode` into its ``-``-joined string key.

    Args:
        barcode: The six-segment barcode.

    Returns:
        The WebDataset sample key (dot-free).

    Note:
        SKELETON — implementation owned by F0-T2d.
    """
    raise NotImplementedError("barcode encoder — owned by F0-T2d")


def decode_barcode(key: str) -> Barcode:
    """Decode a barcode string key back into a :class:`Barcode`.

    ``decode_barcode`` is the exact inverse of :func:`encode_barcode`: the pair
    is a bijection (TESTING_DOCTRINE §6.2).

    Args:
        key: A six-segment, ``-``-joined barcode key.

    Returns:
        The decoded :class:`Barcode`.

    Raises:
        DnaTraceError: If ``key`` is not a well-formed six-segment barcode.

    Note:
        SKELETON — implementation owned by F0-T2d.
    """
    raise NotImplementedError("barcode decoder — owned by F0-T2d")


def build_dna_json(
    *,
    barcode: Barcode,
    recipe: Recipe,
    audio: np.ndarray,
    target: np.ndarray,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the ``dna.json`` "Libretto Sanitario" for one Gold sample.

    The document permits full reverse-engineering of the sample (F0-T2a §4.2):
    lineage, render/augmentation parameters, and the ``sha256`` + ``n_nonfinite``
    of both buffers (F0-T2a §3.7).

    Note:
        SKELETON — implementation owned by F0-T2d.
    """
    raise NotImplementedError("dna.json builder — owned by F0-T2d")


def validate_dna_json(dna: dict[str, Any], *, audio: np.ndarray, target: np.ndarray) -> None:
    """Verify a ``dna.json`` against its buffers (Gate L2 / DoD F0-T2d).

    Recomputes the buffer hashes, checks ``0`` non-finite values, and checks
    that the recorded shapes match (F0-T2a §3.7).

    Raises:
        DnaTraceError: On any mismatch.

    Note:
        SKELETON — implementation owned by F0-T2d.
    """
    raise NotImplementedError("dna.json validator — owned by F0-T2d")
