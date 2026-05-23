"""Statistical validation suite (F0-T17) — pre-F2-T3 gate + post-F2-T3 Gate L4.

Four modules, each callable both as a library function and a CLI:

* :mod:`evaluation.data_audit` — distribution of the Gold tensor (pre-F2-T3,
  informative).
* :mod:`evaluation.split_consistency` — KS / chi-square train↔val + MIDI
  leakage check (**bloccante** F2-T3).
* :mod:`evaluation.anti_leak_audit` — verifica numerica dei Decision Lock A+C
  anti-shortcut engine (**bloccante** F2-T3).
* :mod:`evaluation.evaluation_suite` — Gate L4 dossier su E-GMD (post-F2-T3).

All modules share :class:`~evaluation.common.ReportResult`, the locked
:func:`~evaluation.common.load_thresholds` reader, and the deterministic
Gold-directory scanner. Outputs are dual — JSON (machine-verifiable gate) and
PNG (Laboratory-Precision dossier).

Spec: ``docs/methodology/F0-T17_STATISTICAL_TEST_PLAN.md`` (LOCKED 2026-05-23).
"""

from evaluation.common import (
    GoldSampleMeta,
    ReportResult,
    Thresholds,
    load_thresholds,
    scan_gold_dir,
)

__all__ = [
    "GoldSampleMeta",
    "ReportResult",
    "Thresholds",
    "load_thresholds",
    "scan_gold_dir",
]
