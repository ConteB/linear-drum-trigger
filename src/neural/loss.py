"""Loss — F0-T4a §6 (Asymmetric Focal onset + masked L1 vel/mt + dense L1 hihat).

| Head          | Loss                              | Notes                                  |
| :--           | :--                               | :--                                    |
| onset         | Asymmetric Focal (FP 3× the FN's) | target Gaussian-smeared σ ↔ ±3 ms      |
| velocity      | L1 masked by ground-truth onset   | supervision only on frames with onset  |
| microtiming   | L1 masked by ground-truth onset   | idem                                   |
| hihat_opening | L1 dense                          | every frame                            |

Spec: ``docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`` §6.
"""
from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

from neural.model import HIHAT_OPENING_COL


@dataclass(frozen=True)
class LossConfig:
    """Inter-head loss weights and Asymmetric Focal hyperparameters.

    The default ``pos_weight`` of ~50 is the **alpha-balance** term implicit in
    canonical Focal Loss (Lin et al. 2017): on a 344 Hz frame grid an onset
    occupies ~1 / 250 frames per bus, so without class balancing the gradient
    is dominated by the easy negatives and the model collapses to ``p ≈ 0``.
    ``pos_weight`` and ``fp_to_fn_ratio`` are orthogonal: the former corrects
    the class prior, the latter is the doctrinal "FP costs 3× the FN" of
    F0-T4a §6 / DOSSIER §6.2.
    """

    # Per-head weights (F0-T4a §6 — "iperparametri di F0-T4b").
    w_onset: float = 1.0
    w_velocity: float = 0.5
    w_microtiming: float = 0.5
    w_hihat: float = 1.0
    # Asymmetric Focal hyperparameters (F0-T4a §6).
    focal_gamma: float = 2.0
    # Doctrinal asymmetry — FP weighted 3× the FN (F0-T4a §6, DOSSIER §6.2).
    fp_to_fn_ratio: float = 3.0
    # Class-imbalance correction (alpha-balance term implicit in Focal Loss).
    # Multiplies the FN term so the gradient is not buried by easy negatives.
    pos_weight: float = 50.0
    # Mask threshold on the Gaussian-smeared onset target — above this the
    # frame is considered "on" and the velocity/microtiming L1 contributes.
    onset_mask_threshold: float = 0.5


class TCNLoss(nn.Module):
    """The four-head loss for F0-T4b."""

    def __init__(self, config: LossConfig | None = None) -> None:
        super().__init__()
        self.config = config or LossConfig()

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
            pos_weight=self.config.pos_weight,
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
    pos_weight: float,
) -> torch.Tensor:
    """Asymmetric Focal BCE with FP/FN reweighting (F0-T4a §6).

    - The "positive" term penalises false negatives (model said no, truth said yes),
      scaled by ``pos_weight`` to correct the class imbalance (alpha-balance).
    - The "negative" term penalises false positives (model said yes, truth said no),
      scaled by ``fp_to_fn_ratio`` (the doctrinal "FP 3× FN" of F0-T4a §6 / DOSSIER §6.2).

    The target is the Gaussian-smeared onset matrix in ``[0, 1]``: we treat it
    as a soft probability target (BCE generalises naturally).
    """
    eps = 1e-7
    p_safe = p.clamp(eps, 1.0 - eps)
    # False-negative term: how confident we are saying "no" when the truth is "yes"
    fn = -t * ((1.0 - p_safe) ** gamma) * torch.log(p_safe)
    # False-positive term: how confident we are saying "yes" when the truth is "no"
    fp = -(1.0 - t) * (p_safe ** gamma) * torch.log(1.0 - p_safe)
    return torch.mean(pos_weight * fn + fp_to_fn_ratio * fp)


def _masked_l1(p: torch.Tensor, t: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """L1(p, t) reduced over the elements where ``mask > 0``.

    Returns zero (with a grad-safe path) when the mask is empty.
    """
    diff = torch.abs(p - t) * mask
    denom = mask.sum().clamp(min=1.0)
    return diff.sum() / denom


__all__ = ["LossConfig", "TCNLoss"]
