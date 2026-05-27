"""Loss — F0-T4a §6 (Asymmetric Focal onset + masked L1 vel/mt + dense L1 hihat).

| Head          | Loss                              | Notes                                  |
| :--           | :--                               | :--                                    |
| onset         | Asymmetric Focal (FP 3× the FN's) | target Gaussian-smeared σ ↔ ±3 ms      |
| velocity      | L1 masked by ground-truth onset   | supervision only on frames with onset  |
| microtiming   | L1 masked by ground-truth onset   | idem                                   |
| hihat_opening | L1 dense                          | every frame                            |

Spec: ``docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`` §6 (+ §6.1 F0-T4c amendment).

**F0-T4f extension (2026-05-27)** — three orthogonal additions, gated by
``LossConfig.kind`` and ``LossConfig.label_smoothing``:

- ``kind="ridnik"`` — Ridnik AsymmetricLoss (Alibaba MS-COCO 2020) with
  separated focusing γ+/γ- and probability shifting on the negative branch.
  Designed to attack the under-confidence on TPs revealed by Step A's
  calibration sweep (6/8 buses preferred T < 1.0).
- ``label_smoothing`` — soft target ``t * (1 - ε) + ε/2``; works with every
  ``kind``. Default 0.0 (backcompat). F0-T4f recommended value: 0.05.
- ``kind="tversky"`` — unchanged from 2026-05-25 Loss Competition.

Spec: ``docs/methodology/F0-T4f_STEP_B_LOSS_REDESIGN_SPEC.md`` §6.1.
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
    # FP/FN asymmetry. **F0-T4a §6 doctrine superseded by Loss Competition
    # 2026-05-25** — Decision Lock CEO: the original doctrine
    # ``fp_to_fn_ratio = 3`` produced "predict-everywhere" collapse on the
    # non-kick buses (FP/FN 23–86× on snare/hihat/floor/ride/crash,
    # confirmed by `docs/gates/F0-T4c_MINI_L3/listening_test_*` and
    # ratified by the loss competition: candidate B
    # (`fp_to_fn_ratio = 30`) emerged as the empirical winner
    # (ShittyKit val F 0.087 vs CTRL 0.084, hihat FP/FN 86→16). The new
    # default of 30 is the LOCKED operational value; the old 3.0 is
    # available via explicit override for backcompat with the F0-T4c
    # regression test.
    fp_to_fn_ratio: float = 30.0
    # Class-imbalance correction (alpha-balance term implicit in Focal Loss).
    # Scalar -> broadcast on all 8 buses; tuple of 8 -> per-bus weight (B6b).
    pos_weight: float | tuple[float, ...] = 200.0
    # Mask threshold on the Gaussian-smeared onset target — above this the
    # frame is considered "on" and the velocity/microtiming L1 contributes.
    onset_mask_threshold: float = 0.5
    # 2026-05-25 — sessione post-listening-test, CEO directive: testare design
    # di loss alternativi per il "predict-everywhere" collapse sui bus non-kick.
    # ``kind = "afl"`` (default, backcompat) = Asymmetric Focal BCE come sopra.
    # ``kind = "tversky"`` = soft Tversky loss `1 - TP/(TP + αFP + βFN)` su
    # probabilità continue, paradigma alternativo che penalizza FP letteralmente
    # invece che via BCE pesata.
    # ``kind = "ridnik"`` (F0-T4f, Decision Lock CEO 2026-05-27) = Ridnik
    # AsymmetricLoss (Alibaba MS-COCO 2020) — γ+ e γ- separati + probability
    # shifting sul ramo negative. Defaults dei parametri Ridnik sotto.
    kind: str = "afl"
    tversky_alpha: float = 0.7  # FP penalty (Tversky)
    tversky_beta: float = 0.3   # FN penalty (Tversky)
    tversky_smooth: float = 1.0  # numerical stability + cold-start anchor
    # F0-T4f Ridnik parameters — attivi solo quando ``kind="ridnik"``. I default
    # sono quelli canonici di Ridnik 2020 sul benchmark MS-COCO multi-label;
    # `gamma_pos < gamma_neg` è la firma asimmetrica che spinge la confidence
    # sui veri positivi (Step A calibration_sweep ha rilevato sotto-confidence).
    gamma_pos: float = 1.0
    gamma_neg: float = 4.0
    prob_clip_negative: float = 0.05  # probability shifting sul ramo negative
    # Label smoothing — F0-T4f Decision Lock CEO 2026-05-27. Applicato a target
    # binari (Gaussian-smeared già "soft", ma il picco è 1.0): t * (1-ε) + ε/2.
    # Attivo per ogni `kind` (afl/ridnik); default 0.0 = backcompat hard targets.
    # Per il preset "ridnik" il default operativo è 0.05; impostato a livello
    # di preset, non di config (mantiene backcompat dei test esistenti AFL).
    label_smoothing: float = 0.0
    # 2026-05-25 — sessione post-piano-roll-diagnostic. CEO directive: la
    # diagnostica edge_crop ha rivelato che 77 % dei FP totali sul val
    # ShittyKit cade nei primi 1024 frame (zona dove la convoluzione causale
    # vede zero-pad → output diffuso). ``edge_skip_frames`` skippa quel
    # range dal calcolo della loss (sia onset che velocity/microtiming/hihat
    # heads): la rete non viene punita per non discriminare in una zona
    # strutturalmente impossibile. Default 0 = backcompat con tutti i
    # checkpoint precedenti; usare 1024 (≈ 2.97 s, RF size) per i nuovi
    # training. Combinato con crop in valutazione, atteso F lift +20-40 %.
    edge_skip_frames: int = 0

    def __post_init__(self) -> None:
        if self.kind not in {"afl", "tversky", "ridnik"}:
            raise ValueError(
                f"kind must be 'afl', 'tversky' or 'ridnik', got {self.kind!r}"
            )
        if self.edge_skip_frames < 0:
            raise ValueError(
                f"edge_skip_frames must be >= 0, got {self.edge_skip_frames}"
            )
        if self.kind == "tversky":
            if not 0.0 < self.tversky_alpha:
                raise ValueError(
                    f"tversky_alpha must be > 0, got {self.tversky_alpha}"
                )
            if not 0.0 < self.tversky_beta:
                raise ValueError(
                    f"tversky_beta must be > 0, got {self.tversky_beta}"
                )
        if self.kind == "ridnik":
            if not 0.0 <= self.gamma_pos:
                raise ValueError(
                    f"gamma_pos must be >= 0, got {self.gamma_pos}"
                )
            if not 0.0 <= self.gamma_neg:
                raise ValueError(
                    f"gamma_neg must be >= 0, got {self.gamma_neg}"
                )
            if not 0.0 <= self.prob_clip_negative < 1.0:
                raise ValueError(
                    f"prob_clip_negative must be in [0, 1), got "
                    f"{self.prob_clip_negative}"
                )
        if not 0.0 <= self.label_smoothing < 1.0:
            raise ValueError(
                f"label_smoothing must be in [0, 1), got {self.label_smoothing}"
            )
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

        # Edge mask — Decision Lock CEO 2026-05-25 (post-piano-roll). Skip
        # the first ``edge_skip_frames`` of every batch sample from BOTH
        # heads: the causal TCN's RF is filled with zero-pad in this range
        # so any signal there is structurally unreliable. Training without
        # punishment in this zone keeps the network from learning
        # spurious patterns at the file edge.
        n_skip = self.config.edge_skip_frames
        if n_skip > 0 and onset_p.shape[1] > n_skip:
            onset_p = onset_p[:, n_skip:]
            onset_t = onset_t[:, n_skip:]
            velocity_p = velocity_p[:, n_skip:]
            velocity_t = velocity_t[:, n_skip:]
            microtiming_p = microtiming_p[:, n_skip:]
            microtiming_t = microtiming_t[:, n_skip:]
            hihat_p = hihat_p[:, n_skip:]
            hihat_t = hihat_t[:, n_skip:]

        # F0-T4f — apply label smoothing once, BEFORE dispatch (so every kind
        # sees the soft target consistently). For Gaussian-smeared targets in
        # [0, 1] the smoothing pulls the peak down from 1.0 to 1 - ε/2 and the
        # floor up from 0.0 to ε/2: t' = t * (1 - ε) + ε/2. The L1 onset mask
        # (used for velocity/microtiming) still uses the RAW target (pre-
        # smoothing) so the mask geometry is unchanged.
        if self.config.label_smoothing > 0.0:
            eps_ls = self.config.label_smoothing
            onset_t_loss = onset_t * (1.0 - eps_ls) + 0.5 * eps_ls
        else:
            onset_t_loss = onset_t

        if self.config.kind == "tversky":
            loss_onset = _tversky_loss(
                onset_p, onset_t_loss,
                alpha=self.config.tversky_alpha,
                beta=self.config.tversky_beta,
                smooth=self.config.tversky_smooth,
            )
        elif self.config.kind == "ridnik":
            loss_onset = _ridnik_asymmetric_loss(
                onset_p, onset_t_loss,
                gamma_pos=self.config.gamma_pos,
                gamma_neg=self.config.gamma_neg,
                prob_clip_negative=self.config.prob_clip_negative,
                fp_to_fn_ratio=self.config.fp_to_fn_ratio,
                pos_weight=self._pos_weight,  # type: ignore[arg-type]
            )
        else:
            loss_onset = _asymmetric_focal_bce(
                onset_p, onset_t_loss,
                gamma=self.config.focal_gamma,
                fp_to_fn_ratio=self.config.fp_to_fn_ratio,
                pos_weight=self._pos_weight,
            )

        # Velocity / microtiming: L1, masked by the ground-truth onset.
        # Use the RAW target for mask geometry (label smoothing only affects
        # the BCE term, not the L1-supervision mask).
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


def _tversky_loss(
    p: torch.Tensor,
    t: torch.Tensor,
    *,
    alpha: float,
    beta: float,
    smooth: float,
) -> torch.Tensor:
    """Soft Tversky loss on the onset head (2026-05-25 candidate D).

    Tversky index (generalisation of Dice for asymmetric FP/FN):
      ``T = (TP + smooth) / (TP + α·FP + β·FN + smooth)``
    Loss = ``1 - T``, averaged across buses.

    Operates on continuous probabilities (the Gaussian-smeared target is
    treated as soft 0..1; ``p * t`` is the soft TP). ``smooth`` anchors the
    cold start (when TP ≈ 0 the gradient is dominated by the constant
    smooth term, preventing the loss from saturating at 1.0).

    Per-bus computation: TP/FP/FN are summed across (B, T) but the loss is
    averaged across the bus dim, so each bus has equal weight in the total
    gradient (no class-imbalance correction needed — the formula handles it
    structurally via α/β).
    """
    # Soft confusion components per bus. ``p`` is already in [0, 1] (sigmoid
    # output upstream), ``t`` is the Gaussian-smeared target also in [0, 1].
    tp = (p * t).sum(dim=(0, 1))            # [N_BUSES]
    fp = (p * (1.0 - t)).sum(dim=(0, 1))    # [N_BUSES]
    fn = ((1.0 - p) * t).sum(dim=(0, 1))    # [N_BUSES]
    tversky = (tp + smooth) / (tp + alpha * fp + beta * fn + smooth)
    return (1.0 - tversky).mean()


def _ridnik_asymmetric_loss(
    p: torch.Tensor,
    t: torch.Tensor,
    *,
    gamma_pos: float,
    gamma_neg: float,
    prob_clip_negative: float,
    fp_to_fn_ratio: float,
    pos_weight: torch.Tensor,
) -> torch.Tensor:
    """Ridnik AsymmetricLoss (Alibaba MS-COCO 2020, F0-T4f).

    Reformulation of the AFL with two distinct focusing exponents (γ+, γ-)
    and *probability shifting* on the negative branch. The signature target
    of Step B is the **under-confidence on TPs** revealed by Step A's
    calibration sweep: 6/8 buses preferred T < 1.0, the sigmoid 0.05–0.20
    on true positives is structural, not anecdotal.

    - **γ_pos < γ_neg** (default 1.0 vs 4.0) — the focusing on the positive
      branch is gentler. AFL with γ=2 punishes "easy" TPs (those already
      at sigmoid > 0.5) almost as much as it does easy negatives; Ridnik
      lets the gradient on the positive branch carry weight even for the
      already-correct TPs, pushing them further toward 1.0.
    - **prob_clip_negative** (default 0.05) — shifts ``xs_neg = (1 - p) +
      clip``, then clamps to 1.0. Negatives with ``p < clip`` end up with
      ``log(xs_neg) ≈ 0`` ⇒ zero contribution. Filters the noise from the
      sea of trivially-correct TNs (~99 % of frames are negatives in our
      sparse multi-label setup).
    - **pos_weight** + **fp_to_fn_ratio** preserved from the AFL path
      (F0-T4c B6b + Loss Competition B). Density-derived per-bus weighting
      keeps the rare cymbal buses (crash_a 0.7 %) from being drowned by
      the common buses (snare 8 %).

    Inputs:
        p : [B, T, N_BUSES] in [0, 1] (model sigmoid output).
        t : [B, T, N_BUSES] Gaussian-smeared target in [0, 1]; may be
            label-smoothed upstream.
        pos_weight : [N_BUSES] or [1] tensor, per-bus FN penalty (broadcast).

    Returns scalar loss (mean over B*T*N_BUSES).
    """
    eps = 1e-7
    xs_pos = p.clamp(eps, 1.0 - eps)
    xs_neg = (1.0 - xs_pos + prob_clip_negative).clamp(max=1.0)
    log_pos = torch.log(xs_pos)
    log_neg = torch.log(xs_neg.clamp(min=eps))

    # Per-branch base loss — negative log-likelihood form.
    loss_pos = pos_weight * t * log_pos                          # [B, T, N_BUSES]
    loss_neg = fp_to_fn_ratio * (1.0 - t) * log_neg              # [B, T, N_BUSES]

    # Asymmetric focusing. Build ``one_sided_gamma`` per-element: on a
    # frame with target ≈ 1 the exponent is gamma_pos; on a frame with
    # target ≈ 0 it is gamma_neg. Continuous targets blend the two.
    pt0 = xs_pos * t                       # how confidently we hit positives
    pt1 = xs_neg * (1.0 - t)               # how confidently we hit negatives
    pt = pt0 + pt1                         # focusing strength per-element
    one_sided_gamma = gamma_pos * t + gamma_neg * (1.0 - t)
    one_sided_w = (1.0 - pt).clamp(min=eps) ** one_sided_gamma

    # Negate (NLL) and apply focusing weight, then mean.
    loss = -(loss_pos + loss_neg) * one_sided_w
    return loss.mean()


def _masked_l1(p: torch.Tensor, t: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """L1(p, t) reduced over the elements where ``mask > 0``.

    Returns zero (with a grad-safe path) when the mask is empty.
    """
    diff = torch.abs(p - t) * mask
    denom = mask.sum().clamp(min=1.0)
    return diff.sum() / denom


__all__ = [
    "LossConfig",
    "N_BUSES",
    "POS_WEIGHT_CAP",
    "TCNLoss",
    "_ridnik_asymmetric_loss",
]
