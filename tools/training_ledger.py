#!/usr/bin/env python3
"""Training Audit Ledger — CLI add / list / diff / query (F0-T4d B3).

Mandatorio: ogni training run del progetto deve avere una entry nel ledger
``docs/audit/training_ledger.yaml``. Il ledger è la single source of truth
versionata: permette di rispondere a "che esperimenti abbiamo fatto, cosa
hanno mostrato, e quale variabile spiega le differenze".

Spec: ``docs/methodology/F0-T4d_PREPROCESSING_HARNESS_AND_AUDIT_SPEC.md`` §4.2.

Usage::

    # Add a new run from a JSON payload (e.g. produced by mini_l3_train.py).
    python tools/training_ledger.py add --from-json artifacts/mini_l3_p1p2.json

    # List all runs with summary.
    python tools/training_ledger.py list

    # Diff two runs (highlights what changed and the metric delta).
    python tools/training_ledger.py diff mini-l3-crosskit-fulldata-2026-05-25 mini-l3-crosskit-p1p2-2026-05-25

    # Filter runs.
    python tools/training_ledger.py query --status FAIL --preprocessing none
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

LEDGER_PATH = Path(__file__).resolve().parents[1] / "docs" / "audit" / "training_ledger.yaml"


def _load() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        return {"schema_version": "1.0", "runs": []}
    payload = yaml.safe_load(LEDGER_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "runs" not in payload:
        raise RuntimeError(f"Malformed ledger at {LEDGER_PATH}")
    return payload


def _save(payload: dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    LEDGER_PATH.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


REQUIRED_FIELDS = {
    "run_id", "date", "git_commit", "status", "purpose",
    "dataset", "model", "preprocessing", "training", "metrics",
    "verdict", "report_html", "cost",
}


def cmd_add(args: argparse.Namespace) -> int:
    """Append a new run to the ledger (fail-loud on duplicate or missing fields)."""
    if args.from_json:
        entry = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    elif args.from_yaml:
        entry = yaml.safe_load(Path(args.from_yaml).read_text(encoding="utf-8"))
    else:
        print("ERROR: provide --from-json or --from-yaml", file=sys.stderr)
        return 1

    missing = REQUIRED_FIELDS - set(entry.keys())
    if missing:
        print(f"ERROR: entry missing required fields: {sorted(missing)}", file=sys.stderr)
        return 1
    payload = _load()
    existing_ids = {r["run_id"] for r in payload["runs"]}
    if entry["run_id"] in existing_ids:
        print(f"ERROR: run_id {entry['run_id']!r} already in ledger — use a unique id "
              f"or remove the previous entry first.", file=sys.stderr)
        return 1
    payload["runs"].append(entry)
    _save(payload)
    print(f"[ledger] added run {entry['run_id']!r} → {LEDGER_PATH}")
    return 0


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    """One-line summary per run, sorted by date."""
    payload = _load()
    runs = sorted(payload["runs"], key=lambda r: str(r.get("date", "")))
    if not runs:
        print("(ledger empty)")
        return 0
    print(f"{'date':<25}  {'status':<6}  {'run_id':<50}  {'preprocessing':<8}  {'metric_value':<10}  notes")
    print("-" * 130)
    for r in runs:
        date = str(r.get("date", "?"))[:25]
        status = r.get("status", "?")
        rid = r.get("run_id", "?")
        prep = r.get("preprocessing", {}).get("kind", "?") if isinstance(r.get("preprocessing"), dict) else "?"
        # Pick the most relevant metric depending on purpose.
        m = r.get("metrics", {})
        val_f = m.get("val_F_mean")
        f_max = m.get("F_max")
        if isinstance(val_f, (int, float)):
            metric = f"val_F={val_f:.3f}"
        elif isinstance(f_max, (int, float)):
            metric = f"F_max={f_max:.3f}"
        else:
            metric = "—"
        notes_short = (r.get("verdict", {}).get("notes") or "")[:50]
        print(f"{date:<25}  {status:<6}  {rid:<50}  {prep:<8}  {metric:<10}  {notes_short}")
    return 0


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def cmd_diff(args: argparse.Namespace) -> int:
    """Show the difference between two runs across every field."""
    payload = _load()
    by_id = {r["run_id"]: r for r in payload["runs"]}
    if args.run_a not in by_id:
        print(f"ERROR: run_id {args.run_a!r} not in ledger", file=sys.stderr)
        return 1
    if args.run_b not in by_id:
        print(f"ERROR: run_id {args.run_b!r} not in ledger", file=sys.stderr)
        return 1
    a, b = by_id[args.run_a], by_id[args.run_b]

    def _walk(prefix: str, va: object, vb: object) -> None:
        if type(va) is not type(vb):
            print(f"  {prefix}: {type(va).__name__} → {type(vb).__name__}")
            print(f"      A: {va!r}")
            print(f"      B: {vb!r}")
            return
        if isinstance(va, dict) and isinstance(vb, dict):
            all_keys = sorted(set(va.keys()) | set(vb.keys()))
            for k in all_keys:
                _walk(f"{prefix}.{k}" if prefix else k, va.get(k, "<missing>"), vb.get(k, "<missing>"))
        elif isinstance(va, list) and isinstance(vb, list):
            if va != vb:
                print(f"  {prefix}:")
                print(f"      A: {va}")
                print(f"      B: {vb}")
        else:
            if va != vb:
                print(f"  {prefix}:")
                print(f"      A: {va!r}")
                print(f"      B: {vb!r}")

    print(f"=== DIFF {args.run_a} → {args.run_b} ===")
    _walk("", a, b)
    return 0


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


def cmd_query(args: argparse.Namespace) -> int:
    """Filter ledger by status / preprocessing kind / kit."""
    payload = _load()
    runs = payload["runs"]
    if args.status:
        runs = [r for r in runs if r.get("status") == args.status]
    if args.preprocessing:
        runs = [r for r in runs
                if (r.get("preprocessing") or {}).get("kind") == args.preprocessing]
    if args.kit:
        runs = [r for r in runs
                if args.kit in (r.get("dataset") or {}).get("train_kits", [])
                or args.kit in (r.get("dataset") or {}).get("val_kits", [])]
    print(f"{len(runs)} matching runs:")
    for r in runs:
        print(f"  - {r['run_id']}  status={r['status']}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description="Training Audit Ledger CLI (F0-T4d B3).")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Add a run to the ledger.")
    p_add.add_argument("--from-json", type=Path, help="JSON file with the entry.")
    p_add.add_argument("--from-yaml", type=Path, help="YAML file with the entry.")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List all runs.")
    p_list.set_defaults(func=cmd_list)

    p_diff = sub.add_parser("diff", help="Diff two runs.")
    p_diff.add_argument("run_a")
    p_diff.add_argument("run_b")
    p_diff.set_defaults(func=cmd_diff)

    p_query = sub.add_parser("query", help="Filter runs.")
    p_query.add_argument("--status", choices=("PASS", "FAIL", "BASELINE", "ABANDONED"))
    p_query.add_argument("--preprocessing", choices=("none", "p1", "p1p2"))
    p_query.add_argument("--kit")
    p_query.set_defaults(func=cmd_query)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
