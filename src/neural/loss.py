"""Loss — F0-T4a §6 (Asymmetric Focal onset + masked L1 vel/mt + dense L1 hihat).

| Head          | Loss                              | Notes                                  |
| :--           | :--                               | :--                                    |
| onset         | Asymmetric Focal (FP 3× the FN's) | target Gaussian-smeared σ ↔ ±3 ms      |
| velocity      | L1 masked by ground-truth onset   | supervision only on frames with onset  |
| microtiming   | L1 masked by ground-truth onset   | idem                                   |
| hihat_opening | L1 dense                          | every frame                            |

Spec: ``docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`` §6 (+ §6.1 F0-T4c amendment).
"""
from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

from neural.model import HIHAT_OPENING_COL

#: Number of output buses on the onset/velocity/microtiming heads
#: (F0-T4a §3, ``flat-25`` layout). Used by the per-bus ``pos_weight`` tuple
#: validation in :class:`LossConfig`.
N_BUSES: int = 8

#: Maximum allowed value of any element in a per-bus ``pos_weight`` tuple
#: (F0-T4c B6b — Decision Lock CEO 2026-05-24). Caps gradient explosion on
#: buses with density ≈ 0 (safe by construction: no positives = no FN term
#: weighed by ``pos_weight``).
POS_WEIGHT_CAP: float = 1000.0


@dataclass(frozen=True)
class LossConfig:
    """Inter-head loss weights and Asymmetric Focal hyperparameters.

    **F0-T4c B3 amendment** (Decision Lock CEO 2026-05-24): defaults
    riparametrizzati dalla density misurata sul Gold mix (0.4-1.5 % vs il
    ~5 % baseline di Lin 2017 → ``pos_weight = 200`` invece di 50). Per-head
    weights ribilanciati per dare priorità al gradient dell'onset
    (segnale primario) e ridurre il peso di velocity/microtiming/hihat
    (storicamente dominavano il loss totale nel regime sparso).

    **F0-T4c B6b amendment**: ``pos_weight`` accetta ora ``float`` (broadcast
    su tutti gli 8 bus, comportamento legacy) **o** ``tuple[float, ...]`` di
    lunghezza ``N_BUSES = 8`` (un peso per bus, calcolato da
    :mod:`tools.scan_density`). Quando è tuple, ``train.py`` attiva
    automaticamente il :class:`WeightedRandomSampler` (B6a).
    """

    # Per-head weights — F0-T4c B3 amendment (Decision Lock CEO 2026-05-24).
    w_onset: float = 2.0
    w_velocity: float = 0.1
    w_microtiming: float = 0.1
    w_hihat: float = 0.25
    # Asymmetric Focal hyperparameters (F0-T4a §6).
    focal_gamma: float = 2.0
    # Doctrinal asymmetry — FP weighted 3× the FN (F0-T4a §6, DOSSIER §6.2).
    fp_to_fn_ratio: float = 3.0
    # Class-imbalance correction (alpha-balance term implicit in Focal Loss).
    # Scalar -> broadcast on all 8 buses; tuple of 8 -> per-bus weight (B6b).
    pos_weight: float | tuple[float, ...] = 200.0
    # Mask threshold on the Gaussian-smeared onset target — above this the
    # frame is considered "on" and the velocity/microtiming L1 contributes.
    onset_mask_threshold: float = 0.5

    def __post_init__(self) -> None:
        # Fail-loud on per-bus ``pos_weight`` tuple of wrong length or
        # out-of-range values (F0-T4c B6b).
        if isinstance(self.pos_weight, tuple):
            if len(self.pos_weight) != N_BUSES:
                raise ValueError(
                    f"pos_weight tuple must have {N_BUSES} elements, "
                    f"got {len(self.pos_weight)}"
                )
            for i, w in enumerate(self.pos_weight):
                if not 0.0 <= float(w) <= POS_WEIGHT_CAP:
                    raise ValueError(
                        f"pos_weight[{i}] = {w} outside [0, {POS_WEIGHT_CAP}] "
                        f"(F0-T4c B6b safety cap)"
                    )
        elif isinstance(self.pos_weight, (int, float)):
            if not 0.0 <= float(self.pos_weight) <= POS_WEIGHT_CAP:
                raise ValueError(
                    f"pos_weight = {self.pos_weight} outside [0, {POS_WEIGHT_CAP}]"
                )
        else:
            raise TypeError(
                f"pos_weight must be float or tuple of {N_BUSES} floats, "
                f"got {type(self.pos_weight).__name__}"
            )


class TCNLoss(nn.Module):
    """The four-head loss for F0-T4b."""

    def __init__(self, config: LossConfig | None = None) -> None:
        super().__init__()
        self.config = config or LossConfig()
        # Pre-build the per-bus pos_weight tensor once — avoids per-step
        # allocations in the hot path. For scalar pos_weight a 1-element
        # tensor still broadcasts correctly across the bus dimension.
        pw = self.config.pos_weight
        if isinstance(pw, tuple):
            pw_tensor = torch.tensor(pw, dtype=torch.float32)  # [N_BUSES]
        else:
            pw_tensor = torch.tensor([float(pw)], dtype=torch.float32)  # [1]
        # ``register_buffer`` keeps it on the same device as the model under
        # ``.to(device)`` without being a learnable parameter.
        self.register_buffer("_pos_weight", pw_tensor, persistent=False)

    def forward(
        self, pred: torch.Tensor, target: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        # pred / target: [B, T, 25] — flat-25 layout.
        # Slice the four heads from flat-25.
        onset_p = pred[..., 0:24:3]  # [B, T, 8]
        velocity_p = pred[..., 1:24:3]
        microtiming_p = pred[..., 2:24:3]
        hihat_p = pred[..., HIHAT_OPENING_COL]  # [B, T]

        onset_t = target[..., 0:24:3]
        velocity_t = target[..., 1:24:3]
        microtiming_t = target[..., 2:24:3]
        hihat_t = target[..., HIHAT_OPENING_COL]

        loss_onset = _asymmetric_focal_bce(
            onset_p, onset_t,
            gamma=self.config.focal_gamma,
            fp_to_fn_ratio=self.config.fp_to_fn_ratio,
            pos_weight=self._pos_weight,
        )

        # Velocity / microtiming: L1, masked by the ground-truth onset.
        mask = (onset_t > self.config.onset_mask_threshold).to(pred.dtype)
        loss_velocity = _masked_l1(velocity_p, velocity_t, mask)
        loss_microtiming = _masked_l1(microtiming_p, microtiming_t, mask)

        loss_hihat = torch.mean(torch.abs(hihat_p - hihat_t))

        total = (
            self.config.w_onset * loss_onset
            + self.config.w_velocity * loss_velocity
            + self.config.w_microtiming * loss_microtiming
            + self.config.w_hihat * loss_hihat
        )

        return {
            "total": total,
            "onset": loss_onset.detach(),
            "velocity": loss_velocity.detach(),
            "microtiming": loss_microtiming.detach(),
            "hihat": loss_hihat.detach(),
        }


def _asymmetric_focal_bce(
    p: torch.Tensor,
    t: torch.Tensor,
    *,
    gamma: float,
    fp_to_fn_ratio: float,
    pos_weight: torch.Tensor,
) -> torch.Tensor:
    """Asymmetric Focal BCE with FP/FN reweighting (F0-T4a §6).

    - The "positive" term penalises false negatives (model said no, truth said yes),
      scaled by ``pos_weight`` to correct the class imbalance (alpha-balance).
    - The "negative" term penalises false positives (model said yes, truth said no),
      scaled by ``fp_to_fn_ratio`` (the doctrinal "FP 3× FN" of F0-T4a §6 / DOSSIER §6.2).

    The target is the Gaussian-smeared onset matrix in ``[0, 1]``: we treat it
    as a soft probability target (BCE generalises naturally).

    **F0-T4c B6b**: ``pos_weight`` is a ``[N_BUSES]`` tensor (or ``[1]`` for
    backward-compat scalar). It broadcasts on the last dim of ``p``/``t``
    (shape ``[B, T, N_BUSES]`` for the onset head), so each bus gets its own
    class-imbalance correction.
    """
    eps = 1e-7
    p_safe = p.clamp(eps, 1.0 - eps)
    # False-negative term: how confident we are saying "no" when the truth is "yes"
    fn = -t * ((1.0 - p_safe) ** gamma) * torch.log(p_safe)
    # False-positive term: how confident we are saying "yes" when the truth is "no"
    fp = -(1.0 - t) * (p_safe ** gamma) * torch.log(1.0 - p_safe)
    # pos_weight broadcasts over [B, T, N_BUSES] on the last dim.
    return torch.mean(pos_weight * fn + fp_to_fn_ratio * fp)


def _masked_l1(p: torch.Tensor, t: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """L1(p, t) reduced over the elements where ``mask > 0``.

    Returns zero (with a grad-safe path) when the mask is empty.
    """
    diff = torch.abs(p - t) * mask
    denom = mask.sum().clamp(min=1.0)
    return diff.sum() / denom


__all__ = ["LossConfig", "N_BUSES", "POS_WEIGHT_CAP", "TCNLoss"]
