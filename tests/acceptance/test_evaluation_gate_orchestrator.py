"""Acceptance — the F0-T17 gate orchestrator script runs end-to-end."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.evaluation, pytest.mark.acceptance]

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = REPO_ROOT / "tools" / "run_evaluation_gate.sh"
MINI_BATCH = REPO_ROOT / "data" / "gold" / "mini_batch"

if not MINI_BATCH.is_dir() or not any(MINI_BATCH.glob("*.dna.json")):
    pytest.skip(
        "mini-batch absent — run tools/run_mini_batch.py first",
        allow_module_level=True,
    )


def test_orchestrator_runs_three_modules_on_mini_batch(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    env = os.environ.copy()
    env["PYTHON"] = str(REPO_ROOT / ".venv" / "bin" / "python")
    result = subprocess.run(
        [str(GATE_SCRIPT), str(MINI_BATCH), str(out)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"orchestrator failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # All three reports landed.
    for module in ("data_audit", "split_consistency", "anti_leak_audit"):
        assert (out / f"{module}.report.json").exists(), \
            f"{module} report.json missing"
        assert (out / f"{module}.report.png").exists(), \
            f"{module} report.png missing"
    # And the trailing log line confirms the gate is green.
    assert "ALL GREEN" in result.stdout
