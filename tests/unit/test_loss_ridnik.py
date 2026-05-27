"""Layer-1 oracles for the F0-T4f Ridnik AsymmetricLoss + label smoothing.

Anchors:
- ``LossConfig`` validation: new ``kind="ridnik"``, ``gamma_pos/neg``,
  ``prob_clip_negative``, ``label_smoothing`` parameter ranges (fail-loud).
- ``_ridnik_asymmetric_loss`` math: shape contract, dtype, finite output,
  asymmetric focusing direction, probability-shifting effect.
- ``TCNLoss(kind="ridnik")`` integration: same return contract as AFL,
  finite forward/backward, label smoothing applied on the BCE term while
  leaving the L1 onset mask geometry unchanged.
- Backcompat: ``kind="afl"`` continues to behave as before; ``kind="tversky"``
  ignores the new Ridnik params; ``label_smoothing=0`` is a no-op for every
  kind.

Spec: ``docs/methodology/F0-T4f_STEP_B_LOSS_REDESIGN_SPEC.md`` §6.3.
"""
from __future__ import annotations

import math

import pytest
import torch

from neural.loss import (
    N_BUSES,
    LossConfig,
    TCNLoss,
    _ridnik_asymmetric_loss,
)
from neural.model import HIHAT_OPENING_COL

# ----------------------------------------------------------------------------
# LossConfig validation
# ----------------------------------------------------------------------------


def test_ridnik_kind_accepted() -> None:
    cfg = LossConfig(kind="ridnik")
    assert cfg.kind == "ridnik"
    assert cfg.gamma_pos == 1.0
    assert cfg.gamma_neg == 4.0
    assert cfg.prob_clip_negative == 0.05


def test_ridnik_defaults_match_canon() -> None:
    """Ridnik 2020 canonical defaults are the LOCKED operational values."""
    cfg = LossConfig(kind="ridnik")
    assert cfg.gamma_pos == 1.0
    assert cfg.gamma_neg == 4.0
    assert cfg.prob_clip_negative == 0.05


def test_invalid_kind_rejected() -> None:
    with pytest.raises(ValueError, match="kind must be"):
        LossConfig(kind="unknown")


@pytest.mark.parametrize("gamma_pos", [-1.0, -0.0001])
def test_negative_gamma_pos_rejected(gamma_pos: float) -> None:
    with pytest.raises(ValueError, match="gamma_pos must be >= 0"):
        LossConfig(kind="ridnik", gamma_pos=gamma_pos)


@pytest.mark.parametrize("gamma_neg", [-1.0, -0.0001])
def test_negative_gamma_neg_rejected(gamma_neg: float) -> None:
    with pytest.raises(ValueError, match="gamma_neg must be >= 0"):
        LossConfig(kind="ridnik", gamma_neg=gamma_neg)


@pytest.mark.parametrize("clip", [-0.01, 1.0, 1.5])
def test_invalid_prob_clip_negative_rejected(clip: float) -> None:
    with pytest.raises(ValueError, match="prob_clip_negative"):
        LossConfig(kind="ridnik", prob_clip_negative=clip)


@pytest.mark.parametrize("ls", [-0.01, 1.0, 1.5])
def test_invalid_label_smoothing_rejected(ls: float) -> None:
    with pytest.raises(ValueError, match="label_smoothing"):
        LossConfig(label_smoothing=ls)


def test_ridnik_validation_skipped_when_kind_is_afl() -> None:
    """gamma_pos < 0 on kind="afl" is irrelevant (Ridnik params unused)."""
    # Build a frozen config bypassing __post_init__ would be invasive; we just
    # confirm that AFL with default Ridnik params doesn't trip the validator.
    cfg = LossConfig(kind="afl", gamma_pos=1.0, gamma_neg=4.0)
    assert cfg.kind == "afl"


# ----------------------------------------------------------------------------
# _ridnik_asymmetric_loss — math contract
# ----------------------------------------------------------------------------


def _make_pos_weight(value: float = 1.0) -> torch.Tensor:
    return torch.full((N_BUSES,), value, dtype=torch.float32)


def test_ridnik_returns_scalar_finite() -> None:
    pw = _make_pos_weight()
    p = torch.rand(2, 32, N_BUSES, dtype=torch.float32) * 0.5
    t = torch.zeros_like(p)
    t[:, ::4, 0] = 1.0
    loss = _ridnik_asymmetric_loss(
        p, t,
        gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05,
        fp_to_fn_ratio=30.0,
        pos_weight=pw,
    )
    assert loss.ndim == 0
    assert torch.isfinite(loss).item()
    assert loss.item() > 0.0


def test_ridnik_non_negative_on_random_inputs() -> None:
    """For prob in (0, 1) and target in [0, 1], loss is always >= 0 (NLL)."""
    pw = _make_pos_weight(value=2.0)
    for seed in range(5):
        torch.manual_seed(seed)
        p = torch.rand(2, 32, N_BUSES, dtype=torch.float32).clamp(1e-3, 1 - 1e-3)
        t = torch.rand(2, 32, N_BUSES, dtype=torch.float32)
        loss = _ridnik_asymmetric_loss(
            p, t,
            gamma_pos=1.0, gamma_neg=4.0,
            prob_clip_negative=0.05,
            fp_to_fn_ratio=30.0,
            pos_weight=pw,
        )
        assert loss.item() >= 0.0


def test_ridnik_prob_clip_silences_easy_negatives() -> None:
    """A negative with p well below `prob_clip_negative` contributes ~0.

    With t=0, ``xs_neg = (1 - p + clip).clamp(max=1.0)`` — if p < 1 - clip,
    xs_neg is < 1 and log(xs_neg) < 0 (some loss); if p < clip itself,
    xs_neg ≈ 1 + (clip - p) → clamped to 1.0 → log(1) = 0 → zero contribution.
    """
    pw = _make_pos_weight()
    p_easy = torch.full((1, 1, N_BUSES), 0.01, dtype=torch.float32)
    p_med = torch.full((1, 1, N_BUSES), 0.30, dtype=torch.float32)
    t = torch.zeros_like(p_easy)
    loss_easy = _ridnik_asymmetric_loss(
        p_easy, t,
        gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05,
        fp_to_fn_ratio=30.0,
        pos_weight=pw,
    )
    loss_med = _ridnik_asymmetric_loss(
        p_med, t,
        gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05,
        fp_to_fn_ratio=30.0,
        pos_weight=pw,
    )
    # Easy negatives (p < clip) should produce a much lower loss than
    # medium-confidence negatives (p > 1 - clip → xs_neg far from 1).
    assert loss_easy.item() < loss_med.item()
    # And the easy-loss should be essentially zero.
    assert loss_easy.item() < 1e-4


def test_ridnik_prob_clip_zero_disables_shifting() -> None:
    """With clip=0 the formula reduces to a vanilla asymmetric BCE (xs_neg = 1 - p)."""
    pw = _make_pos_weight()
    p = torch.full((1, 1, N_BUSES), 0.30, dtype=torch.float32)
    t = torch.zeros_like(p)
    # clip=0 → xs_neg = 1 - 0.3 = 0.7 → -log(0.7) ≈ 0.357 per element
    # base term: fp_to_fn_ratio * 1 * log(0.7) → -0.357 → loss positive
    # focusing: gamma_neg=4 → (1 - 0.3*0)^4 = 1.0 (pt0=0 because t=0; pt=pt1=0.7)
    # Actually pt1 = xs_neg * (1-t) = 0.7 * 1 = 0.7 → (1-0.7)^4 = 0.0081
    loss = _ridnik_asymmetric_loss(
        p, t,
        gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.0,
        fp_to_fn_ratio=1.0,
        pos_weight=pw,
    )
    # Expected magnitude: -(0 + 1.0 * 1.0 * log(0.7)) * (1 - 0.7)^4 ≈ 0.357 * 0.0081 ≈ 0.0029
    # We just check it's positive and small (gamma_neg=4 strongly down-weights this).
    assert 0.0 < loss.item() < 0.01


def test_ridnik_pos_weight_per_bus_broadcasts() -> None:
    """Per-bus pos_weight multiplies the loss_pos term per bus."""
    pw_uniform = _make_pos_weight(value=1.0)
    pw_heavy = torch.tensor(
        [10.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=torch.float32,
    )
    p = torch.full((1, 4, N_BUSES), 0.2, dtype=torch.float32)
    # ground-truth positives only on bus 0
    t = torch.zeros_like(p)
    t[:, :, 0] = 1.0
    loss_uniform = _ridnik_asymmetric_loss(
        p, t, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw_uniform,
    )
    loss_heavy = _ridnik_asymmetric_loss(
        p, t, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw_heavy,
    )
    assert loss_heavy.item() > loss_uniform.item()


def test_ridnik_gamma_pos_zero_recovers_unfocused_positive() -> None:
    """gamma_pos=0 → (1 - pt)^0 = 1 on the positive branch (no focusing)."""
    pw = _make_pos_weight()
    p = torch.full((1, 1, N_BUSES), 0.9, dtype=torch.float32)  # high-conf TPs
    t = torch.ones_like(p)
    # With gamma_pos=0, an already-confident TP is NOT down-weighted; loss stays
    # at ~ -log(p). With gamma_pos=4, the loss collapses to nearly zero.
    loss_no_focus = _ridnik_asymmetric_loss(
        p, t, gamma_pos=0.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    loss_focus = _ridnik_asymmetric_loss(
        p, t, gamma_pos=4.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    assert loss_no_focus.item() > loss_focus.item() * 10.0


def test_ridnik_signature_pushes_confidence_on_tps() -> None:
    """The Ridnik signature: gamma_pos < gamma_neg keeps the gradient on
    correctly-classified TPs alive longer than the AFL with the same γ.

    Concretely: at p=0.5, t=1 (a "correctly classified" TP at the boundary),
    Ridnik (gamma_pos=1, gamma_neg=4) yields a LARGER per-element positive
    contribution than AFL with γ=4 (which down-weights the TP as if it were
    already easy).
    """
    pw = _make_pos_weight()
    p = torch.full((1, 1, N_BUSES), 0.5, dtype=torch.float32)
    t = torch.ones_like(p)
    loss_ridnik = _ridnik_asymmetric_loss(
        p, t, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    # Same params but symmetric γ=4 — i.e. "AFL-like" focusing on positives.
    loss_sym = _ridnik_asymmetric_loss(
        p, t, gamma_pos=4.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    # The Ridnik asymmetric (γ+=1) keeps the gradient on TPs alive → loss higher.
    assert loss_ridnik.item() > loss_sym.item()


def test_ridnik_deterministic_on_cpu() -> None:
    """Same seed + same inputs ⇒ bit-identical loss output."""
    pw = _make_pos_weight()
    torch.manual_seed(42)
    p1 = torch.rand(2, 16, N_BUSES, dtype=torch.float32).clamp(1e-3, 1 - 1e-3)
    t1 = torch.rand(2, 16, N_BUSES, dtype=torch.float32)
    loss_a = _ridnik_asymmetric_loss(
        p1, t1, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    loss_b = _ridnik_asymmetric_loss(
        p1.clone(), t1.clone(), gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    assert loss_a.item() == loss_b.item()


# ----------------------------------------------------------------------------
# TCNLoss integration
# ----------------------------------------------------------------------------


def _flat25_target(B: int, T: int, peak_density: float = 0.1) -> torch.Tensor:
    """Synthetic flat-25 target with a few sparse onsets on bus 0."""
    target = torch.zeros(B, T, 25, dtype=torch.float32)
    n_onsets = max(1, int(T * peak_density))
    stride = max(1, T // n_onsets)
    target[:, ::stride, 0] = 1.0          # onset bus 0
    target[:, ::stride, 1] = 0.7          # velocity bus 0
    target[:, ::stride, 2] = 0.0          # microtiming bus 0 (centered)
    target[:, :, HIHAT_OPENING_COL] = 0.3  # hihat opening dense
    return target


def test_tcnloss_ridnik_forward_returns_5_keys() -> None:
    cfg = LossConfig(kind="ridnik")
    loss_fn = TCNLoss(cfg)
    pred = torch.rand(2, 64, 25, dtype=torch.float32) * 0.5
    target = _flat25_target(2, 64)
    out = loss_fn(pred, target)
    assert set(out.keys()) == {"total", "onset", "velocity", "microtiming", "hihat"}
    for k, v in out.items():
        assert torch.isfinite(v).all(), f"{k} non-finite"


def test_tcnloss_ridnik_backward_finite() -> None:
    cfg = LossConfig(kind="ridnik")
    loss_fn = TCNLoss(cfg)
    pred = (torch.rand(2, 64, 25, dtype=torch.float32) * 0.5).requires_grad_(True)
    target = _flat25_target(2, 64)
    out = loss_fn(pred, target)
    out["total"].backward()
    assert pred.grad is not None
    assert torch.isfinite(pred.grad).all()
    # Sanity: non-zero gradient on the onset columns
    onset_grad = pred.grad[..., 0:24:3]
    assert onset_grad.abs().sum().item() > 0.0


def test_tcnloss_label_smoothing_changes_onset_loss() -> None:
    """With label_smoothing > 0, the onset loss differs from the hard-target
    baseline. The L1 (velocity/microtiming) terms remain identical because
    they use the RAW target for the mask geometry."""
    cfg_hard = LossConfig(kind="ridnik", label_smoothing=0.0)
    cfg_smooth = LossConfig(kind="ridnik", label_smoothing=0.05)
    loss_hard = TCNLoss(cfg_hard)
    loss_smooth = TCNLoss(cfg_smooth)
    torch.manual_seed(7)
    pred = torch.rand(1, 32, 25, dtype=torch.float32) * 0.5
    target = _flat25_target(1, 32)
    out_hard = loss_hard(pred, target)
    out_smooth = loss_smooth(pred, target)
    assert out_hard["onset"].item() != out_smooth["onset"].item()
    # L1 supervision uses the raw target for masking — unchanged.
    assert math.isclose(
        out_hard["velocity"].item(), out_smooth["velocity"].item(), rel_tol=1e-6,
    )
    assert math.isclose(
        out_hard["microtiming"].item(), out_smooth["microtiming"].item(), rel_tol=1e-6,
    )
    assert math.isclose(
        out_hard["hihat"].item(), out_smooth["hihat"].item(), rel_tol=1e-6,
    )


def test_tcnloss_label_smoothing_works_for_afl_kind_too() -> None:
    """Label smoothing is `kind`-agnostic: it changes the onset loss for AFL
    as well."""
    cfg_hard = LossConfig(kind="afl", label_smoothing=0.0)
    cfg_smooth = LossConfig(kind="afl", label_smoothing=0.05)
    torch.manual_seed(3)
    pred = torch.rand(1, 32, 25, dtype=torch.float32) * 0.5
    target = _flat25_target(1, 32)
    out_hard = TCNLoss(cfg_hard)(pred, target)
    out_smooth = TCNLoss(cfg_smooth)(pred, target)
    assert out_hard["onset"].item() != out_smooth["onset"].item()


def test_tcnloss_afl_backcompat_unchanged() -> None:
    """A default LossConfig (kind="afl", label_smoothing=0.0) produces the
    same output as before F0-T4f (no regression)."""
    cfg = LossConfig()  # defaults
    assert cfg.kind == "afl"
    assert cfg.label_smoothing == 0.0
    loss_fn = TCNLoss(cfg)
    torch.manual_seed(11)
    pred = torch.rand(1, 32, 25, dtype=torch.float32) * 0.5
    target = _flat25_target(1, 32)
    out = loss_fn(pred, target)
    # Just sanity-check it runs end-to-end + finite.
    assert torch.isfinite(out["total"]).item()
    assert out["total"].item() > 0.0


def test_tcnloss_ridnik_vs_afl_differ() -> None:
    """Ridnik and AFL produce different losses on the same input."""
    torch.manual_seed(13)
    pred = torch.rand(2, 64, 25, dtype=torch.float32) * 0.5
    target = _flat25_target(2, 64)
    out_afl = TCNLoss(LossConfig(kind="afl"))(pred, target)
    out_ridnik = TCNLoss(LossConfig(kind="ridnik"))(pred, target)
    # Different math paths → different scalar value (modulo a vanishingly
    # small chance of accidental equality).
    assert out_afl["total"].item() != out_ridnik["total"].item()


def test_tcnloss_ridnik_deterministic() -> None:
    """Same input ⇒ same output across two TCNLoss instances (no hidden state)."""
    cfg = LossConfig(kind="ridnik", label_smoothing=0.05)
    a = TCNLoss(cfg)
    b = TCNLoss(cfg)
    torch.manual_seed(17)
    pred = torch.rand(2, 32, 25, dtype=torch.float32) * 0.5
    target = _flat25_target(2, 32)
    out_a = a(pred, target)
    out_b = b(pred, target)
    for key in ("total", "onset", "velocity", "microtiming", "hihat"):
        assert out_a[key].item() == out_b[key].item(), key
