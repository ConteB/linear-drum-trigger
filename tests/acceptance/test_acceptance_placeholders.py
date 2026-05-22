"""§6.3 — per-subtask acceptance tests (pending sub-tasks).

These exercise the orchestrator end-to-end, which does not exist yet. It is
materialised here as a SKIPPED scaffold so the §6.3 acceptance plan stays
tracked in the harness and is filled in by the owning sub-task.

When a sub-task lands it replaces its ``skip`` with a real body:

* F0-T2b (Sfizz) — done: §6.3 oracles in ``test_sfizz_render.py``.
* F0-T2c (DrumGizmo) — done: §6.3 oracles in ``test_drumgizmo_render.py``.
* F0-T2e (orchestrator) — pending, scaffold below.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.acceptance


@pytest.mark.skip(reason="F0-T2e — needs the full recipe->writer orchestrator")
def test_minibatch_end_to_end_sample_count() -> None:
    """Orchestrating ~10-20 scenarios yields N Gold samples, no errors (§6.3)."""
