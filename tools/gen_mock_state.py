#!/usr/bin/env python3
"""F2-T1 — mock state.json generator for monitor smoke-testing.

Simulates the production runner: writes ``/tmp/f2-t1-state.json`` and updates
it on a fast clock (default: every 0.5 s) so the monitor TUI can be developed
and demoed without provisioning Azure. The progress curve is realistic-shape
(linear) and the log tail is fake but plausibly formatted, so the smoke
ratifies the TUI layout end-to-end.

Run::

    python tools/gen_mock_state.py &
    python tools/f2_t1_monitor.py --source mock --interval 2

Stop with ``kill %1`` or just close the parent terminal.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path

#: Mock matrix size — small enough that the simulation completes in a few
#: minutes on default interval.
DEFAULT_TOTAL_RECIPES = 210
DEFAULT_TOTAL_SHARDS = 30
DEFAULT_TARGET_BYTES = int(30 * 1024**3)  # ~30 GB for the mock
DEFAULT_VM_HOURLY = 0.77
DEFAULT_VM_NAME = "vm-render-d16s"
DEFAULT_VM_SIZE = "Standard_D16s_v3"

_GMD_NAMES = ("rock", "funk", "afro", "metal", "jazz", "latin", "blues")
_KITS = ("DRSKit", "CrocellKit", "Frankensnare", "UnrulyDrums", "BigRustyDrums")
_ENGINES = ("drumgizmo", "sfizz")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fake_recipe_id(index: int) -> str:
    name = random.choice(_GMD_NAMES)
    kit = random.choice(_KITS)
    variant = random.randint(0, 2)
    return f"R-F2T1-GMD{index:03d}-{name}-{kit}-J{variant:02d}"


def _fake_log_line(index: int, kind: str) -> str:
    ts = datetime.now(UTC).strftime("%H:%M:%S")
    if kind == "shard":
        return f"{ts}  shard gold-train-{index:06d}.tar packed (1.02 GB)"
    if kind == "start":
        return f"{ts}  start render {_fake_recipe_id(index)}"
    return f"{ts}  finish render GMD{index:03d}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/f2-t1-state.json"),
        help="State file to write (default: /tmp/f2-t1-state.json).",
    )
    parser.add_argument(
        "--tick", type=float, default=0.5,
        help="Seconds between updates (default: 0.5).",
    )
    parser.add_argument(
        "--total", type=int, default=DEFAULT_TOTAL_RECIPES,
        help="Total recipe count (default: 210).",
    )
    parser.add_argument(
        "--start-completed", type=int, default=0,
        help="Initial completed count (for resume scenarios).",
    )
    args = parser.parse_args()

    started_at = _now_iso()
    completed = args.start_completed
    shards_written = completed * DEFAULT_TOTAL_SHARDS // max(args.total, 1)
    log_tail: list[str] = []

    while completed <= args.total:
        # Progress one recipe per tick (deterministic enough for the demo).
        completed = min(completed + 1, args.total)
        new_shards = completed * DEFAULT_TOTAL_SHARDS // args.total
        if new_shards > shards_written:
            shards_written = new_shards
            log_tail.append(_fake_log_line(shards_written, "shard"))
        log_tail.append(_fake_log_line(completed, "start"))
        log_tail = log_tail[-12:]  # cap

        if completed < args.total:
            phase = "rendering"
            current: dict[str, str] | None = {
                "recipe_id": _fake_recipe_id(completed),
                "engine": random.choice(_ENGINES),
                "started_at": _now_iso(),
            }
        else:
            phase = "done"
            current = None

        ratio = completed / max(args.total, 1)
        state: dict[str, object] = {
            "schema_version": "1.0",
            "vm_name": DEFAULT_VM_NAME,
            "vm_size": DEFAULT_VM_SIZE,
            "vm_hourly_usd": DEFAULT_VM_HOURLY,
            "started_at": started_at,
            "updated_at": _now_iso(),
            "phase": phase,
            "recipe_matrix": {
                "total": args.total,
                "completed": completed,
                "failed": 0,
            },
            "shards": {
                "total_target": DEFAULT_TOTAL_SHARDS,
                "written": shards_written,
                "total_bytes": int(DEFAULT_TARGET_BYTES * ratio),
                "target_bytes": DEFAULT_TARGET_BYTES,
            },
            "current": current,
            "log_tail": list(log_tail),
        }

        # Atomic write — tmp + rename, so the monitor never reads a half-file.
        tmp = args.output.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        tmp.replace(args.output)

        if phase == "done":
            print(f"mock done — final state at {args.output}")
            return 0
        time.sleep(args.tick)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
