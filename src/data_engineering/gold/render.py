"""Render engines — Sfizz and DrumGizmo CLI adapters (F0-T2b / F0-T2c).

Two fail-loud adapters over the project's render toolchain, each producing a
verified :class:`RenderResult`:

* :class:`SfizzRenderer` drives ``sfizz_render`` (F0-T2b) — SFZ multi-layer
  libraries, a clean stereo stem, **no** inter-instrument bleed. Rewrite of the
  scrapped FluidSynth ``MidiRenderer`` prototype (Design Lock 2026-05-20,
  F0-T2a §2.1, DOSSIER §3.2).
* :class:`DrumGizmoRenderer` drives ``drumgizmo`` (F0-T2c) — multi-microphone
  kits whose channels carry the real mic *bleed*, the product's moat (F0-T2a
  §2.2). DrumGizmo writes one mono WAV per kit channel; the adapter assembles
  them, in kit-channel order, into a single multi-channel WAV.

Robustness contract (ENGINEERING_STANDARDS §6), enforced by both adapters:

* **Watchdog.** Every CLI invocation is wrapped in an explicit timeout. A hung
  render must fail loud, never masquerade as "in progress" — on Azure that is
  burnt credit (the *Tracker-Integrity Trap*).
* **Fail-loud on Silent Zero.** A render whose output is identically zero is a
  *structural defect*, not a statistical edge case: it is rejected before any
  caller can mistake it for valid audio.

Spec: ``docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md`` §2.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
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
        wav_path: Path to the rendered WAV file. For :class:`DrumGizmoRenderer`
            this is the assembled multi-channel WAV.
        sample_rate: Sample rate of the WAV (always :data:`SAMPLE_RATE`).
        n_channels: Channel count of the WAV.
        n_frames: Number of audio frames (samples per channel).
        peak: Largest absolute sample amplitude — strictly ``> 0`` (a silent
            render is rejected upstream).
        channel_labels: Per-channel names, in WAV channel order, when the
            engine exposes them (DrumGizmo kit-channel names — F0-T2a §2.3).
            ``None`` for Sfizz, whose stereo stem has no per-mic naming.
    """

    wav_path: Path
    sample_rate: int
    n_channels: int
    n_frames: int
    peak: float
    channel_labels: tuple[str, ...] | None = None


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


#: Per-channel WAV name written by DrumGizmo's ``wavfile`` output engine —
#: ``{prefix}{ChannelName}-{index}.wav`` (observed on the real CLI, 2026-05-22).
_DGZ_CHANNEL_RE = r"^{prefix}(?P<name>.+)-(?P<idx>\d+)\.wav$"

#: DRSKit (13 mic) -> the industry-standard 8-channel layout — F0-T2a §2.3
#: ``multitrack_full``, aligned to Superior Drummer 3 / EZdrummer / Steven Slate
#: Drums / GetGood Drums (Decision Lock CEO 2026-05-22). Ordered
#: ``(canonical_label, drskit_channel)`` pairs. Selection only — one real mic
#: per slot, never down-mixed (down-mixing two spaced mics combs the signal).
#: Dropped from DRSKit: Kdrum_back, Snare_bottom, Ride, Tom2, AmbR.
DRSKIT_MULTITRACK8: tuple[tuple[str, str], ...] = (
    ("kick", "Kdrum_front"),
    ("snare", "Snare_top"),
    ("hihat", "Hihat"),
    ("tom", "Tom1"),
    ("floor", "Tom3"),
    ("oh_L", "OHL"),
    ("oh_R", "OHR"),
    ("room", "AmbL"),
)


class DrumGizmoRenderer:
    """Fail-loud adapter over the ``drumgizmo`` CLI (F0-T2a §2.2).

    DrumGizmo renders a multi-microphone kit: every kit channel is a real mic,
    so the channels carry genuine inter-instrument *bleed* — the signal
    characteristic Sfizz cannot produce and the product's primary moat.

    The CLI's ``wavfile`` output engine writes **one mono WAV per kit channel**
    (``{prefix}{ChannelName}-{index}.wav``); this adapter collects them in
    kit-channel order (the ``index`` suffix) and assembles a single
    multi-channel WAV, returning a :class:`RenderResult` whose
    ``channel_labels`` preserve the kit's mic names.

    The adapter is engine-faithful: it reports the kit's *native* channel count
    (e.g. 13 for DRSKit). Reconciling that with the recipe ``mic_config`` /
    the Gold-tensor ``n_mic <= 8`` contract (F0-T2a §3.2) is a downstream
    concern, not the renderer's.

    The ``drumgizmo`` binary is provisioned on Linux (apt; the F2 render runs
    on Azure Linux) — there is no macOS prebuilt. The adapter resolves it on
    ``PATH``; acceptance tests skip where it is absent.
    """

    def __init__(
        self,
        *,
        binary: str | Path = "drumgizmo",
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        """Configure the renderer.

        Args:
            binary: Name or path of the ``drumgizmo`` executable; resolved on
                ``PATH``. Defaults to ``"drumgizmo"``.
            timeout_s: Watchdog timeout for a single render, in seconds. Must
                be positive.

        Raises:
            RenderError: If ``timeout_s`` is not positive.
        """
        if timeout_s <= 0:
            raise RenderError(f"timeout_s must be positive, got {timeout_s}")
        self._binary = str(binary)
        self._timeout_s = timeout_s

    def render(
        self,
        *,
        kit_path: str | Path,
        midimap_path: str | Path,
        midi_path: str | Path,
        wav_path: str | Path,
        duration_s: float,
        channel_map: tuple[tuple[str, str], ...] | None = None,
        sample_rate: int = SAMPLE_RATE,
    ) -> RenderResult:
        """Render ``midi_path`` through a DrumGizmo kit into a multi-mic WAV.

        Args:
            kit_path: DrumGizmo kit ``.xml`` file (defines the mic channels).
            midimap_path: MIDI-map ``.xml`` mapping notes to kit instruments.
            midi_path: Input MIDI file.
            wav_path: Destination of the assembled multi-channel WAV; parent
                directories are created.
            duration_s: Desired output length in seconds — the caller must
                include enough tail for cymbal/ambience decay. Drives the CLI
                ``--endpos`` sample count.
            channel_map: Optional ordered ``(canonical_label, kit_channel)``
                pairs. When given, the rendered kit channels are **selected and
                reordered** onto this layout — e.g. :data:`DRSKIT_MULTITRACK8`
                maps DRSKit's 13 mics onto the standard 8 (F0-T2a §2.3). When
                ``None`` the renderer is engine-faithful, returning every kit
                channel (the future ``NeuroTrigger Pro`` path).
            sample_rate: Output sample rate. Must be :data:`SAMPLE_RATE` — the
                contract forbids resampling (F0-T2a §1.1).

        Returns:
            A :class:`RenderResult` for the assembled multi-channel WAV. Its
            ``channel_labels`` are the canonical labels of ``channel_map`` when
            one is given, otherwise the kit's own mic names in channel order.

        Raises:
            RenderError: On any failure — an unresolved binary, missing inputs,
                an invalid ``sample_rate`` or ``duration_s``, a non-zero CLI
                exit, a watchdog timeout, no channel WAVs written, non-contiguous
                channel indices, channels that disagree on sample rate or
                length, a ``channel_map`` naming a channel the kit did not
                render, or a non-finite or silent-zero render.
        """
        kit = Path(kit_path)
        midimap = Path(midimap_path)
        midi = Path(midi_path)
        wav = Path(wav_path)

        if sample_rate != SAMPLE_RATE:
            raise RenderError(
                f"sample_rate must be {SAMPLE_RATE} (no resampling); got {sample_rate}"
            )
        if duration_s <= 0:
            raise RenderError(f"duration_s must be positive, got {duration_s}")
        binary = shutil.which(self._binary)
        if binary is None:
            raise RenderError(f"DrumGizmo binary not found on PATH: {self._binary}")
        for label, path in (("kit", kit), ("MIDI map", midimap), ("MIDI", midi)):
            if not path.is_file():
                raise RenderError(f"{label} file not found: {path}")

        endpos = round(duration_s * sample_rate)
        wav.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="dgz_render_") as tmp:
            prefix = Path(tmp) / "ch"
            cmd = [
                binary,
                "-s",  # streaming — bound RAM for multi-GB kits
                "-i", "midifile",
                "-I", f"file={midi},midimap={midimap}",
                "-o", "wavfile",
                "-O", f"file={prefix},srate={sample_rate}",
                "-e", str(endpos),
                str(kit),
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
                    f"DrumGizmo render timed out after {self._timeout_s:g}s "
                    f"(watchdog, ENGINEERING_STANDARDS §6) — {kit.name}"
                ) from exc
            except OSError as exc:
                raise RenderError(
                    f"cannot execute DrumGizmo binary {binary}: {exc}"
                ) from exc

            if proc.returncode != 0:
                detail = proc.stderr.strip() or proc.stdout.strip() or "no diagnostics"
                raise RenderError(
                    f"DrumGizmo render exited with code {proc.returncode} "
                    f"for {kit.name}: {detail}"
                )
            return self._assemble(prefix, wav, sample_rate, channel_map)

    @staticmethod
    def _assemble(
        prefix: Path,
        wav: Path,
        expected_sr: int,
        channel_map: tuple[tuple[str, str], ...] | None,
    ) -> RenderResult:
        """Collect the per-channel WAVs and assemble one verified multi-mic WAV.

        When ``channel_map`` is given the kit channels are selected and
        reordered onto its canonical layout; otherwise every channel is kept.
        """
        pattern = re.compile(_DGZ_CHANNEL_RE.format(prefix=re.escape(prefix.name)))
        found: list[tuple[int, str, Path]] = []
        for entry in prefix.parent.iterdir():
            match = pattern.match(entry.name)
            if match:
                found.append((int(match["idx"]), match["name"], entry))
        if not found:
            raise RenderError(
                f"DrumGizmo reported success but wrote no channel WAVs "
                f"(prefix {prefix.name!r} in {prefix.parent})"
            )
        found.sort(key=lambda item: item[0])
        indices = [idx for idx, _, _ in found]
        if indices != list(range(len(indices))):
            raise RenderError(
                f"DrumGizmo channel indices are not contiguous 0..N-1: {indices}"
            )

        columns: list[np.ndarray] = []
        labels: list[str] = []
        for _, name, path in found:
            try:
                data, sr = sf.read(str(path), dtype="float32", always_2d=True)
            except sf.LibsndfileError as exc:
                raise RenderError(
                    f"DrumGizmo channel WAV is unreadable: {path} — {exc}"
                ) from exc
            if sr != expected_sr:
                raise RenderError(
                    f"DrumGizmo channel {name!r} sample rate is {sr}, "
                    f"expected {expected_sr}"
                )
            if data.shape[1] != 1:
                raise RenderError(
                    f"DrumGizmo channel {name!r} is not mono ({data.shape[1]} channels)"
                )
            if columns and data.shape[0] != columns[0].shape[0]:
                raise RenderError(
                    f"DrumGizmo channels differ in length: {name!r} has "
                    f"{data.shape[0]} frames, expected {columns[0].shape[0]}"
                )
            columns.append(data[:, 0])
            labels.append(name)

        if channel_map is not None:
            by_name = dict(zip(labels, columns, strict=True))
            selected: list[np.ndarray] = []
            for _, kit_channel in channel_map:
                if kit_channel not in by_name:
                    raise RenderError(
                        f"channel_map names kit channel {kit_channel!r}, which "
                        f"the kit did not render; rendered channels: {sorted(by_name)}"
                    )
                selected.append(by_name[kit_channel])
            columns = selected
            labels = [canonical for canonical, _ in channel_map]

        audio = np.stack(columns, axis=1)  # [n_sample, n_mic]
        n_sample = int(audio.shape[0])
        if n_sample == 0:
            raise RenderError(f"DrumGizmo render is empty (zero frames): {wav}")
        if not bool(np.isfinite(audio).all()):
            raise RenderError(f"DrumGizmo render contains NaN/Inf: {wav}")
        peak = float(np.abs(audio).max())
        if peak == 0.0:
            raise RenderError(
                f"silent-zero render — every DrumGizmo channel is identically "
                f"zero: {wav} (ENGINEERING_STANDARDS §6 — fail-loud on Silent Zero)"
            )

        sf.write(str(wav), audio, expected_sr, subtype="FLOAT")
        return RenderResult(
            wav_path=wav,
            sample_rate=expected_sr,
            n_channels=int(audio.shape[1]),
            n_frames=n_sample,
            peak=peak,
            channel_labels=tuple(labels),
        )
