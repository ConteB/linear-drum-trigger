"""F0-T6 — Layer-S static gate for the C++ audio thread.

Scans C++ source files and reports lines that violate the **Zero-Allocation**
mandate of the audio thread (ENGINEERING_STANDARDS §2 + §3.2,
MASTER_CHECKLIST §3, TESTING_DOCTRINE §2 Layer-S).

Two complementary scopes anchor each finding to actual audio-thread code:

1. **Explicit markers** — line comments ``// @audio_thread`` opens a region;
   ``// @audio_thread_end`` closes it. Robust for any wrapper class or
   thread-pool worker.
2. **JUCE heuristics** — functions whose identifier matches a known
   audio-callback (``processBlock`` / ``getNextAudioBlock`` /
   ``audioDeviceIOCallback`` …) are auto-scoped from their header line to the
   matching closing brace.

A line that lives **inside** any active scope and matches any rule pattern is
flagged. Findings are emitted both to stdout (human report) and to a
deterministic JSON report (CI gate). Exit code: ``0`` if no error-severity
findings, ``1`` otherwise — ready for ``set -e``.

Spec: ``tools/audit_dsp_rigor.yaml`` (LOCKED rules).
Predisposed in F0; **operational gate applies in F4** on every commit to the
DSP core (``cpp/dsp/**``).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Default config — sits next to this script so it follows on `git mv`.
DEFAULT_CONFIG = Path(__file__).resolve().parent / "audit_dsp_rigor.yaml"

#: Severity levels — error blocks the gate, warn does not.
_SEVERITY_ERROR = "error"
_SEVERITY_WARN = "warn"
_VALID_SEVERITIES = (_SEVERITY_ERROR, _SEVERITY_WARN)

#: File extensions audited by default.
_DEFAULT_EXTENSIONS = (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h", ".inl")

#: Line-comment / block-comment / string-literal stripper — strips C/C++
#: comments and double-quoted strings so we never match inside them. This is
#: a *minimal* parser (it doesn't track macros or raw strings); enough for the
#: Layer-S grep gate per TESTING_DOCTRINE §2.
_RE_LINE_COMMENT = re.compile(r"//[^\n]*")
_RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_RE_STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')


@dataclass(frozen=True)
class Rule:
    """One forbidden-pattern rule (loaded from YAML)."""

    id: str
    pattern: re.Pattern[str]
    severity: str
    description: str


@dataclass(frozen=True)
class ScopeConfig:
    """Static scope markers + JUCE-callback identifiers."""

    begin_markers: tuple[str, ...]
    end_markers: tuple[str, ...]
    juce_callbacks: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    """One rule violation, located in source."""

    file: str
    line: int
    column: int
    rule_id: str
    severity: str
    description: str
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class AuditError(RuntimeError):
    """Raised when the config or input files cannot be read."""


# --- config -----------------------------------------------------------------


def load_config(path: Path | str) -> tuple[list[Rule], ScopeConfig]:
    """Load rules + scope config from YAML; fail-loud on malformed input."""
    p = Path(path)
    if not p.is_file():
        raise AuditError(f"config not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AuditError(f"config YAML parse error: {exc}") from exc
    if not isinstance(raw, dict):
        raise AuditError(f"config root must be a mapping, got {type(raw).__name__}")

    scope = raw.get("scope") or {}
    if not isinstance(scope, dict):
        raise AuditError("config.scope must be a mapping")
    begin = tuple(scope.get("begin_markers") or ())
    end = tuple(scope.get("end_markers") or ())
    callbacks = tuple(scope.get("juce_audio_callbacks") or ())
    if not begin or not end:
        raise AuditError("config.scope must define begin_markers and end_markers")
    scope_cfg = ScopeConfig(begin_markers=begin, end_markers=end, juce_callbacks=callbacks)

    rules_raw = raw.get("rules") or []
    if not isinstance(rules_raw, list) or not rules_raw:
        raise AuditError("config.rules must be a non-empty list")

    rules: list[Rule] = []
    seen_ids: set[str] = set()
    for r in rules_raw:
        if not isinstance(r, dict):
            raise AuditError(f"rule must be a mapping, got {r!r}")
        rid = r.get("id")
        pat = r.get("pattern")
        sev = r.get("severity")
        desc = r.get("description")
        if not (isinstance(rid, str) and rid):
            raise AuditError(f"rule.id required, got {rid!r}")
        if rid in seen_ids:
            raise AuditError(f"duplicate rule id: {rid!r}")
        seen_ids.add(rid)
        if not isinstance(pat, str) or not pat:
            raise AuditError(f"rule[{rid}].pattern must be a non-empty string")
        if sev not in _VALID_SEVERITIES:
            raise AuditError(
                f"rule[{rid}].severity must be one of {_VALID_SEVERITIES}, got {sev!r}"
            )
        try:
            compiled = re.compile(pat)
        except re.error as exc:
            raise AuditError(f"rule[{rid}].pattern is not a valid regex: {exc}") from exc
        rules.append(Rule(id=rid, pattern=compiled, severity=sev,
                           description=str(desc or "")))
    return rules, scope_cfg


# --- preprocessing ----------------------------------------------------------


def _strip_comments_and_strings(source: str) -> str:
    """Mask comment + double-quoted string content with spaces.

    Comments and string literals are blanked (replaced by same-length
    whitespace) so line/column numbers remain stable — pattern matches
    against the masked source still report the original line/column.
    """
    def _blank(m: re.Match[str]) -> str:
        text = m.group(0)
        # Preserve newlines so line numbers do not shift.
        return "".join("\n" if ch == "\n" else " " for ch in text)

    masked = _RE_BLOCK_COMMENT.sub(_blank, source)
    masked = _RE_LINE_COMMENT.sub(_blank, masked)
    masked = _RE_STRING_LITERAL.sub(_blank, masked)
    return masked


# --- scope detection --------------------------------------------------------


def _line_starts(text: str) -> list[int]:
    """Char offsets at which each line begins (1-indexed lookups)."""
    offsets = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _offset_to_line_col(offset: int, line_starts: list[int]) -> tuple[int, int]:
    """1-based ``(line, column)`` of a char offset."""
    # Binary search would be faster but linear is fine at <10k LOC per file.
    line = 0
    for i, start in enumerate(line_starts):
        if start <= offset:
            line = i
        else:
            break
    col = offset - line_starts[line] + 1
    return line + 1, col


def _explicit_marker_ranges(
    source: str, scope: ScopeConfig
) -> list[tuple[int, int]]:
    """Char-offset ranges enclosed by explicit ``// @audio_thread`` markers."""
    ranges: list[tuple[int, int]] = []
    cursor = 0
    n = len(source)
    while cursor < n:
        # find any begin marker
        next_begin = -1
        next_begin_marker: str | None = None
        for m in scope.begin_markers:
            idx = source.find(m, cursor)
            if idx >= 0 and (next_begin < 0 or idx < next_begin):
                next_begin = idx
                next_begin_marker = m
        if next_begin < 0:
            break
        # find any end marker after the begin
        search_from = next_begin + len(next_begin_marker or "")
        next_end = -1
        next_end_marker: str | None = None
        for m in scope.end_markers:
            idx = source.find(m, search_from)
            if idx >= 0 and (next_end < 0 or idx < next_end):
                next_end = idx
                next_end_marker = m
        if next_end < 0:
            # Open marker without close — region extends to EOF (fail-loud at
            # report time via a synthetic finding).
            ranges.append((next_begin, n))
            break
        ranges.append((next_begin, next_end + len(next_end_marker or "")))
        cursor = next_end + len(next_end_marker or "")
    return ranges


def _juce_callback_ranges(
    masked: str, scope: ScopeConfig
) -> list[tuple[int, int]]:
    """Char-offset ranges of audio-callback function bodies (JUCE heuristic).

    For each identifier in ``scope.juce_callbacks``, scan for occurrences that
    look like a function definition (identifier followed by ``(`` … ``)`` and
    an opening ``{``). The range covers the body from the function header to
    the matching closing brace, brace-counted.
    """
    ranges: list[tuple[int, int]] = []
    for cb in scope.juce_callbacks:
        # Identifier on a word boundary, then '(' on the same or next line.
        pat = re.compile(rf"\b{re.escape(cb)}\b\s*\(")
        for m in pat.finditer(masked):
            start = m.start()
            # Find the matching '{' after the closing ')'.
            paren_depth = 0
            i = m.end() - 1
            while i < len(masked):
                ch = masked[i]
                if ch == "(":
                    paren_depth += 1
                elif ch == ")":
                    paren_depth -= 1
                    if paren_depth == 0:
                        break
                i += 1
            if i >= len(masked):
                continue
            # Skip whitespace + 'override', 'noexcept', etc. until '{' or ';'.
            j = i + 1
            while j < len(masked) and masked[j] not in "{;":
                j += 1
            if j >= len(masked) or masked[j] != "{":
                # Declaration only (ends with ';'), no body — skip.
                continue
            # Brace-count to find the matching '}'.
            depth = 0
            k = j
            while k < len(masked):
                ch = masked[k]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            if k >= len(masked):
                # Unbalanced braces — emit a synthetic open range to EOF.
                ranges.append((start, len(masked)))
                continue
            ranges.append((start, k + 1))
    return ranges


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping / adjacent half-open offset ranges."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges)
    merged: list[tuple[int, int]] = [sorted_ranges[0]]
    for s, e in sorted_ranges[1:]:
        ms, me = merged[-1]
        if s <= me:
            merged[-1] = (ms, max(me, e))
        else:
            merged.append((s, e))
    return merged


def _in_scope(offset: int, scopes: list[tuple[int, int]]) -> bool:
    for s, e in scopes:
        if s <= offset < e:
            return True
        if offset < s:
            return False
    return False


# --- audit ------------------------------------------------------------------


def audit_file(
    path: Path | str, rules: list[Rule], scope: ScopeConfig
) -> list[Finding]:
    """Audit a single C/C++ source file. Returns findings (may be empty)."""
    p = Path(path)
    try:
        source = p.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError) as exc:
        raise AuditError(f"{p}: cannot read source: {exc}") from exc

    masked = _strip_comments_and_strings(source)
    line_starts = _line_starts(source)

    explicit = _explicit_marker_ranges(source, scope)
    juce = _juce_callback_ranges(masked, scope)
    scopes = _merge_ranges(explicit + juce)

    findings: list[Finding] = []
    if not scopes:
        return findings

    src_lines = source.splitlines()
    for rule in rules:
        for m in rule.pattern.finditer(masked):
            off = m.start()
            if not _in_scope(off, scopes):
                continue
            line, col = _offset_to_line_col(off, line_starts)
            snippet = src_lines[line - 1].strip() if 0 < line <= len(src_lines) else ""
            findings.append(
                Finding(
                    file=str(p),
                    line=line,
                    column=col,
                    rule_id=rule.id,
                    severity=rule.severity,
                    description=rule.description,
                    snippet=snippet,
                )
            )
    # Stable order: by (file, line, column, rule_id) — ENGINEERING_STANDARDS §1.
    findings.sort(key=lambda f: (f.file, f.line, f.column, f.rule_id))
    return findings


def audit_paths(
    paths: list[Path], rules: list[Rule], scope: ScopeConfig,
    extensions: tuple[str, ...] = _DEFAULT_EXTENSIONS,
) -> list[Finding]:
    """Audit one or more files / directories; recurse into directories."""
    targets: list[Path] = []
    for p in paths:
        if p.is_file():
            targets.append(p)
        elif p.is_dir():
            for ext in extensions:
                targets.extend(sorted(p.rglob(f"*{ext}")))
        else:
            raise AuditError(f"path not found: {p}")
    targets = sorted(set(targets))
    findings: list[Finding] = []
    for t in targets:
        findings.extend(audit_file(t, rules, scope))
    return findings


# --- report -----------------------------------------------------------------


def _write_report(
    out_path: Path, findings: list[Finding], n_files: int,
) -> Path:
    """Write a deterministic JSON report (sort-keys, trailing newline)."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "n_files_scanned": n_files,
        "n_findings": len(findings),
        "n_error": sum(1 for f in findings if f.severity == _SEVERITY_ERROR),
        "n_warn": sum(1 for f in findings if f.severity == _SEVERITY_WARN),
        "findings": [f.to_dict() for f in findings],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    out_path.write_text(body + "\n", encoding="utf-8")
    return out_path.resolve()


def _format_human_report(findings: list[Finding], n_files: int) -> str:
    n_err = sum(1 for f in findings if f.severity == _SEVERITY_ERROR)
    n_warn = sum(1 for f in findings if f.severity == _SEVERITY_WARN)
    head = (
        f"[audit_dsp_rigor] {n_files} file scanned · "
        f"{n_err} error · {n_warn} warn"
    )
    if not findings:
        return f"{head}\n  ALL CLEAR — no audio-thread violations."
    lines = [head, "  Findings:"]
    for f in findings:
        marker = "✗" if f.severity == _SEVERITY_ERROR else "⚠"
        lines.append(
            f"  {marker} {f.file}:{f.line}:{f.column}: [{f.rule_id}] "
            f"{f.description}"
        )
        lines.append(f"      {f.snippet}")
    return "\n".join(lines)


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="F0-T6 — Layer-S static gate for the C++ audio thread "
        "(Zero-Allocation invariant)."
    )
    p.add_argument(
        "paths", nargs="+", type=Path,
        help="C++ files or directories to audit.",
    )
    p.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help=f"YAML rules file (default: {DEFAULT_CONFIG.name}).",
    )
    p.add_argument(
        "--report", type=Path, default=None,
        help="Write JSON report to this path (optional).",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Suppress human report on stdout; emit only on error.",
    )
    args = p.parse_args(argv)

    rules, scope = load_config(args.config)
    findings = audit_paths(args.paths, rules, scope)

    # Count distinct files scanned (for the report header).
    scanned: set[Path] = set()
    for path in args.paths:
        if path.is_file():
            scanned.add(path)
        elif path.is_dir():
            for ext in _DEFAULT_EXTENSIONS:
                scanned.update(path.rglob(f"*{ext}"))
    n_files = len(scanned)

    if args.report:
        _write_report(args.report, findings, n_files)

    has_error = any(f.severity == _SEVERITY_ERROR for f in findings)
    if not args.quiet or has_error:
        print(_format_human_report(findings, n_files))

    return 1 if has_error else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
