#!/usr/bin/env python3
"""F2-T1 burn monitor — real-time TUI over the Azure render VM.

The render runner on the VM writes a small ``state.json`` (schema below) to
``/opt/neurotrigger/state.json`` every N samples. This script fetches that
file periodically — either over SSH (``--source ssh``) or from a local mock
file (``--source mock``) — and renders a 5-panel TUI:

    1. Header — VM name, status, elapsed time, ETA.
    2. Progress — recipe and shard completion bars + volume.
    3. Current — which recipe is being rendered right now.
    4. Cost — VM compute estimate (elapsed × $/h) and projected full-burn cost.
    5. Log tail — the last few render events.

Designed to be **forgiving**: a missing state.json renders "waiting for first
state…" instead of crashing; a malformed JSON shows a stale-data warning. The
CEO can leave this open in a terminal for hours without worrying about it
dying on a transient SSH glitch.

state.json schema (1.0)
-----------------------

    {
      "schema_version": "1.0",
      "vm_name": "vm-render-d16s",
      "vm_size": "Standard_D16s_v3",
      "vm_hourly_usd": 0.77,
      "started_at": "2026-05-23T14:02:00Z",
      "updated_at": "2026-05-23T14:32:15Z",
      "phase": "rendering",        // provisioning | smoke | rendering |
                                   // packing | uploading | done | failed
      "recipe_matrix": {"total": 210, "completed": 43, "failed": 0},
      "shards": {"total_target": 1500, "written": 3,
                 "total_bytes": 3214000000, "target_bytes": 4500000000000},
      "current": {"recipe_id": "R-F2T1-GMD142-DRSKit-J01",
                  "engine": "drumgizmo",
                  "started_at": "2026-05-23T14:31:48Z"},
      "log_tail": ["…", "…", "…"]
    }

Run
---

    # Local mock (no VM needed — for smoke testing the monitor itself)
    python tools/gen_mock_state.py &
    python tools/f2_t1_monitor.py --source mock --mock-path /tmp/state.json

    # Real VM
    python tools/f2_t1_monitor.py \\
        --source ssh \\
        --ssh-target azureuser@<vm-public-ip> \\
        --interval 30
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

_REPO_ROOT = Path(__file__).resolve().parents[1]

# ----------------------------------------------------------------------------
# Constants — match MASTER_SCHEDULING §5 thresholds
# ----------------------------------------------------------------------------

#: Azure credit budget; updated to match the live cap.
AZURE_BUDGET_USD: float = 200.0
#: Monitoring thresholds (USD remaining) — colour-coded in the cost panel.
THRESHOLD_GREEN: float = 100.0  # ">$100 left" — calm
THRESHOLD_YELLOW: float = 40.0  # "$40-100 left" — watch
THRESHOLD_RED: float = 10.0     # "$10-40 left" — kill switch ready

#: Phase glyphs.
PHASE_GLYPH = {
    "provisioning": "[yellow]◐[/yellow]",
    "smoke":        "[yellow]◐[/yellow]",
    "rendering":    "[green]●[/green]",
    "packing":      "[green]●[/green]",
    "uploading":    "[cyan]↑[/cyan]",
    "done":         "[bold green]✓[/bold green]",
    "failed":       "[bold red]✗[/bold red]",
}

# ----------------------------------------------------------------------------
# State fetching — SSH (real VM) or filesystem (mock)
# ----------------------------------------------------------------------------


class StateFetchError(RuntimeError):
    """Wraps any failure to read/parse the state.json — never fatal."""


def _fetch_local(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise StateFetchError(f"mock state file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateFetchError(f"malformed JSON in {path}: {exc}") from exc


def _fetch_ssh(target: str, remote_path: str, timeout_s: float) -> dict[str, Any]:
    """Read ``remote_path`` on ``target`` via SSH. Fails soft."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
             target, f"cat {remote_path}"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise StateFetchError(f"ssh timed out after {timeout_s}s") from exc
    if result.returncode != 0:
        raise StateFetchError(
            f"ssh exit {result.returncode}: {result.stderr.strip()[:200]}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StateFetchError(f"malformed JSON from ssh: {exc}") from exc


# ----------------------------------------------------------------------------
# Rendering — each panel is built from a fresh state dict on every refresh
# ----------------------------------------------------------------------------


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m:02d}m {s:02d}s"


def _format_bytes(b: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    val = float(b)
    for unit in units:
        if abs(val) < 1024.0 or unit == units[-1]:
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{val:.2f} {units[-1]}"


def _build_header(state: dict[str, Any], now: datetime) -> Panel:
    vm_name = state.get("vm_name", "?")
    vm_size = state.get("vm_size", "?")
    phase = state.get("phase", "unknown")
    glyph = PHASE_GLYPH.get(phase, "[dim]?[/dim]")
    started = _parse_iso(state.get("started_at"))
    elapsed_s = (now - started).total_seconds() if started else 0
    eta_text = ""
    matrix = state.get("recipe_matrix", {})
    total = int(matrix.get("total", 0))
    completed = int(matrix.get("completed", 0))
    if total > 0 and completed > 0 and elapsed_s > 0:
        rate = completed / elapsed_s  # recipes/sec
        remaining = (total - completed) / rate
        eta_text = f"  ETA: {_format_duration(remaining)}"
    text = (
        f"{glyph} {vm_name}  ([cyan]{vm_size}[/cyan])  "
        f"phase: [bold]{phase}[/bold]\n"
        f"elapsed: [bold]{_format_duration(elapsed_s)}[/bold]{eta_text}"
    )
    return Panel(text, title="F2-T1 burn", title_align="left", border_style="cyan")


def _build_progress(state: dict[str, Any]) -> Panel:
    matrix = state.get("recipe_matrix", {})
    shards = state.get("shards", {})
    progress = Progress(
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(bar_width=40),
        TextColumn("{task.percentage:>5.1f}%"),
        TextColumn("[dim]({task.completed}/{task.total})[/dim]"),
        expand=False,
    )
    t_total = max(int(matrix.get("total", 0)), 1)
    t_done = int(matrix.get("completed", 0))
    progress.add_task("Recipes", total=t_total, completed=t_done)
    s_total = max(int(shards.get("total_target", 0)), 1)
    s_done = int(shards.get("written", 0))
    progress.add_task("Shards ", total=s_total, completed=s_done)

    volume_text = Text.assemble(
        ("Volume   ", "bold"),
        (
            f"{_format_bytes(shards.get('total_bytes', 0))}  /  "
            f"{_format_bytes(shards.get('target_bytes', 0))}",
            "",
        ),
    )
    failed = int(matrix.get("failed", 0))
    if failed > 0:
        volume_text.append(f"   [red]failed: {failed}[/red]")

    body = Group(progress, Text(""), volume_text)
    return Panel(body, title="progress", title_align="left", border_style="green")


def _build_current(state: dict[str, Any], now: datetime) -> Panel:
    cur = state.get("current") or {}
    recipe_id = cur.get("recipe_id")
    if not recipe_id:
        return Panel(
            Align.center(Text("[dim]idle — between recipes[/dim]")),
            title="now",
            title_align="left",
            border_style="dim",
        )
    engine = cur.get("engine", "?")
    started = _parse_iso(cur.get("started_at"))
    age = _format_duration((now - started).total_seconds()) if started else "?"
    text = (
        f"[bold]{recipe_id}[/bold]\n"
        f"engine: [cyan]{engine}[/cyan]   "
        f"started {age} ago"
    )
    return Panel(text, title="now", title_align="left", border_style="magenta")


def _build_cost(state: dict[str, Any], now: datetime) -> Panel:
    started = _parse_iso(state.get("started_at"))
    hourly = float(state.get("vm_hourly_usd", 0))
    elapsed_h = (now - started).total_seconds() / 3600.0 if started else 0
    spent = elapsed_h * hourly
    matrix = state.get("recipe_matrix", {})
    total = max(int(matrix.get("total", 0)), 1)
    completed = max(int(matrix.get("completed", 0)), 1)
    projected_total = (
        (elapsed_h / max(completed, 1)) * total * hourly
        if elapsed_h > 0 else hourly * 14  # fall-back: 14h calibration
    )
    remaining_budget = AZURE_BUDGET_USD - spent

    if remaining_budget > THRESHOLD_GREEN:
        budget_style = "green"
    elif remaining_budget > THRESHOLD_YELLOW:
        budget_style = "yellow"
    else:
        budget_style = "red"

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style="dim")
    table.add_column(justify="left")
    elapsed_str = _format_duration(elapsed_h * 3600)
    table.add_row(
        "VM compute spent",
        f"[bold]${spent:.2f}[/bold]  ({elapsed_str} × ${hourly:.2f}/h)",
    )
    table.add_row(
        "Projected full-burn",
        f"[bold]${projected_total:.2f}[/bold]",
    )
    budget_text = (
        f"[{budget_style}]${remaining_budget:.2f}[/{budget_style}]"
        f"  / ${AZURE_BUDGET_USD:.0f}"
    )
    table.add_row("Budget left", budget_text)
    table.add_row("Storage Blob",
                  "[dim]see Azure portal · cumulative[/dim]")
    return Panel(table, title="cost", title_align="left", border_style=budget_style)


def _build_log(state: dict[str, Any]) -> Panel:
    log_tail = state.get("log_tail") or []
    if not log_tail:
        body: Group | Text = Text("[dim]no events yet[/dim]")
    else:
        # Reverse so the freshest line is at the bottom (terminal-natural).
        lines = [Text(str(line)) for line in log_tail[-8:]]
        body = Group(*lines)
    return Panel(body, title="recent log", title_align="left", border_style="blue")


def _build_layout(state: dict[str, Any], now: datetime,
                  warning: str | None) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="progress", size=8),
        Layout(name="middle", size=5),
        Layout(name="cost", size=8),
        Layout(name="log", size=11),
        Layout(name="footer", size=2),
    )
    layout["header"].update(_build_header(state, now))
    layout["progress"].update(_build_progress(state))
    layout["middle"].update(_build_current(state, now))
    layout["cost"].update(_build_cost(state, now))
    layout["log"].update(_build_log(state))
    footer_text = Text.assemble(
        ("[q]", "bold"), (" quit   ", ""),
        ("[r]", "bold"), (" refresh now   ", ""),
        ("polling every ", "dim"),
        (str(state.get("_poll_interval", "?")), "dim"),
        ("s · last poll: ", "dim"),
        (now.strftime("%H:%M:%S"), "dim"),
    )
    if warning:
        footer_text.append(f"   [yellow]⚠ {warning}[/yellow]")
    layout["footer"].update(Align.center(footer_text))
    return layout


def _waiting_layout(reason: str) -> Layout:
    layout = Layout()
    layout.update(
        Panel(
            Align.center(
                Text.from_markup(
                    "[bold]waiting for first state…[/bold]\n"
                    f"[dim]{reason}[/dim]\n\n"
                    "The render VM writes ``/opt/neurotrigger/state.json``\n"
                    "every N samples. This panel refreshes automatically."
                )
            ),
            title="F2-T1 burn",
            border_style="yellow",
        )
    )
    return layout


# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------


def _fetch_state(args: argparse.Namespace) -> dict[str, Any]:
    if args.source == "mock":
        return _fetch_local(args.mock_path)
    if args.source == "ssh":
        return _fetch_ssh(args.ssh_target, args.ssh_remote_path, args.ssh_timeout)
    raise ValueError(f"unknown source: {args.source}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-time TUI monitor for the F2-T1 Azure render burn."
    )
    parser.add_argument(
        "--source", choices=("ssh", "mock"), default="mock",
        help="Where to read the state from (default: mock).",
    )
    parser.add_argument(
        "--mock-path", type=Path, default=Path("/tmp/f2-t1-state.json"),
        help="(mock) Local state.json path (default: /tmp/f2-t1-state.json).",
    )
    parser.add_argument(
        "--ssh-target", type=str, default="azureuser@vm-render",
        help="(ssh) Target for `ssh user@host` (default: azureuser@vm-render).",
    )
    parser.add_argument(
        "--ssh-remote-path", type=str, default="/opt/neurotrigger/state.json",
        help="(ssh) Remote state.json path.",
    )
    parser.add_argument(
        "--ssh-timeout", type=float, default=15.0,
        help="(ssh) Per-poll SSH timeout in seconds.",
    )
    parser.add_argument(
        "--interval", type=float, default=30.0,
        help="Polling interval in seconds (default: 30).",
    )
    args = parser.parse_args()

    console = Console()
    state: dict[str, Any] | None = None
    warning: str | None = None

    with Live(_waiting_layout("starting…"), console=console,
              refresh_per_second=4, screen=True) as live:
        try:
            while True:
                try:
                    state = _fetch_state(args)
                    state["_poll_interval"] = args.interval
                    warning = None
                except StateFetchError as exc:
                    warning = f"poll failed: {exc}"
                    # keep showing the previous state if we had one
                now = datetime.now(UTC)
                if state is None:
                    live.update(_waiting_layout(warning or "no state yet"))
                else:
                    live.update(_build_layout(state, now, warning))
                time.sleep(args.interval)
        except KeyboardInterrupt:
            console.print("[dim]monitor stopped — VM keeps rendering on Azure.[/dim]")
            return 0


if __name__ == "__main__":
    sys.exit(main())
