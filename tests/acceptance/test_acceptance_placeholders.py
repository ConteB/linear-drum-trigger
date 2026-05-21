"""§6.3 — per-subtask acceptance tests.

These exercise the render engines end-to-end and therefore need external
binaries (Sfizz, DrumGizmo) and the orchestrator — none of which exist yet.
They are materialised here as SKIPPED scaffolds so the §6.3 acceptance plan is
tracked in the harness and filled in by the owning sub-task.

When a sub-task lands it replaces the corresponding ``skip`` with a real body.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.acceptance


@pytest.mark.skip(reason="F0-T2b — needs the Sfizz binary integrated")
def test_sfizz_render_is_deterministic_per_seed() -> None:
    """Same recipe + same seed -> bit-identical WAV (TESTING_DOCTRINE §6.3)."""


@pytest.mark.skip(reason="F0-T2b — needs the Sfizz binary integrated")
def test_sfizz_render_sample_rate_is_44100() -> None:
    """Rendered WAV is 44.1 kHz, amplitude within [-1, 1] (§6.3)."""


@pytest.mark.skip(reason="F0-T2c — needs a DrumGizmo multi-mic kit")
def test_drumgizmo_channel_count_matches_mic_config() -> None:
    """n_mic of the render matches the recipe's mic_config (§6.3)."""


@pytest.mark.skip(reason="F0-T2c — needs a DrumGizmo multi-mic kit")
def test_drumgizmo_bleed_is_present_falsifiably() -> None:
    """Inter-channel cross-correlation > 0 — bleed proven, not eyeballed (§6.3)."""


@pytest.mark.skip(reason="F0-T2e — needs the full recipe->writer orchestrator")
def test_minibatch_end_to_end_sample_count() -> None:
    """Orchestrating ~10-20 scenarios yields N Gold samples, no errors (§6.3)."""
