"""Sfizz render engine — drives the ``sfizz_render`` CLI (F0-T2b).

This is the rewrite of the scrapped FluidSynth ``MidiRenderer`` prototype: the
Design Lock selected SFZ multi-layer libraries rendered through **Sfizz**
(F0-T2a §2.1, DOSSIER §3.2). :class:`SfizzRenderer` is a thin, fail-loud
adapter over the vendored ``sfizz_render`` binary (``vendor/sfizz/`` —
ENGINEERING_STANDARDS §4).

Robustness contract (ENGINEERING_STANDARDS §6):

* **Watchdog.** Every CLI invocation is wrapped in an explicit timeout. A hung
  render must fail loud, never masquerade as "in progress" — on Azure that is
  burnt credit (the *Tracker-Integrity Trap*).
* **Fail-loud on Silent Zero.** A render whose output is identically zero is a
  *structural defect*, not a statistical edge case: it is rejected before any
  caller can mistake it for valid audio.

DrumGizmo — the multi-mic / bleed engine — is a separate adapter (F0-T2c) and
will reuse :class:`RenderError` / :class:`RenderResult` from this module.

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §2.1.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]

#: Fixed render sample rate — no resampling (F0-T2a §1.1/§3.2, DOSSIER §6.1).
SAMPLE_RATE = 44100

#: Repo root, resolved from this file: ``src/data_engineering/gold/render.py``.
_REPO_ROOT = Path(__file__).resolve().parents[3]
#: Path of the vendored Sfizz CLI (manifest: ``vendor/README.md``).
DEFAULT_SFIZZ_BINARY = _REPO_ROOT / "vendor" / "sfizz" / "sfizz_render"

#: Default watchdog timeout for a single render, in seconds. A mini-batch clip
#: is a few seconds of audio; a render that exceeds this is hung, not slow.
DEFAULT_TIMEOUT_S = 120.0


class RenderError(RuntimeError):
    """Raised when a render fails.

    Covers bad inputs, a missing binary, a non-zero CLI exit, a watchdog
    timeout, and a missing, unreadable or silent-zero output WAV. Fail-loud
    contract (ENGINEERING_STANDARDS §6): the renderer never returns a
    :class:`RenderResult` for a render it could not prove correct.
    """


@dataclass(frozen=True)
class RenderResult:
    """Verified outcome of one successful render.

    Attributes:
        wav_path: Path to the rendered WAV file.
        sample_rate: Sample rate of the WAV (always :data:`SAMPLE_RATE`).
        n_channels: Channel count of the WAV.
        n_frames: Number of audio frames (samples per channel).
        peak: Largest absolute sample amplitude — strictly ``> 0`` (a silent
            render is rejected upstream).
    """

    wav_path: Path
    sample_rate: int
    n_channels: int
    n_frames: int
    peak: float


class SfizzRenderer:
    """Fail-loud adapter over the ``sfizz_render`` CLI (F0-T2a §2.1).

    The SFZ library handles velocity layers and round-robin internally; the
    renderer only references the ``.sfz`` file and produces a clean stereo
    stem — no inter-instrument bleed (that is DrumGizmo's role, F0-T2c).
    """

    def __init__(
        self,
        *,
        binary: str | Path = DEFAULT_SFIZZ_BINARY,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        """Configure the renderer.

        Args:
            binary: Path to the ``sfizz_render`` executable. Defaults to the
                vendored binary.
            timeout_s: Watchdog timeout for a single render, in seconds. Must
                be positive.

        Raises:
            RenderError: If ``timeout_s`` is not positive.
        """
        if timeout_s <= 0:
            raise RenderError(f"timeout_s must be positive, got {timeout_s}")
        self._binary = Path(binary)
        self._timeout_s = timeout_s

    def render(
        self,
        *,
        sfz_path: str | Path,
        midi_path: str | Path,
        wav_path: str | Path,
        sample_rate: int = SAMPLE_RATE,
    ) -> RenderResult:
        """Render ``midi_path`` through ``sfz_path`` into ``wav_path``.

        Args:
            sfz_path: SFZ instrument file driving the render.
            midi_path: Input MIDI file.
            wav_path: Destination WAV path; parent directories are created.
            sample_rate: Output sample rate. Must be :data:`SAMPLE_RATE` — the
                contract forbids resampling (F0-T2a §1.1).

        Returns:
            A :class:`RenderResult` describing the verified output WAV.

        Raises:
            RenderError: On any failure — missing binary or inputs, an invalid
                ``sample_rate``, a non-zero CLI exit, a watchdog timeout, or a
                missing, unreadable or silent-zero output WAV.
        """
        sfz = Path(sfz_path)
        midi = Path(midi_path)
        wav = Path(wav_path)

        if sample_rate != SAMPLE_RATE:
            raise RenderError(
                f"sample_rate must be {SAMPLE_RATE} (no resampling); got {sample_rate}"
            )
        if not self._binary.is_file():
            raise RenderError(f"Sfizz binary not found: {self._binary}")
        if not sfz.is_file():
            raise RenderError(f"SFZ file not found: {sfz}")
        if not midi.is_file():
            raise RenderError(f"MIDI file not found: {midi}")

        wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(self._binary),
            "--sfz", str(sfz),
            "--midi", str(midi),
            "--wav", str(wav),
            "--samplerate", str(sample_rate),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(
                f"Sfizz render timed out after {self._timeout_s:g}s "
                f"(watchdog, ENGINEERING_STANDARDS §6) — {sfz.name}"
            ) from exc
        except OSError as exc:
            raise RenderError(f"cannot execute Sfizz binary {self._binary}: {exc}") from exc

        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or "no diagnostics"
            raise RenderError(
                f"Sfizz render exited with code {proc.returncode} for {sfz.name}: {detail}"
            )
        if not wav.is_file():
            raise RenderError(f"Sfizz reported success but wrote no WAV: {wav}")

        return self._verify(wav, sample_rate)

    @staticmethod
    def _verify(wav: Path, expected_sr: int) -> RenderResult:
        """Read the output WAV and prove it is a valid, non-silent render."""
        try:
            data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
        except sf.LibsndfileError as exc:
            raise RenderError(f"rendered WAV is unreadable: {wav} — {exc}") from exc

        if sr != expected_sr:
            raise RenderError(
                f"rendered WAV sample rate is {sr}, expected {expected_sr}: {wav}"
            )
        if data.shape[0] == 0:
            raise RenderError(f"rendered WAV is empty (zero frames): {wav}")
        if not bool(np.isfinite(data).all()):
            raise RenderError(f"rendered WAV contains NaN/Inf: {wav}")

        peak = float(np.abs(data).max())
        if peak == 0.0:
            raise RenderError(
                f"silent-zero render — output is identically zero: {wav} "
                "(ENGINEERING_STANDARDS §6 — fail-loud on Silent Zero)"
            )
        return RenderResult(
            wav_path=wav,
            sample_rate=int(sr),
            n_channels=int(data.shape[1]),
            n_frames=int(data.shape[0]),
            peak=peak,
        )
