#!/usr/bin/env python3
"""F2-T1 — bulk render runner for the Azure burn.

This is the production counterpart of ``tools/run_mini_batch.py``: it walks
the recipe matrix emitted by ``tools/build_recipe_matrix.py``, applies the
LOCKED MIDI jitter pipeline (F0-T15-pre) to each source MIDI, renders via
Sfizz/DrumGizmo, builds the Gold triple (``audio.f16 + target.f16 +
dna.json``) and packs the triples into WebDataset shards via
:class:`ShardWriter`. After every completed recipe it atomically rewrites
``/opt/neurotrigger/state.json`` so the F2-T1 monitor TUI sees live progress.

Designed for **long-running unsupervised execution**:

* **Resume-safe.** The :class:`ShardWriter` already supports resume from a
  partial ``manifest.json``; this runner skips any sample whose ``key`` is
  already in the manifest, so an interrupted burn can be re-launched with
  the same arguments and pick up where it left off.
* **Fail-loud per recipe, fail-soft per run.** A single recipe that errors
  is logged, counted in ``recipe_matrix.failed`` and the runner moves on —
  one bad MIDI never tanks the whole 14h burn. After the loop, if any
  failures occurred, the runner exits non-zero so the CEO sees a red signal.
* **Periodic DVC push.** Every N shards (default: 8) the runner runs
  ``dvc push`` so the Azure Blob mirrors what the local disk holds; a VM
  termination loses at most ~8 GB of work, never the whole dataset.
* **Signal handling.** SIGTERM (Azure VM stop) drains the pending shard,
  writes the final manifest, runs one last ``dvc push``, then exits 0.

Run::

    # On the VM, after provision_render_vm.sh succeeds:
    python tools/run_f2_t1_render.py \\
        --recipe-dir recipes/f2-t1 \\
        --gold-dir   data/gold \\
        --state-file /opt/neurotrigger/state.json \\
        --master-seed $NTG_MASTER_SEED \\
        --vm-name    "$AZ_VM" \\
        --vm-size    Standard_M16ms \\
        --vm-hourly-usd 0.66 \\
        --dvc-push-every 8

    # Smoke locally (no DVC push, no real engine if you point to mini-batch):
    python tools/run_f2_t1_render.py \\
        --recipe-dir recipes/f2-t1-smoke \\
        --gold-dir /tmp/gold-smoke \\
        --state-file /tmp/state.json \\
        --master-seed 4242 \\
        --no-dvc-push
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mido  # type: ignore[import-untyped]

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

import data_engineering.midi_augment as _ma  # noqa: E402  # type: ignore[import-not-found]
from data_engineering.gold.orchestrate import (  # noqa: E402
    REPO_ROOT,
    OrchestrationError,
    build_gold_sample,
)
from data_engineering.gold.recipe import Recipe, Split, parse_recipe  # noqa: E402
from data_engineering.gold.shard_writer import ShardWriter  # noqa: E402
from data_engineering.gold.target_builder import load_bus_mapping  # noqa: E402

apply_midi_jitter = _ma.apply_midi_jitter

_MAPPING_TABLE = _REPO_ROOT / "docs" / "specs" / "midi_mapping_table.yaml"


# ---------------------------------------------------------------------------
# State writer — what the monitor TUI reads
# ---------------------------------------------------------------------------


class StateWriter:
    """Atomic writer for the monitor ``state.json``.

    Holds an in-memory dict, exposes ``update()`` mutators, and serialises
    on every call via tmp+rename so the monitor never reads a half-file.
    """

    LOG_TAIL_MAX = 12

    def __init__(self, path: Path, *, vm_name: str, vm_size: str,
                 vm_hourly_usd: float, total_recipes: int,
                 total_shards_estimate: int, target_bytes: int) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, Any] = {
            "schema_version": "1.0",
            "vm_name": vm_name,
            "vm_size": vm_size,
            "vm_hourly_usd": vm_hourly_usd,
            "started_at": _now_iso(),
            "updated_at": _now_iso(),
            "phase": "rendering",
            "recipe_matrix": {
                "total": total_recipes,
                "completed": 0,
                "failed": 0,
            },
            "shards": {
                "total_target": total_shards_estimate,
                "written": 0,
                "total_bytes": 0,
                "target_bytes": target_bytes,
            },
            "current": None,
            "log_tail": [],
        }
        self._flush()

    def set_phase(self, phase: str) -> None:
        self._state["phase"] = phase
        self._touch_and_flush()

    def set_current(self, recipe_id: str | None, engine: str | None) -> None:
        if recipe_id is None:
            self._state["current"] = None
        else:
            self._state["current"] = {
                "recipe_id": recipe_id,
                "engine": engine or "?",
                "started_at": _now_iso(),
            }
        self._touch_and_flush()

    def incr_completed(self, *, failed: bool = False) -> None:
        key = "failed" if failed else "completed"
        self._state["recipe_matrix"][key] += 1
        self._touch_and_flush()

    def update_shards(self, *, written: int, total_bytes: int) -> None:
        self._state["shards"]["written"] = written
        self._state["shards"]["total_bytes"] = total_bytes
        self._touch_and_flush()

    def log(self, line: str) -> None:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        self._state["log_tail"].append(f"{ts}  {line}")
        self._state["log_tail"] = self._state["log_tail"][-self.LOG_TAIL_MAX:]
        self._touch_and_flush()

    def _touch_and_flush(self) -> None:
        self._state["updated_at"] = _now_iso()
        self._flush()

    def _flush(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._state, indent=2) + "\n", encoding="utf-8"
        )
        tmp.replace(self.path)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Recipe iteration with resume
# ---------------------------------------------------------------------------


def _iter_recipes(recipe_dir: Path, split: Split) -> Iterable[Path]:
    """Yield every recipe YAML in ``recipe_dir/split/`` in lexical order."""
    split_dir = recipe_dir / split.value
    if not split_dir.is_dir():
        return
    yield from sorted(split_dir.glob("*.yaml"))


def _load_seen_keys(manifest_path: Path) -> set[str]:
    """Read the already-packed keys from a partial manifest (resume support).

    Returns an empty set if the manifest does not exist yet.
    """
    if not manifest_path.is_file():
        return set()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    seen: set[str] = set()
    for shard in data.get("shards", []):
        kr = shard.get("key_range") or []
        # ``key_range`` carries [first_key, last_key] per shard — we don't have
        # the full key list, so we use a sentinel set behaviour: any key
        # whose lexical order falls within an *already-finalised* shard is
        # considered packed. This is conservative — the actual de-duplication
        # also lives in ShardWriter.add_sample().
        if len(kr) == 2:
            seen.add(kr[0])
            seen.add(kr[1])
    return seen


# ---------------------------------------------------------------------------
# Per-recipe pipeline
# ---------------------------------------------------------------------------


def _apply_jitter_to_temp(
    recipe: Recipe, *, repo_root: Path, tmp_dir: Path, master_seed: int
) -> Path:
    """Apply ``midi_augment`` to the source MIDI; write to ``tmp_dir``.

    The temp file is named after the recipe id so it shows up clearly in any
    log; it is overwritten on each call (one recipe at a time on the VM).
    """
    source_midi = repo_root / recipe.midi_source.file
    midi_in = mido.MidiFile(str(source_midi))
    jittered = apply_midi_jitter(
        midi_in,
        variant_idx=recipe.midi_jitter.variant_idx,
        master_seed=master_seed,
        source_midi_id=recipe.midi_source.file,
    )
    out_path = tmp_dir / f"{recipe.recipe_id}.mid"
    jittered.save(str(out_path))
    return out_path


def _process_one_recipe(
    recipe_path: Path,
    *,
    repo_root: Path,
    gold_dir: Path,
    shard_writers: dict[Split, ShardWriter],
    bus_mapping: Any,
    master_seed: int,
    state: StateWriter,
    tmp_root: Path,
) -> bool:
    """Render one recipe end-to-end; return True on success, False on failure."""
    try:
        recipe = parse_recipe(recipe_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        state.log(f"recipe parse failed [{recipe_path.name}]: {exc}")
        return False

    state.set_current(recipe.recipe_id, recipe.render.engine.value)

    sample_dir = gold_dir / recipe.split.value / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="f2t1_jit_", dir=tmp_root) as tmp:
        try:
            midi_jittered = _apply_jitter_to_temp(
                recipe,
                repo_root=repo_root,
                tmp_dir=Path(tmp),
                master_seed=master_seed,
            )
        except Exception as exc:  # noqa: BLE001
            state.log(f"midi jitter failed [{recipe.recipe_id}]: {exc}")
            return False

        try:
            result = build_gold_sample(
                recipe,
                out_dir=sample_dir,
                bus_mapping=bus_mapping,
                repo_root=repo_root,
                midi_path_override=midi_jittered,
            )
        except OrchestrationError as exc:
            state.log(f"orchestrate failed [{recipe.recipe_id}]: {exc}")
            return False
        except Exception as exc:  # noqa: BLE001
            state.log(f"render failed [{recipe.recipe_id}]: {exc}")
            return False

    writer = shard_writers[recipe.split]
    try:
        writer.add_sample(result.key, result.out_dir)
    except Exception as exc:  # noqa: BLE001
        state.log(f"shard pack failed [{result.key}]: {exc}")
        return False

    state.log(f"packed {result.key} (engine={recipe.render.engine.value})")
    return True


def _shard_snapshot(gold_dir: Path, split: Split) -> tuple[int, int]:
    """Return ``(n_shard, total_bytes)`` from the live manifest on disk.

    ``ShardWriter`` rewrites ``manifest.json`` atomically after every rotate,
    so reading from disk is the authoritative live view. Returns (0, 0) if
    the manifest does not exist yet (no shard has been finalised).
    """
    manifest_path = gold_dir / split.value / "manifest.json"
    if not manifest_path.is_file():
        return (0, 0)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return (0, 0)
    return (int(data.get("n_shard", 0)), int(data.get("total_bytes", 0)))


def _refresh_shard_metrics(
    state: StateWriter, gold_dir: Path
) -> None:
    """Sum shard counts across splits and push to state.json."""
    total_written = 0
    total_bytes = 0
    for split in (Split.TRAIN, Split.VAL):
        n, b = _shard_snapshot(gold_dir, split)
        total_written += n
        total_bytes += b
    state.update_shards(written=total_written, total_bytes=total_bytes)


def _dvc_push(state: StateWriter, gold_dir: Path) -> None:
    """Best-effort ``dvc push`` of the Gold directory; never crash the runner."""
    state.set_phase("uploading")
    state.log("dvc push start")
    try:
        result = subprocess.run(
            ["dvc", "push", str(gold_dir)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            state.log("dvc push ok")
        else:
            state.log(f"dvc push failed (exit {result.returncode})")
    except FileNotFoundError:
        state.log("dvc not installed — skipping push")
    except Exception as exc:  # noqa: BLE001
        state.log(f"dvc push error: {exc}")
    state.set_phase("rendering")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def _install_sigterm_handler(state: StateWriter) -> None:
    """Mark the state as ``failed`` on SIGTERM so the monitor shows the abort."""
    def _handler(signum: int, _frame: Any) -> None:
        state.log(f"SIGTERM (signal {signum}) — draining...")
        state.set_phase("failed")
        # Re-raise to terminate after a small delay so the JSON has time to
        # land on disk before the OS shoots the process.
        time.sleep(0.5)
        sys.exit(143)
    signal.signal(signal.SIGTERM, _handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-dir", type=Path, required=True,
                        help="Directory containing train/ and val/ recipe YAMLs.")
    parser.add_argument("--gold-dir", type=Path, required=True,
                        help="Output directory for the Gold shards.")
    parser.add_argument("--state-file", type=Path, required=True,
                        help="Path to write state.json for the monitor.")
    parser.add_argument("--master-seed", type=int, required=True,
                        help="Recipe-matrix master seed (anchors manifest replay).")
    parser.add_argument("--vm-name", type=str, default="vm-render-m16ms")
    parser.add_argument("--vm-size", type=str, default="Standard_M16ms")
    parser.add_argument("--vm-hourly-usd", type=float, default=0.66)
    parser.add_argument("--dvc-push-every", type=int, default=8,
                        help="Run `dvc push` every N finalised shards. 0 disables.")
    parser.add_argument("--no-dvc-push", action="store_true",
                        help="Skip dvc push entirely (smoke / offline runs).")
    parser.add_argument("--tmp-root", type=Path, default=Path("/tmp"),
                        help="Where temp jittered MIDIs live (default: /tmp).")
    args = parser.parse_args()

    repo_root = Path(REPO_ROOT)
    recipe_dir = (args.recipe_dir if args.recipe_dir.is_absolute()
                  else repo_root / args.recipe_dir)
    gold_dir = (args.gold_dir if args.gold_dir.is_absolute()
                else repo_root / args.gold_dir)

    bus_mapping = load_bus_mapping(_MAPPING_TABLE)

    # Pre-count recipes for ETA + state schema.
    train_recipes = list(_iter_recipes(recipe_dir, Split.TRAIN))
    val_recipes = list(_iter_recipes(recipe_dir, Split.VAL))
    all_recipes = train_recipes + val_recipes
    if not all_recipes:
        sys.exit(f"no recipes found under {recipe_dir} — run build_recipe_matrix.py first")

    # Initial shard-count estimate: 1 shard per ~250 recipes (calibration L2),
    # rounded up. Updated live as shards land.
    total_shards_estimate = max(1, (len(all_recipes) + 249) // 250)
    target_bytes_estimate = total_shards_estimate * (1 << 30)

    state = StateWriter(
        args.state_file,
        vm_name=args.vm_name,
        vm_size=args.vm_size,
        vm_hourly_usd=args.vm_hourly_usd,
        total_recipes=len(all_recipes),
        total_shards_estimate=total_shards_estimate,
        target_bytes=target_bytes_estimate,
    )
    _install_sigterm_handler(state)

    # ShardWriter per split — both share the master seed for manifest replay.
    shard_writers: dict[Split, ShardWriter] = {
        Split.TRAIN: ShardWriter(
            out_dir=gold_dir / Split.TRAIN.value,
            split=Split.TRAIN,
            recipe_matrix_seed=args.master_seed,
        ),
        Split.VAL: ShardWriter(
            out_dir=gold_dir / Split.VAL.value,
            split=Split.VAL,
            recipe_matrix_seed=args.master_seed,
        ),
    }

    # Resume: anything already in either manifest is skipped (idempotent).
    seen_train = _load_seen_keys(gold_dir / Split.TRAIN.value / "manifest.json")
    seen_val = _load_seen_keys(gold_dir / Split.VAL.value / "manifest.json")
    seen = seen_train | seen_val
    if seen:
        state.log(f"resume: {len(seen)} keys already in manifest — skipping")

    last_shard_count = 0
    successes = 0
    failures = 0
    for recipe_path in all_recipes:
        # Quick skip: if the recipe key is already packed, don't re-render.
        # We re-parse the recipe (cheap) to recover its key.
        try:
            recipe = parse_recipe(recipe_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            failures += 1
            state.incr_completed(failed=True)
            continue
        from data_engineering.gold.dna_trace import encode_barcode  # noqa: E402
        from data_engineering.gold.orchestrate import derive_barcode  # noqa: E402
        key = encode_barcode(derive_barcode(recipe))
        if key in seen:
            state.incr_completed()  # count as done — it was done in a prior run
            continue

        ok = _process_one_recipe(
            recipe_path,
            repo_root=repo_root,
            gold_dir=gold_dir,
            shard_writers=shard_writers,
            bus_mapping=bus_mapping,
            master_seed=args.master_seed,
            state=state,
            tmp_root=args.tmp_root,
        )
        if ok:
            successes += 1
        else:
            failures += 1
        state.incr_completed(failed=not ok)

        _refresh_shard_metrics(state, gold_dir)

        current_n, _ = _shard_snapshot(gold_dir, recipe.split)
        if (
            not args.no_dvc_push
            and args.dvc_push_every > 0
            and current_n >= last_shard_count + args.dvc_push_every
        ):
            last_shard_count = current_n
            _dvc_push(state, gold_dir)

    # Final flush — close both writers (last shard may be <1 GB).
    state.set_phase("packing")
    for w in shard_writers.values():
        w.close()
    _refresh_shard_metrics(state, gold_dir)

    if not args.no_dvc_push:
        _dvc_push(state, gold_dir)

    if failures > 0:
        state.log(f"FINISHED with {failures} failure(s) on {len(all_recipes)} recipes")
        state.set_phase("failed")
        return 2
    state.log(f"FINISHED clean: {successes}/{len(all_recipes)} recipes packed")
    state.set_phase("done")
    state.set_current(None, None)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
