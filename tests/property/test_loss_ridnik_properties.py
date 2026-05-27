"""Hypothesis property tests for the F0-T4f Ridnik AsymmetricLoss.

Three central claims pinned with random inputs:

1. **Non-negativity** — for any p ∈ (0, 1) and t ∈ [0, 1], the loss is ≥ 0
   (it's a sum of NLL terms with non-negative weights).
2. **Bus permutation invariance** — permuting the bus dimension of both
   `pred` and `target` (and `pos_weight`) yields the same loss.
3. **Monotonia w.r.t. pos_weight** — scaling pos_weight by k ≥ 1 cannot
   decrease the loss when there is at least one positive target frame.
"""
from __future__ import annotations

import numpy as np
import torch
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from neural.loss import N_BUSES, _ridnik_asymmetric_loss

_SETTINGS = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)


def _from_seed(seed: int, B: int = 1, T: int = 16) -> tuple[torch.Tensor, torch.Tensor]:
    """Reproducible (pred, target) tensors from a single integer seed."""
    rng = np.random.default_rng(seed)
    p = torch.from_numpy(
        rng.uniform(1e-3, 1.0 - 1e-3, size=(B, T, N_BUSES)).astype(np.float32),
    )
    t = torch.from_numpy(
        rng.uniform(0.0, 1.0, size=(B, T, N_BUSES)).astype(np.float32),
    )
    return p, t


@_SETTINGS
@given(seed=st.integers(min_value=0, max_value=1_000_000))
def test_ridnik_non_negative(seed: int) -> None:
    p, t = _from_seed(seed)
    pw = torch.ones(N_BUSES, dtype=torch.float32)
    loss = _ridnik_asymmetric_loss(
        p, t, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    assert loss.item() >= 0.0


@_SETTINGS
@given(
    seed=st.integers(min_value=0, max_value=1_000_000),
    perm_seed=st.integers(min_value=0, max_value=10_000),
)
def test_ridnik_bus_permutation_invariance(seed: int, perm_seed: int) -> None:
    """Permuting the bus dim of (pred, target, pos_weight) coherently must
    leave the loss unchanged: it is a sum (.mean()) over all elements with
    per-bus weights, which is permutation-invariant when all 3 are permuted
    together."""
    p, t = _from_seed(seed)
    pw = torch.linspace(1.0, 8.0, N_BUSES, dtype=torch.float32)
    perm_rng = np.random.default_rng(perm_seed)
    perm = perm_rng.permutation(N_BUSES)
    perm_t = torch.as_tensor(perm, dtype=torch.long)
    p_perm = p.index_select(-1, perm_t)
    t_perm = t.index_select(-1, perm_t)
    pw_perm = pw.index_select(0, perm_t)
    loss_orig = _ridnik_asymmetric_loss(
        p, t, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    loss_perm = _ridnik_asymmetric_loss(
        p_perm, t_perm, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw_perm,
    )
    assert torch.isclose(loss_orig, loss_perm, rtol=1e-5, atol=1e-7).item()


@_SETTINGS
@given(
    seed=st.integers(min_value=0, max_value=1_000_000),
    scale=st.floats(min_value=1.0, max_value=10.0),
)
def test_ridnik_pos_weight_monotonia(seed: int, scale: float) -> None:
    """Multiplying pos_weight by k >= 1 cannot decrease the loss if there is
    at least one positive target (loss_pos is multiplied by pos_weight, which
    is then summed into the total — bigger weight, bigger contribution)."""
    p, t = _from_seed(seed)
    # ensure at least one positive frame
    t[0, 0, 0] = 1.0
    pw_base = torch.ones(N_BUSES, dtype=torch.float32)
    pw_scaled = pw_base * scale
    loss_base = _ridnik_asymmetric_loss(
        p, t, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw_base,
    )
    loss_scaled = _ridnik_asymmetric_loss(
        p, t, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw_scaled,
    )
    # Strict monotonia (scale > 1 means strictly more positive penalty);
    # at scale == 1 the loss is identical (rtol).
    if scale > 1.0 + 1e-6:
        assert loss_scaled.item() >= loss_base.item() - 1e-7
    else:
        assert torch.isclose(loss_base, loss_scaled, rtol=1e-5).item()


@_SETTINGS
@given(seed=st.integers(min_value=0, max_value=1_000_000))
def test_ridnik_byte_determinism_across_dtype_preserving_runs(seed: int) -> None:
    """Same seed + same tensors ⇒ bit-identical loss output on CPU.

    This pins the absence of nondeterministic primitives in the Ridnik path
    (no Dropout, no atomics, no device-side scatter)."""
    p, t = _from_seed(seed)
    pw = torch.ones(N_BUSES, dtype=torch.float32)
    loss_a = _ridnik_asymmetric_loss(
        p, t, gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    loss_b = _ridnik_asymmetric_loss(
        p.clone(), t.clone(), gamma_pos=1.0, gamma_neg=4.0,
        prob_clip_negative=0.05, fp_to_fn_ratio=30.0, pos_weight=pw,
    )
    assert loss_a.item() == loss_b.item()
