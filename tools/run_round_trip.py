"""F0-T4b L3 round-trip — PyTorch ↔ NumPy reference ↔ C++ smoke test.

Drives the three-way comparison:

1. Load the trained TCN checkpoint, dump a deterministic test input.
2. Run the **PyTorch** forward — the ground-truth implementation.
3. Run the **NumPy reference** forward (``neural.export.numpy_reference_forward``)
   on the JSON export — proves the operations are exportable losslessly.
4. Run the **C++ smoke test** (``cpp/round_trip_smoke``) on the binary sidecar —
   proves the operations are implementable in C++ using the RTNeural-equivalent
   op-set (Conv1D + ReLU/sigmoid/tanh + additive merge), the L3 gate's central
   architectural de-risking (F0-T4a §7, §8).

Pass criterion: max(|PyTorch - X|) < tolerance for X ∈ {NumPy, C++}, where the
tolerance is the fp32 precision floor (default 1e-5).

Run:  ``python tools/run_round_trip.py``
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch

# So we can import from src/ without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from neural.data import load_pool  # noqa: E402
from neural.export import export_tcn, numpy_reference_forward  # noqa: E402
from neural.export_bin import export_binary  # noqa: E402
from neural.model import TCNConfig, TCNModel  # noqa: E402

DEFAULT_CKPT = Path("artifacts/f0t4b_tcn.pt")
DEFAULT_BIN_OUT = Path("artifacts/f0t4b_tcn.bin")
DEFAULT_JSON_OUT = Path("artifacts/f0t4b_tcn.json")
DEFAULT_BUILD_DIR = Path("cpp/round_trip_smoke/build")
DEFAULT_TOL = 1e-5


def _ensure_binary_built(build_dir: Path) -> Path:
    exe = build_dir / "round_trip_smoke"
    if not exe.is_file():
        print(f"[round-trip] building C++ smoke binary in {build_dir} ...", flush=True)
        src_dir = build_dir.parent
        build_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["cmake", str(src_dir.resolve())], cwd=build_dir, check=True
        )
        subprocess.run(["cmake", "--build", "."], cwd=build_dir, check=True)
    return exe


def _pick_input(audio: np.ndarray, n_sample: int) -> np.ndarray:
    """Take the deterministic leading window from ``audio`` (float32, [8, n_sample])."""
    n_sample = (n_sample // 128) * 128
    return audio[:, :n_sample].astype(np.float32, copy=False)


def run(
    ckpt_path: Path = DEFAULT_CKPT,
    *,
    json_out: Path = DEFAULT_JSON_OUT,
    bin_out: Path = DEFAULT_BIN_OUT,
    build_dir: Path = DEFAULT_BUILD_DIR,
    pool_root: Path = Path("data/gold/L2_pool"),
    sample_key: str = "GMD000-V0T0-DGZ-R0-L1-NONE",
    n_sample: int = 16384,
    tolerance: float = DEFAULT_TOL,
    report_to: Path | None = Path("docs/gates/L3_OCULAR_PROOF/round_trip_report.json"),
) -> dict[str, object]:
    """Execute the three-way comparison and return a summary dict."""
    # 1. Load model.
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    model = TCNModel(TCNConfig())
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    # 2. Export.
    json_path = export_tcn(model, json_out)
    bin_path = export_binary(json_path, bin_out)
    print(f"[round-trip] exported JSON → {json_path}")
    print(f"[round-trip] exported BIN  → {bin_path}")

    # 3. Pick a deterministic input from a real Gold sample.
    pool = load_pool(pool_root, keys=[sample_key])
    if not pool:
        raise SystemExit(f"sample {sample_key} not found under {pool_root}")
    audio = _pick_input(pool[0].audio, n_sample)
    print(f"[round-trip] input audio: {audio.shape} from {sample_key}")

    # 4. PyTorch forward — the ground truth.
    with torch.no_grad():
        pt_out = (
            model(torch.from_numpy(audio).unsqueeze(0).float())
            .squeeze(0)
            .numpy()
            .astype(np.float32, copy=False)
        )
    print(f"[round-trip] PyTorch out: {pt_out.shape}")

    # 5. NumPy reference forward — exportability of the op-set.
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    np_out = numpy_reference_forward(doc, audio).astype(np.float32, copy=False)
    np_max = float(np.abs(pt_out - np_out).max())
    np_mean = float(np.abs(pt_out - np_out).mean())
    print(f"[round-trip] PyTorch ↔ NumPy   max|Δ|={np_max:.3e}  mean|Δ|={np_mean:.3e}")

    # 6. C++ smoke test — implementability on the streaming inference target.
    exe = _ensure_binary_built(build_dir)
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        audio_path = tmpd / "input.f32"
        out_path = tmpd / "output.f32"
        # Audio layout: raw float32, [8, n_sample]. C++ side computes time = bytes / (8*4).
        audio_path.write_bytes(audio.astype("<f4").tobytes())
        proc = subprocess.run(
            [str(exe), str(bin_path), str(audio_path), str(out_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
            raise SystemExit("C++ smoke-test failed")
        print(f"[round-trip] C++ stderr: {proc.stderr.strip()}")
        cpp_flat = np.frombuffer(out_path.read_bytes(), dtype="<f4")
    n_frame = pt_out.shape[0]
    if cpp_flat.size != n_frame * pt_out.shape[1]:
        raise SystemExit(
            f"C++ output size {cpp_flat.size} does not match expected "
            f"{n_frame * pt_out.shape[1]}"
        )
    cpp_out = cpp_flat.reshape(n_frame, pt_out.shape[1])
    cpp_max = float(np.abs(pt_out - cpp_out).max())
    cpp_mean = float(np.abs(pt_out - cpp_out).mean())
    print(f"[round-trip] PyTorch ↔ C++     max|Δ|={cpp_max:.3e}  mean|Δ|={cpp_mean:.3e}")

    # 7. Verdict.
    passes_numpy = np_max < tolerance
    passes_cpp = cpp_max < tolerance
    print(
        f"[round-trip] tolerance={tolerance:.0e}  "
        f"numpy_pass={passes_numpy}  cpp_pass={passes_cpp}"
    )

    summary: dict[str, object] = {
        "ckpt_path": str(ckpt_path),
        "sample_key": sample_key,
        "input_shape": list(audio.shape),
        "output_shape": list(pt_out.shape),
        "tolerance": tolerance,
        "numpy_max_abs_diff": np_max,
        "numpy_mean_abs_diff": np_mean,
        "cpp_max_abs_diff": cpp_max,
        "cpp_mean_abs_diff": cpp_mean,
        "numpy_pass": passes_numpy,
        "cpp_pass": passes_cpp,
        "round_trip_pass": passes_numpy and passes_cpp,
    }
    if report_to is not None:
        report_to.parent.mkdir(parents=True, exist_ok=True)
        report_to.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"[round-trip] wrote report to {report_to}")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="F0-T4b L3 round-trip smoke test")
    p.add_argument("--ckpt", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    p.add_argument("--bin-out", type=Path, default=DEFAULT_BIN_OUT)
    p.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    p.add_argument("--pool", type=Path, default=Path("data/gold/L2_pool"))
    p.add_argument("--sample-key", default="GMD000-V0T0-DGZ-R0-L1-NONE")
    p.add_argument("--n-sample", type=int, default=16384)
    p.add_argument("--tolerance", type=float, default=DEFAULT_TOL)
    p.add_argument(
        "--report-to", type=Path,
        default=Path("docs/gates/L3_OCULAR_PROOF/round_trip_report.json"),
    )
    args = p.parse_args()
    summary = run(
        ckpt_path=args.ckpt,
        json_out=args.json_out,
        bin_out=args.bin_out,
        build_dir=args.build_dir,
        pool_root=args.pool,
        sample_key=args.sample_key,
        n_sample=args.n_sample,
        tolerance=args.tolerance,
        report_to=args.report_to,
    )
    if not summary["round_trip_pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
