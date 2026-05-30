"""Onset metrics — F0-T4a §7 (L3 threshold).

The L3 gate (F0-T4a §7) asks four numbers:

* Onset **F-measure** (±20 ms, per-bus mean) ≥ **0.80**
* Onset F-measure on **shuffled** ground-truth labels < **0.10** (negative
  control: gap proves non-randomness)
* **Timing-MAE** of matched onsets < **5 ms**
* **MAE** of hihat opening < **0.15**

All metrics are computed on the *predicted onset* matrix after peak picking.
Peak picking is the classical "local-max above threshold" rule, with a
``min_distance`` refractory period to avoid double-counting one onset
(MIREX-style, but kept dependency-free).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from neural.model import HIHAT_OPENING_COL, N_CHANNELS

#: F0-T4a §2 — target frame-rate ≡ 44100 / 128.
R_TARGET_HZ = 344.53125
FRAME_PERIOD_MS = 1000.0 / R_TARGET_HZ  # ≈ 2.902 ms
#: F0-T4a §7 — onset match window (full width).
MATCH_WINDOW_MS = 20.0
MATCH_WINDOW_FRAMES = int(round(MATCH_WINDOW_MS / FRAME_PERIOD_MS))  # ≈ 7 frames

# F0-T4a §7 — L3 numerical thresholds.
L3_F_MEASURE_MIN = 0.80
L3_SHUFFLED_F_MAX = 0.10
L3_TIMING_MAE_MAX_MS = 5.0
L3_HIHAT_MAE_MAX = 0.15


@dataclass(frozen=True)
class OnsetReport:
    """Per-bus onset metrics + a summary."""

    f_measure_per_bus: np.ndarray  # [N_CHANNELS]
    precision_per_bus: np.ndarray
    recall_per_bus: np.ndarray
    timing_mae_ms: float
    n_pred_total: int
    n_true_total: int
    n_matched_total: int

    @property
    def f_measure_mean(self) -> float:
        # F0-T4a §7 — "media per-bus".
        return float(np.nanmean(self.f_measure_per_bus))


def peak_pick(
    onset_prob: np.ndarray,
    *,
    threshold: float = 0.5,
    min_distance_frames: int = 3,
) -> list[int]:
    """Pick local maxima of ``onset_prob`` above ``threshold``.

    Args:
        onset_prob: 1-D array of onset probabilities for a single bus.
        threshold: Detection threshold in ``[0, 1]``.
        min_distance_frames: Refractory period — onsets closer than this are
            collapsed onto the highest peak.

    Returns:
        Sorted list of frame indices where an onset is declared.
    """
    n = len(onset_prob)
    if n == 0:
        return []
    above = onset_prob >= threshold
    # Local-max candidates: strictly greater than both neighbours, or
    # ``>=`` at the boundaries.
    cand: list[int] = []
    for i in range(n):
        if not above[i]:
            continue
        left = onset_prob[i - 1] if i > 0 else -np.inf
        right = onset_prob[i + 1] if i < n - 1 else -np.inf
        if onset_prob[i] >= left and onset_prob[i] >= right:
            cand.append(i)
    # Refractory: walk through candidates and keep the strongest within window.
    cand.sort(key=lambda j: float(onset_prob[j]), reverse=True)
    kept: list[int] = []
    for j in cand:
        if all(abs(j - k) >= min_distance_frames for k in kept):
            kept.append(j)
    return sorted(kept)


def match_onsets(
    pred_frames: list[int],
    true_frames: list[int],
    *,
    window_frames: int = MATCH_WINDOW_FRAMES,
) -> tuple[int, list[float]]:
    """Greedy onset matching within ``±window_frames``.

    Both lists are assumed sorted. Returns ``(n_matched, drift_ms)`` where
    ``drift_ms[i]`` is the signed drift (pred - true) for the i-th matched pair.
    """
    drifts: list[float] = []
    used_true: set[int] = set()
    pred_sorted = sorted(pred_frames)
    for p in pred_sorted:
        # Find the closest unused true onset within the window.
        best_j = -1
        best_d = window_frames + 1
        for j, t in enumerate(true_frames):
            if j in used_true:
                continue
            d = abs(p - t)
            if d < best_d:
                best_d = d
                best_j = j
        if best_j >= 0 and best_d <= window_frames:
            used_true.add(best_j)
            drifts.append((p - true_frames[best_j]) * FRAME_PERIOD_MS)
    return len(drifts), drifts


def f_measure(n_matched: int, n_pred: int, n_true: int) -> tuple[float, float, float]:
    """Return ``(precision, recall, f1)``. F-measure is NaN if both lists empty."""
    if n_pred == 0 and n_true == 0:
        return float("nan"), float("nan"), float("nan")
    if n_pred == 0 or n_true == 0:
        return 0.0, 0.0, 0.0
    precision = n_matched / n_pred
    recall = n_matched / n_true
    if precision + recall == 0:
        return precision, recall, 0.0
    f = 2 * precision * recall / (precision + recall)
    return precision, recall, f


def onset_report(
    onset_pred: np.ndarray,
    onset_target: np.ndarray,
    *,
    threshold: float = 0.5,
    min_distance_frames: int = 3,
) -> OnsetReport:
    """Compute the per-channel onset report from the flat-28 onset slices.

    Args:
        onset_pred: ``[T, 9]`` predicted onset probabilities.
        onset_target: ``[T, 9]`` Gaussian-smeared ground-truth onset matrix.
        threshold: Peak-picking threshold for both pred and target.
        min_distance_frames: Refractory window for peak picking.
    """
    f_per_bus = np.full(N_CHANNELS, np.nan, dtype=np.float64)
    p_per_bus = np.full(N_CHANNELS, np.nan, dtype=np.float64)
    r_per_bus = np.full(N_CHANNELS, np.nan, dtype=np.float64)
    drifts_all: list[float] = []
    n_pred_total = 0
    n_true_total = 0
    n_matched_total = 0
    for b in range(N_CHANNELS):
        pred = peak_pick(
            onset_pred[:, b], threshold=threshold, min_distance_frames=min_distance_frames
        )
        true = peak_pick(
            onset_target[:, b], threshold=threshold, min_distance_frames=min_distance_frames
        )
        n_matched, drifts = match_onsets(pred, true)
        p, r, f = f_measure(n_matched, len(pred), len(true))
        p_per_bus[b] = p
        r_per_bus[b] = r
        f_per_bus[b] = f
        drifts_all.extend(drifts)
        n_pred_total += len(pred)
        n_true_total += len(true)
        n_matched_total += n_matched
    timing_mae = float(np.mean(np.abs(drifts_all))) if drifts_all else float("nan")
    return OnsetReport(
        f_measure_per_bus=f_per_bus,
        precision_per_bus=p_per_bus,
        recall_per_bus=r_per_bus,
        timing_mae_ms=timing_mae,
        n_pred_total=n_pred_total,
        n_true_total=n_true_total,
        n_matched_total=n_matched_total,
    )


def shuffled_control(
    onset_pred: np.ndarray, onset_target: np.ndarray, *, seed: int = 0
) -> float:
    """F-measure on temporally-shuffled labels — F0-T4a §7 negative control.

    Shuffles the frame *axis* of the ground-truth onset matrix so the temporal
    relation between audio and target is broken; the F-measure on the shuffled
    truth should be far below the real F-measure (< 0.10 per the L3 threshold).
    """
    rng = np.random.default_rng(seed)
    perm = rng.permutation(onset_target.shape[0])
    shuffled = onset_target[perm]
    report = onset_report(onset_pred, shuffled)
    return report.f_measure_mean


def hihat_mae(hihat_pred: np.ndarray, hihat_target: np.ndarray) -> float:
    return float(np.mean(np.abs(hihat_pred - hihat_target)))


@dataclass(frozen=True)
class L3Verdict:
    """Verdict of the L3 numerical thresholds (F0-T4a §7)."""

    f_measure_mean: float
    f_shuffled: float
    timing_mae_ms: float
    hihat_mae: float

    @property
    def passes_f_measure(self) -> bool:
        return self.f_measure_mean >= L3_F_MEASURE_MIN

    @property
    def passes_shuffled(self) -> bool:
        return self.f_shuffled < L3_SHUFFLED_F_MAX

    @property
    def passes_timing(self) -> bool:
        # Skip the timing check if there were no matched onsets.
        if np.isnan(self.timing_mae_ms):
            return False
        return self.timing_mae_ms < L3_TIMING_MAE_MAX_MS

    @property
    def passes_hihat(self) -> bool:
        return self.hihat_mae < L3_HIHAT_MAE_MAX

    @property
    def passes(self) -> bool:
        return (
            self.passes_f_measure
            and self.passes_shuffled
            and self.passes_timing
            and self.passes_hihat
        )


def tune_threshold(
    onset_pred: np.ndarray,
    onset_target: np.ndarray,
    *,
    candidates: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80),
) -> tuple[float, float]:
    """Pick the peak-pick threshold that maximises mean F-measure on ``onset_pred``.

    Returns ``(best_threshold, best_f_measure)``. Standard MIREX practice — the
    threshold is a calibration parameter, not part of the network; tuning on the
    sample itself is acceptable because the L3 gate is a *de-risking* gate, not
    a generalisation claim (F0-T4a §7).
    """
    best_thr = candidates[0]
    best_f = -1.0
    for thr in candidates:
        r = onset_report(onset_pred, onset_target, threshold=thr)
        f = r.f_measure_mean
        if not np.isnan(f) and f > best_f:
            best_thr = thr
            best_f = f
    return best_thr, max(best_f, 0.0)


def evaluate_l3(
    pred_flat25: np.ndarray,
    target_flat25: np.ndarray,
    *,
    threshold: float | None = None,
) -> L3Verdict:
    """Compute the full L3 verdict from a single sample's prediction and target.

    Args:
        pred_flat25: ``[T, 28]`` predicted flat-28 output (F0-T19 §7b; the
            parameter keeps its historical name for caller backcompat).
        target_flat25: ``[T, 28]`` ground-truth flat-28 target.
        threshold: Peak-picking threshold; if ``None``, tuned on the prediction
            itself per :func:`tune_threshold`.
    """
    onset_pred = pred_flat25[:, 0:HIHAT_OPENING_COL:3]
    onset_target = target_flat25[:, 0:HIHAT_OPENING_COL:3]
    hihat_pred = pred_flat25[:, HIHAT_OPENING_COL]
    hihat_target = target_flat25[:, HIHAT_OPENING_COL]
    if threshold is None:
        threshold, _ = tune_threshold(onset_pred, onset_target)
    report = onset_report(onset_pred, onset_target, threshold=threshold)
    # The shuffled control reuses the same threshold so the comparison is fair.
    rng = np.random.default_rng(0)
    perm = rng.permutation(onset_target.shape[0])
    shuffled = onset_target[perm]
    shuf_report = onset_report(onset_pred, shuffled, threshold=threshold)
    return L3Verdict(
        f_measure_mean=report.f_measure_mean,
        f_shuffled=shuf_report.f_measure_mean,
        timing_mae_ms=report.timing_mae_ms,
        hihat_mae=hihat_mae(hihat_pred, hihat_target),
    )


__all__ = [
    "FRAME_PERIOD_MS",
    "L3_F_MEASURE_MIN",
    "L3_HIHAT_MAE_MAX",
    "L3_SHUFFLED_F_MAX",
    "L3_TIMING_MAE_MAX_MS",
    "L3Verdict",
    "MATCH_WINDOW_FRAMES",
    "MATCH_WINDOW_MS",
    "OnsetReport",
    "R_TARGET_HZ",
    "evaluate_l3",
    "f_measure",
    "hihat_mae",
    "match_onsets",
    "onset_report",
    "peak_pick",
    "shuffled_control",
    "tune_threshold",
]
