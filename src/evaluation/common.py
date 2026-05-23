"""Shared primitives for the F0-T17 statistical validation suite.

Five concerns live here, in the order the four modules consume them:

1. :class:`Thresholds` — strongly-typed view over the locked
   ``src/evaluation/thresholds.yaml`` (F0-T17 §4). Loading is fail-loud:
   any missing or out-of-range value raises :class:`ThresholdsError`.
2. :class:`GoldSampleMeta` — one row per sample in a Gold directory,
   pulled from the matching ``.dna.json`` file. The four modules consume
   *only* this view of the dataset; they never read the raw audio buffer
   for distribution stats (too slow at 300 k samples × 4 GB each).
3. :func:`scan_gold_dir` — deterministic directory walk producing the
   list of :class:`GoldSampleMeta`, sorted by ``key`` (the ordering
   anchors the determinism oracle of every module).
4. :class:`ReportResult` — the uniform return value of every
   ``module.run()`` function (F0-T17 §5).
5. :func:`write_report_json`, :func:`save_lab_precision_figure` —
   serializers shared by all four modules so reports look identical.

All functions are deterministic for a given input (ENGINEERING_STANDARDS §1):
the JSON serializer sorts keys, the directory scanner sorts samples by key,
and the matplotlib helper uses a fixed monochrome stylesheet (no system
font dependency).
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ThresholdsError(ValueError):
    """Raised when the LOCKED thresholds file is malformed or out of range."""


class GoldScanError(RuntimeError):
    """Raised when a Gold directory cannot be scanned (missing triple, bad JSON)."""


@dataclass(frozen=True)
class Thresholds:
    """Strongly-typed view over ``thresholds.yaml`` (F0-T17 §4 — LOCKED).

    Attributes mirror the four top-level sections of the YAML. Each numeric
    floor is validated at load time — modifying a value at runtime is
    impossible by design (``frozen=True``); a new run must reload the file.
    """

    # data_audit
    bus_minority_pct: float
    bpm_min: int
    bpm_max: int
    velocity_n_bin: int
    duration_n_bin: int

    # split_consistency
    ks_p_min: float
    chi2_p_min: float
    midi_leakage_max: int

    # anti_leak_audit
    duration_engine_chi2_p_min: float
    mi_audio_engine_max_bits: float
    cross_engine_match_pct_min: float

    # evaluation_suite
    onset_tolerance_ms: float
    bootstrap_n_resamples: int
    bootstrap_ci_max_width: float
    per_bus_f_min: float
    f_macro_min: float


def load_thresholds(path: Path | str) -> Thresholds:
    """Read and validate the LOCKED thresholds file.

    Args:
        path: Path to ``thresholds.yaml``. Resolved as-is — no fallback search.

    Returns:
        A validated :class:`Thresholds`.

    Raises:
        ThresholdsError: when the file is missing, not a mapping, contains a
            non-numeric value, or violates a structural invariant (e.g.
            ``bpm_min >= bpm_max``).
    """
    p = Path(path)
    if not p.is_file():
        raise ThresholdsError(f"thresholds file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ThresholdsError(f"thresholds YAML parse error: {exc}") from exc
    if not isinstance(raw, dict):
        raise ThresholdsError(f"thresholds root must be a mapping, got {type(raw).__name__}")

    sections = ("data_audit", "split_consistency", "anti_leak_audit", "evaluation_suite")
    for s in sections:
        if s not in raw or not isinstance(raw[s], dict):
            raise ThresholdsError(f"thresholds missing or malformed section: {s!r}")

    def get_num(section: str, key: str, *, kind: type) -> int | float:
        v = raw[section].get(key)
        if v is None or not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ThresholdsError(f"thresholds[{section}].{key}: numeric value required, got {v!r}")
        return kind(v)  # type: ignore[no-any-return]

    bpm_min = int(get_num("data_audit", "bpm_min", kind=int))
    bpm_max = int(get_num("data_audit", "bpm_max", kind=int))
    if not 0 < bpm_min < bpm_max:
        raise ThresholdsError(f"bpm_min ({bpm_min}) must satisfy 0 < bpm_min < bpm_max ({bpm_max})")

    velocity_n_bin = int(get_num("data_audit", "velocity_n_bin", kind=int))
    duration_n_bin = int(get_num("data_audit", "duration_n_bin", kind=int))
    if velocity_n_bin < 2 or duration_n_bin < 2:
        raise ThresholdsError(
            f"velocity_n_bin / duration_n_bin must be >= 2, got "
            f"{velocity_n_bin} / {duration_n_bin}"
        )

    bus_minority_pct = float(get_num("data_audit", "bus_minority_pct", kind=float))
    if not 0.0 < bus_minority_pct < 100.0:
        raise ThresholdsError(
            f"bus_minority_pct must be in (0, 100), got {bus_minority_pct}"
        )

    def _check_prob(section: str, key: str) -> float:
        v = float(get_num(section, key, kind=float))
        if not 0.0 <= v <= 1.0:
            raise ThresholdsError(f"thresholds[{section}].{key} must be in [0, 1], got {v}")
        return v

    return Thresholds(
        bus_minority_pct=bus_minority_pct,
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        velocity_n_bin=velocity_n_bin,
        duration_n_bin=duration_n_bin,
        ks_p_min=_check_prob("split_consistency", "ks_p_min"),
        chi2_p_min=_check_prob("split_consistency", "chi2_p_min"),
        midi_leakage_max=int(get_num("split_consistency", "midi_leakage_max", kind=int)),
        duration_engine_chi2_p_min=_check_prob(
            "anti_leak_audit", "duration_engine_chi2_p_min"
        ),
        mi_audio_engine_max_bits=float(
            get_num("anti_leak_audit", "mi_audio_engine_max_bits", kind=float)
        ),
        cross_engine_match_pct_min=float(
            get_num("anti_leak_audit", "cross_engine_match_pct_min", kind=float)
        ),
        onset_tolerance_ms=float(get_num("evaluation_suite", "onset_tolerance_ms", kind=float)),
        bootstrap_n_resamples=int(
            get_num("evaluation_suite", "bootstrap_n_resamples", kind=int)
        ),
        bootstrap_ci_max_width=float(
            get_num("evaluation_suite", "bootstrap_ci_max_width", kind=float)
        ),
        per_bus_f_min=_check_prob("evaluation_suite", "per_bus_f_min"),
        f_macro_min=_check_prob("evaluation_suite", "f_macro_min"),
    )


@dataclass(frozen=True)
class GoldSampleMeta:
    """One sample of a Gold directory, viewed through its ``dna.json``.

    The audit modules walk a directory of these — never the raw f16 buffers
    when computing distributions. Audio is loaded on-demand only by
    :mod:`evaluation.anti_leak_audit` (which needs the first 1 s for the
    mutual-information check).

    Attributes:
        key: ``barcode`` field of the DNA — also the filename stem (without
            extension). Anchors the deterministic sort order.
        dna_path: Absolute path to the ``.dna.json`` file.
        audio_path: Absolute path to the ``.audio.f16`` sibling.
        target_path: Absolute path to the ``.target.f16`` sibling.
        split: Locked enum value (``"train"`` or ``"val"``).
        engine: Render engine (``"sfizz"`` / ``"drumgizmo"``).
        kit: Render kit name (e.g. ``"DRSKit"``).
        mic_config: Microphone configuration (``"mono"`` / ``"solo_stereo"``
            / ``"glyn_johns"`` / ``"multitrack_full"``).
        sample_rate: Audio sample rate (Hz).
        midi_source: Bronze MIDI source path — used for the leakage check.
        n_mic: First axis of the audio buffer (channel count).
        n_sample: Second axis of the audio buffer (sample count).
        n_frame: First axis of the target matrix (frame count).
        audio_sha256: SHA-256 of the audio buffer bytes.
        target_sha256: SHA-256 of the target buffer bytes.
        recipe_sha256: SHA-256 of the recipe document that produced this sample.
        jitter_variant_idx: Recipe-matrix jitter variant index (0 = baseline);
            absent in the F0-T2e mini-batch (decoded from the barcode key
            instead — ``None`` on legacy samples).
        augmentation_level: Augmentation level (``0`` / ``1`` / ``2`` / ``3``).
    """

    key: str
    dna_path: Path
    audio_path: Path
    target_path: Path
    split: str
    engine: str
    kit: str
    mic_config: str
    sample_rate: int
    midi_source: str
    n_mic: int
    n_sample: int
    n_frame: int
    audio_sha256: str
    target_sha256: str
    recipe_sha256: str
    jitter_variant_idx: int | None
    augmentation_level: int


_DNA_REQUIRED_KEYS = ("key", "split", "audio", "target", "lineage", "recipe_sha256")
_LINEAGE_REQUIRED_KEYS = ("midi_source", "render", "augmentation")
_RENDER_REQUIRED_KEYS = ("engine", "kit", "mic_config", "sample_rate")


def _load_dna_meta(dna_path: Path) -> GoldSampleMeta:
    """Internal — parse one ``.dna.json`` into a :class:`GoldSampleMeta`."""
    try:
        doc = json.loads(dna_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GoldScanError(f"{dna_path}: invalid JSON ({exc})") from exc
    if not isinstance(doc, dict):
        raise GoldScanError(f"{dna_path}: root must be a JSON object")
    for k in _DNA_REQUIRED_KEYS:
        if k not in doc:
            raise GoldScanError(f"{dna_path}: missing required key {k!r}")
    lineage = doc["lineage"]
    if not isinstance(lineage, dict):
        raise GoldScanError(f"{dna_path}: 'lineage' must be an object")
    for k in _LINEAGE_REQUIRED_KEYS:
        if k not in lineage:
            raise GoldScanError(f"{dna_path}: missing lineage.{k}")
    render = lineage["render"]
    for k in _RENDER_REQUIRED_KEYS:
        if k not in render:
            raise GoldScanError(f"{dna_path}: missing lineage.render.{k}")

    audio_shape = doc["audio"]["shape"]
    target_shape = doc["target"]["shape"]
    if not (isinstance(audio_shape, list) and len(audio_shape) == 2):
        raise GoldScanError(f"{dna_path}: audio.shape must be [n_mic, n_sample]")
    if not (isinstance(target_shape, list) and len(target_shape) == 2):
        raise GoldScanError(f"{dna_path}: target.shape must be [n_frame, n_cols]")

    key = str(doc["key"])
    stem_audio = dna_path.parent / f"{key}.audio.f16"
    stem_target = dna_path.parent / f"{key}.target.f16"

    # Decode jitter variant from the 7-segment barcode if present
    # (F0-T15-pre §3 — segment 2 is ``Jnn``); legacy 6-segment keys (F0-T2e)
    # surface as ``None``.
    jitter_variant: int | None = None
    parts = key.split("-")
    for seg in parts:
        if len(seg) >= 2 and seg.startswith("J") and seg[1:].isdigit():
            jitter_variant = int(seg[1:])
            break

    midi_source_doc = lineage["midi_source"]
    midi_source = str(midi_source_doc.get("file", ""))
    if not midi_source:
        raise GoldScanError(f"{dna_path}: lineage.midi_source.file must be non-empty")

    return GoldSampleMeta(
        key=key,
        dna_path=dna_path.resolve(),
        audio_path=stem_audio.resolve(),
        target_path=stem_target.resolve(),
        split=str(doc["split"]),
        engine=str(render["engine"]),
        kit=str(render["kit"]),
        mic_config=str(render["mic_config"]),
        sample_rate=int(render["sample_rate"]),
        midi_source=midi_source,
        n_mic=int(audio_shape[0]),
        n_sample=int(audio_shape[1]),
        n_frame=int(target_shape[0]),
        audio_sha256=str(doc["audio"].get("sha256", "")),
        target_sha256=str(doc["target"].get("sha256", "")),
        recipe_sha256=str(doc["recipe_sha256"]),
        jitter_variant_idx=jitter_variant,
        augmentation_level=int(lineage["augmentation"].get("level", 0)),
    )


def scan_gold_dir(gold_dir: Path | str) -> list[GoldSampleMeta]:
    """Walk a Gold sample directory and return one row per sample.

    The list is sorted by ``key`` so that every consumer sees the same
    ordering — anchors the deterministic JSON serialization (and the
    determinism property test of every module).

    Args:
        gold_dir: Path to a directory of ``{key}.audio.f16``/``.target.f16``/
            ``.dna.json`` triples (the F0-T2a §3.1 layout).

    Returns:
        A list of :class:`GoldSampleMeta`, sorted ascending by ``key``.

    Raises:
        GoldScanError: when the directory does not exist, contains no
            ``.dna.json`` files, or any triple is incomplete.
    """
    d = Path(gold_dir)
    if not d.is_dir():
        raise GoldScanError(f"gold_dir is not a directory: {d}")
    dna_files = sorted(d.glob("*.dna.json"))
    if not dna_files:
        raise GoldScanError(f"gold_dir contains no .dna.json files: {d}")
    metas: list[GoldSampleMeta] = []
    for dp in dna_files:
        meta = _load_dna_meta(dp)
        if not meta.audio_path.is_file():
            raise GoldScanError(f"{dp}: missing sibling audio file {meta.audio_path}")
        if not meta.target_path.is_file():
            raise GoldScanError(f"{dp}: missing sibling target file {meta.target_path}")
        metas.append(meta)
    metas.sort(key=lambda m: m.key)
    return metas


@dataclass(frozen=True)
class ReportResult:
    """Uniform return value of every ``module.run()`` (F0-T17 §5).

    Attributes:
        module_name: Stable module identifier (e.g. ``"data_audit"``).
        passed: Gate verdict. ``False`` → the caller must refuse to proceed
            (the CLI ``exit code = 1``).
        metrics: The full JSON-serialisable payload (also written to disk).
        failures: Human-readable failure descriptions — empty when ``passed``.
        report_json: Absolute path of the written ``report.json``.
        report_png: Absolute path of the written ``report.png``.
    """

    module_name: str
    passed: bool
    metrics: dict[str, Any]
    failures: list[str] = field(default_factory=list)
    report_json: Path = field(default_factory=lambda: Path())
    report_png: Path = field(default_factory=lambda: Path())


def write_report_json(out_dir: Path | str, module_name: str, payload: dict[str, Any]) -> Path:
    """Serialize ``payload`` deterministically to ``out_dir/{module_name}.report.json``.

    The JSON is sorted-key, 2-space-indented, with trailing newline — so
    byte-identical for the same input on every platform.
    """
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{module_name}.report.json"
    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    target.write_text(body + "\n", encoding="utf-8")
    return target.resolve()


# --- matplotlib helpers -------------------------------------------------------
#
# We import matplotlib lazily inside the function so the module is importable
# even on machines where matplotlib is not installed (e.g. a unit-test slice
# that does not exercise plotting). Tests must use the ``Agg`` backend.

def _configure_lab_precision_style() -> None:
    """Apply the Laboratory-Precision monochrome stylesheet to matplotlib."""
    import matplotlib  # noqa: PLC0415 — lazy import (see module docstring)

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt  # noqa: PLC0415

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.edgecolor": "#1a1a1a",
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "grid.color": "#dddddd",
            "grid.linewidth": 0.4,
            "lines.color": "#1a1a1a",
            "lines.linewidth": 1.0,
            "patch.edgecolor": "#1a1a1a",
            "patch.linewidth": 0.6,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.dpi": 150,
        }
    )


def save_lab_precision_figure(out_dir: Path | str, module_name: str, figure: Any) -> Path:
    """Save a matplotlib ``Figure`` to ``out_dir/{module_name}.report.png``.

    Uses the monochrome Laboratory-Precision stylesheet (see
    :func:`_configure_lab_precision_style`). Closes the figure after save.
    """
    import matplotlib.pyplot as plt  # noqa: PLC0415

    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{module_name}.report.png"
    figure.tight_layout()
    figure.savefig(target, bbox_inches="tight")
    plt.close(figure)
    return target.resolve()


def report_to_dict(result: ReportResult) -> dict[str, Any]:
    """JSON-serialisable view of a :class:`ReportResult` (for tooling)."""
    payload = asdict(result)
    payload["report_json"] = str(result.report_json)
    payload["report_png"] = str(result.report_png)
    return payload


def assert_all_same_keys(rows: Iterable[GoldSampleMeta]) -> None:
    """Internal — verify no two samples share a key (sanity for the scanner)."""
    seen: set[str] = set()
    for r in rows:
        if r.key in seen:
            raise GoldScanError(f"duplicate sample key in gold dir: {r.key}")
        seen.add(r.key)
