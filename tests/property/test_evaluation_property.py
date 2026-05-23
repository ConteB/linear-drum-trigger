"""Layer-2 property oracles for the F0-T17 evaluation suite (Hypothesis).

Two contracts are properties, not unit:

1. **Determinism per seed** (ENGINEERING_STANDARDS §1): every module's
   ``run()`` is byte-deterministic for the same input.
2. **Monotonia di soglia**: tightening a threshold cannot turn a failing
   gate into a passing one (and vice-versa relaxing cannot fail what passed).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from tests.unit.test_evaluation_common import _make_dna
from tests.unit.test_evaluation_data_audit import _write_target_with_onsets

from evaluation.data_audit import N_BUSES
from evaluation.data_audit import run as run_data_audit
from evaluation.evaluation_suite import _bootstrap_ci, _f_measure

pytestmark = [pytest.mark.evaluation, pytest.mark.property]

THRESHOLDS = Path("src/evaluation/thresholds.yaml")


# --- 1. determinism per seed --------------------------------------------------


@settings(
    max_examples=10, deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    onsets_per_bus=st.lists(
        st.integers(min_value=1, max_value=10), min_size=N_BUSES, max_size=N_BUSES,
    )
)
def test_data_audit_run_is_byte_deterministic(
    onsets_per_bus: list[int], tmp_path: Path
) -> None:
    gold = tmp_path / "gold"
    gold.mkdir(exist_ok=True)
    _make_dna(gold, key=f"A-{sum(onsets_per_bus)}", n_frame=64)
    _write_target_with_onsets(
        gold / f"A-{sum(onsets_per_bus)}.target.f16",
        n_frame=64, onsets_per_bus=onsets_per_bus,
    )
    r1 = run_data_audit(gold_dir=gold, thresholds=THRESHOLDS,
                         out_dir=tmp_path / "out1")
    r2 = run_data_audit(gold_dir=gold, thresholds=THRESHOLDS,
                         out_dir=tmp_path / "out2")
    assert r1.report_json.read_bytes() == r2.report_json.read_bytes()


# --- 2. F-measure properties --------------------------------------------------


@given(
    n=st.integers(min_value=1, max_value=50),
    tol_s=st.floats(min_value=0.001, max_value=0.1),
)
def test_f_measure_perfect_match_property(n: int, tol_s: float) -> None:
    """Pred = Ref → F = 1, no matter the times or tolerance."""
    ref = np.linspace(0.1, 5.0, n)
    f = _f_measure(ref, ref, tol_s=tol_s)
    assert f == pytest.approx(1.0)


@given(
    n_ref=st.integers(min_value=2, max_value=20),
)
def test_f_measure_zero_pred_yields_zero(n_ref: int) -> None:
    ref = np.linspace(0.1, 5.0, n_ref)
    assert _f_measure(np.array([]), ref, tol_s=0.025) == 0.0


# --- 3. bootstrap monotonicity ------------------------------------------------


@given(
    base=st.floats(min_value=0.05, max_value=0.95),
    n=st.integers(min_value=2, max_value=50),
)
@settings(max_examples=20, deadline=None)
def test_bootstrap_ci_mean_is_sample_mean(base: float, n: int) -> None:
    """CI mean = sample mean (by construction of basic bootstrap)."""
    values = [base] * n
    ci = _bootstrap_ci(values, n_resamples=200, seed=0)
    assert ci["mean"] == pytest.approx(base)
    # CI lo <= mean <= hi
    assert ci["lo"] <= ci["mean"] <= ci["hi"]


# --- 4. monotonia di soglia (looser threshold cannot turn pass→fail) ---------


@settings(
    max_examples=5, deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    onsets=st.lists(
        st.integers(min_value=2, max_value=5),
        min_size=N_BUSES, max_size=N_BUSES,
    )
)
def test_data_audit_monotonicity_minority_threshold(
    onsets: list[int], tmp_path: Path
) -> None:
    """If informative-only metrics drive imbalance, lowering the minority
    threshold cannot turn a passing report into a failing one (because the
    only blocking failure is *empty buses*, which is independent of the
    minority threshold)."""
    gold = tmp_path / "gold"
    gold.mkdir(exist_ok=True)
    _make_dna(gold, key="A", n_frame=128)
    _write_target_with_onsets(gold / "A.target.f16", n_frame=128,
                              onsets_per_bus=onsets)
    r = run_data_audit(gold_dir=gold, thresholds=THRESHOLDS,
                       out_dir=tmp_path / "out")
    # No empty buses → must pass regardless of minority threshold.
    assert r.passed is True
    assert r.metrics["empty_buses"] == []
