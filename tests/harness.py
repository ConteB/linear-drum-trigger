"""Shared scaffolding for the F0 pipeline test harness (F0-T9b).

Importable from any test module (``tests`` is on ``pythonpath`` — see
``pyproject.toml``). This module holds no fixtures (those live in
``conftest.py``); it holds the contract-oracle marker helper.
"""
from __future__ import annotations

import pytest

#: F0 sub-tasks that own each not-yet-implemented module (TESTING_DOCTRINE §6).
#: Drained: F0-T2b (recipe parser / Sfizz), F0-T2c (DrumGizmo), F0-T2d (writer +
#: DNA-Trace), F0-T4b (mic standardisation, data-loader stage) — the
#: self-dismantling scaffold worked as designed.
OWNERS: dict[str, str] = {}


def awaiting(task: str) -> pytest.MarkDecorator:
    """Mark a contract test-oracle that is GREEN-as-xfail until ``task`` lands.

    The oracle is written test-first against the F0-T2a contract
    (TESTING_DOCTRINE §1.3, §6.2). While the implementation is a skeleton stub
    it raises :class:`NotImplementedError`; this marker absorbs *exactly* that
    exception, and nothing else:

    * a bug in the oracle itself raises some *other* exception — that surfaces
      as a real ``FAILED``; the marker never hides it;
    * once ``task`` implements the module, the oracle either passes — reported
      as a strict-xfail ``XPASS`` → the run goes RED, forcing this marker to be
      removed — or fails for a genuine reason. Either way the scaffold cannot
      rot into a silent false-green.

    Args:
        task: The owning F0 sub-task id (a key of :data:`OWNERS`).

    Returns:
        A ``pytest.mark.xfail`` decorator scoped to ``NotImplementedError``.
    """
    return pytest.mark.xfail(
        reason=f"contract oracle — awaiting {task} ({OWNERS.get(task, '?')})",
        strict=True,
        raises=NotImplementedError,
    )
