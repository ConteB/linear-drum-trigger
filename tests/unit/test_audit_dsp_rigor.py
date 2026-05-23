"""Layer-1 oracles for :mod:`tools.audit_dsp_rigor` (F0-T6 Layer-S gate).

The gate must:

1. Load and validate the LOCKED rules YAML, fail-loud on malformed input.
2. Recognise both scope mechanisms — explicit ``// @audio_thread`` markers
   and JUCE-callback heuristic.
3. Ignore lines OUTSIDE any active scope (no false positives).
4. Catch every canonical Zero-Allocation violation INSIDE a scope.
5. Produce a deterministic JSON report (byte-identical for identical input).
6. Return exit code 1 if any ``error``-severity finding is present, else 0.

Spec: ``tools/audit_dsp_rigor.yaml`` (LOCKED rules,
ENGINEERING_STANDARDS §2 + §3.2, TESTING_DOCTRINE §2 Layer-S).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "audit_dsp_rigor.py"
CONFIG = REPO_ROOT / "tools" / "audit_dsp_rigor.yaml"
FIXTURE_GOOD = REPO_ROOT / "tests" / "fixtures" / "dsp_rigor" / "good.cpp"
FIXTURE_BAD = REPO_ROOT / "tests" / "fixtures" / "dsp_rigor" / "bad.cpp"

# Make the script importable as a module (no entry-point installed in setup).
sys.path.insert(0, str(REPO_ROOT / "tools"))
import audit_dsp_rigor as adr  # noqa: E402

# --- config loader ----------------------------------------------------------


def test_load_config_locked_file() -> None:
    """The LOCKED YAML parses; every rule has a compiled regex + valid severity."""
    rules, scope = adr.load_config(CONFIG)
    assert rules, "LOCKED config must declare at least one rule"
    assert scope.begin_markers
    assert scope.end_markers
    assert scope.juce_callbacks
    ids = {r.id for r in rules}
    # Canonical rules anchor the LOCKED schema — if any disappears, a
    # Decision Lock CEO is required (do not silently drop).
    for required in (
        "heap_alloc_new",
        "heap_alloc_delete",
        "vector_push_back",
        "iostream_cout",
        "stdio_printf",
        "blocking_mutex_lock",
        "throw_statement",
        "smart_pointer_construction",
        "string_assign_op",
    ):
        assert required in ids, f"missing LOCKED rule {required!r}"


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(adr.AuditError, match="not found"):
        adr.load_config(tmp_path / "nope.yaml")


def test_load_config_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{not: valid: yaml", encoding="utf-8")
    with pytest.raises(adr.AuditError, match="parse error"):
        adr.load_config(bad)


def test_load_config_missing_scope(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("rules: []\n", encoding="utf-8")
    with pytest.raises(adr.AuditError, match="scope"):
        adr.load_config(bad)


def test_load_config_duplicate_rule_id(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
scope:
  begin_markers: ['// @audio_thread']
  end_markers: ['// @audio_thread_end']
  juce_audio_callbacks: ['processBlock']
rules:
  - {id: dup, pattern: 'new', severity: error, description: ''}
  - {id: dup, pattern: 'delete', severity: error, description: ''}
""",
        encoding="utf-8",
    )
    with pytest.raises(adr.AuditError, match="duplicate"):
        adr.load_config(bad)


def test_load_config_invalid_regex(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
scope:
  begin_markers: ['// @audio_thread']
  end_markers: ['// @audio_thread_end']
  juce_audio_callbacks: []
rules:
  - {id: r, pattern: '(unclosed', severity: error, description: ''}
""",
        encoding="utf-8",
    )
    with pytest.raises(adr.AuditError, match="regex"):
        adr.load_config(bad)


def test_load_config_invalid_severity(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
scope:
  begin_markers: ['// @audio_thread']
  end_markers: ['// @audio_thread_end']
  juce_audio_callbacks: []
rules:
  - {id: r, pattern: 'new', severity: oops, description: ''}
""",
        encoding="utf-8",
    )
    with pytest.raises(adr.AuditError, match="severity"):
        adr.load_config(bad)


# --- audit on fixtures ------------------------------------------------------


def test_good_fixture_has_no_findings() -> None:
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_file(FIXTURE_GOOD, rules, scope)
    assert findings == [], (
        f"good.cpp must be clean but produced: "
        f"{[(f.rule_id, f.line) for f in findings]}"
    )


def test_bad_fixture_catches_all_canonical_violations() -> None:
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_file(FIXTURE_BAD, rules, scope)
    assert findings, "bad.cpp must produce at least one finding"
    rule_hits = {f.rule_id for f in findings}
    # Every canonical violation in the LOCKED fixture must be caught.
    canonical = {
        "heap_alloc_new",
        "heap_alloc_delete",
        "vector_push_back",
        "vector_emplace_back",
        "iostream_cout",
        "blocking_mutex_lock",
        "throw_statement",
        "string_assign_op",
        "smart_pointer_construction",
        "stdio_printf",
        "juce_logger",
    }
    missing = canonical - rule_hits
    assert not missing, f"missed canonical violations: {sorted(missing)}"


def test_bad_fixture_does_not_flag_out_of_scope_lines() -> None:
    """The bad.cpp ends with a `new`/`delete` pair OUTSIDE any scope — must
    NOT appear in the findings (setup-time alloc is legitimate)."""
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_file(FIXTURE_BAD, rules, scope)
    out_of_scope_lines = {
        line for line in (61, 62)  # the trailing `new float[10]` + delete[]
    }
    flagged_lines = {f.line for f in findings}
    assert not (out_of_scope_lines & flagged_lines), (
        f"out-of-scope lines should be ignored, found: "
        f"{out_of_scope_lines & flagged_lines}"
    )


def test_findings_are_sorted_deterministically() -> None:
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_file(FIXTURE_BAD, rules, scope)
    sorted_keys = [(f.file, f.line, f.column, f.rule_id) for f in findings]
    assert sorted_keys == sorted(sorted_keys), \
        "findings must be sorted by (file, line, column, rule_id)"


# --- scope detection edge cases ---------------------------------------------


def test_explicit_marker_scope_is_respected(tmp_path: Path) -> None:
    src = tmp_path / "x.cpp"
    src.write_text(
        """
void foo() {
    new int[10];          // line 3 — OUT of scope, must be ignored
    // @audio_thread
    new float[20];        // line 5 — IN scope, must be flagged
    // @audio_thread_end
    new double[30];       // line 7 — OUT of scope, must be ignored
}
""",
        encoding="utf-8",
    )
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_file(src, rules, scope)
    assert len(findings) == 1
    assert findings[0].line == 5
    assert findings[0].rule_id == "heap_alloc_new"


def test_juce_callback_heuristic_scopes_function_body(tmp_path: Path) -> None:
    src = tmp_path / "x.cpp"
    src.write_text(
        """
class P {
public:
    void unrelated() {
        new int[10];              // OUT — not in any callback
    }
    void processBlock(int n) {
        new float[n];             // IN — JUCE callback heuristic
    }
};
""",
        encoding="utf-8",
    )
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_file(src, rules, scope)
    assert len(findings) == 1
    assert "processBlock" in src.read_text().splitlines()[findings[0].line - 2]


def test_string_literals_and_comments_dont_match(tmp_path: Path) -> None:
    """The word ``new`` inside a string or comment must NOT be flagged."""
    src = tmp_path / "x.cpp"
    src.write_text(
        '''
void processBlock(int n) {
    const char* msg = "this string mentions new but is literal";
    // The word new appears in this comment but must be ignored.
    /* Block comment with new also ignored. */
    int x = 0;
    (void)x;
}
''',
        encoding="utf-8",
    )
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_file(src, rules, scope)
    assert findings == [], f"false positives from strings/comments: {findings}"


def test_unmatched_begin_marker_extends_to_eof(tmp_path: Path) -> None:
    src = tmp_path / "x.cpp"
    src.write_text(
        """
void foo() {
    // @audio_thread
    new int[10];
    // no end marker — region open to EOF
}
""",
        encoding="utf-8",
    )
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_file(src, rules, scope)
    assert any(f.rule_id == "heap_alloc_new" for f in findings)


# --- CLI / report -----------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_exit_0_on_clean_file() -> None:
    result = _run_cli(str(FIXTURE_GOOD))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CLEAR" in result.stdout


def test_cli_exit_1_on_violations() -> None:
    result = _run_cli(str(FIXTURE_BAD))
    assert result.returncode == 1
    assert "error" in result.stdout.lower()


def test_cli_writes_json_report(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    result = _run_cli(str(FIXTURE_BAD), "--report", str(out), "--quiet")
    assert result.returncode == 1
    assert out.exists()
    doc = json.loads(out.read_text())
    assert doc["schema_version"] == 1
    assert doc["n_findings"] >= 11  # 11 canonical violations in bad.cpp
    assert doc["n_error"] >= 11
    rule_ids = {f["rule_id"] for f in doc["findings"]}
    assert "heap_alloc_new" in rule_ids


def test_cli_quiet_mode_suppresses_clean_output(tmp_path: Path) -> None:
    result = _run_cli(str(FIXTURE_GOOD), "--quiet")
    assert result.returncode == 0
    assert "ALL CLEAR" not in result.stdout


def test_json_report_is_byte_deterministic(tmp_path: Path) -> None:
    out1 = tmp_path / "report1.json"
    out2 = tmp_path / "report2.json"
    _run_cli(str(FIXTURE_BAD), "--report", str(out1), "--quiet")
    _run_cli(str(FIXTURE_BAD), "--report", str(out2), "--quiet")
    assert out1.read_bytes() == out2.read_bytes()


# --- directory scanning -----------------------------------------------------


def test_directory_scan_walks_recursively(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "x.cpp").write_text(
        "void processBlock() { new int[1]; }\n", encoding="utf-8"
    )
    (tmp_path / "y.cpp").write_text(
        "void processBlock() { new float[2]; }\n", encoding="utf-8"
    )
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_paths([tmp_path], rules, scope)
    assert len(findings) == 2
    files = sorted({Path(f.file).name for f in findings})
    assert files == ["x.cpp", "y.cpp"]


def test_directory_scan_skips_non_cpp_files(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("def f(): pass\n", encoding="utf-8")
    (tmp_path / "x.txt").write_text("processBlock new\n", encoding="utf-8")
    rules, scope = adr.load_config(CONFIG)
    findings = adr.audit_paths([tmp_path], rules, scope)
    assert findings == []
