"""Layer-1 unit oracles for the Sfizz render adapter (F0-T2b).

These exercise :class:`~data_engineering.gold.render.SfizzRenderer` against
*fake* ``sfizz_render`` binaries — small scripts that simulate each failure
mode. They need no real Sfizz install, so they run everywhere and fast; the
real binary is exercised by the §6.3 acceptance suite (``tests/acceptance/``).

The robustness paths under test are the ENGINEERING_STANDARDS §6 mandate:
watchdog timeout and fail-loud on Silent Zero.
"""
from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

from data_engineering.gold.render import RenderError, SfizzRenderer

# --------------------------------------------------------------------------
# Fake-binary fixtures
# --------------------------------------------------------------------------

#: A fake ``sfizz_render`` that accepts the real CLI flags and simulates one
#: behaviour. ``{behavior}`` is substituted per build.
_FAKE_SFIZZ = '''\
#!{python}
import argparse
import sys

BEHAVIOR = "{behavior}"

parser = argparse.ArgumentParser()
parser.add_argument("--sfz")
parser.add_argument("--midi")
parser.add_argument("--wav")
parser.add_argument("--samplerate", type=int)
args, _ = parser.parse_known_args()

if BEHAVIOR == "fail":
    sys.stderr.write("fake sfizz: simulated render failure\\n")
    sys.exit(3)
if BEHAVIOR == "hang":
    import time
    time.sleep(30)
    sys.exit(0)
if BEHAVIOR == "no_output":
    sys.exit(0)

import numpy as np
import soundfile as sf

sr = 48000 if BEHAVIOR == "wrong_sr" else args.samplerate
n = sr // 2
n_ch = 1 if BEHAVIOR == "mono" else 2

if BEHAVIOR == "silent":
    data = np.zeros((n, n_ch), dtype=np.float32)
elif BEHAVIOR == "nan":
    data = np.zeros((n, n_ch), dtype=np.float32)
    data[0, 0] = np.nan
else:
    t = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32)
    tone = 0.5 * np.sin(2.0 * np.pi * 220.0 * t)
    data = np.tile(tone[:, None], (1, n_ch))

sf.write(args.wav, data, sr, subtype="FLOAT")
sys.exit(0)
'''


def _make_fake_sfizz(tmp_path: Path, behavior: str) -> Path:
    """Write an executable fake ``sfizz_render`` with the given behaviour."""
    script = tmp_path / f"fake_sfizz_{behavior}"
    script.write_text(_FAKE_SFIZZ.format(python=sys.executable, behavior=behavior))
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture
def dummy_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """A pair of (sfz, midi) input files — content is irrelevant to the fakes."""
    sfz = tmp_path / "kit.sfz"
    midi = tmp_path / "probe.mid"
    sfz.write_text("<region> sample=x.wav\n")
    midi.write_bytes(b"MThd")
    return sfz, midi


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_render_produces_result_for_valid_inputs(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "ok"))
    result = renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")
    assert result.sample_rate == 44100
    assert result.n_channels == 2
    assert result.n_frames > 0
    assert result.peak > 0.0
    assert result.wav_path.is_file()


def test_render_creates_missing_parent_directory(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "ok"))
    nested = tmp_path / "deep" / "nested" / "out.wav"
    result = renderer.render(sfz_path=sfz, midi_path=midi, wav_path=nested)
    assert result.wav_path == nested
    assert nested.is_file()


def test_mono_render_reports_one_channel(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "mono"))
    result = renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")
    assert result.n_channels == 1


# --------------------------------------------------------------------------
# Input validation — fail loud before invoking the CLI
# --------------------------------------------------------------------------


def test_nonpositive_timeout_is_rejected() -> None:
    with pytest.raises(RenderError, match="timeout_s must be positive"):
        SfizzRenderer(timeout_s=0.0)


def test_missing_binary_raises(tmp_path: Path, dummy_inputs: tuple[Path, Path]) -> None:
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=tmp_path / "does_not_exist")
    with pytest.raises(RenderError, match="Sfizz binary not found"):
        renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")


def test_missing_sfz_raises(tmp_path: Path, dummy_inputs: tuple[Path, Path]) -> None:
    _, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "ok"))
    with pytest.raises(RenderError, match="SFZ file not found"):
        renderer.render(
            sfz_path=tmp_path / "missing.sfz", midi_path=midi, wav_path=tmp_path / "out.wav"
        )


def test_missing_midi_raises(tmp_path: Path, dummy_inputs: tuple[Path, Path]) -> None:
    sfz, _ = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "ok"))
    with pytest.raises(RenderError, match="MIDI file not found"):
        renderer.render(
            sfz_path=sfz, midi_path=tmp_path / "missing.mid", wav_path=tmp_path / "out.wav"
        )


def test_invalid_sample_rate_is_rejected(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    # F0-T2a §1.1 — the sample rate is fixed; resampling is a contract violation.
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "ok"))
    with pytest.raises(RenderError, match="no resampling"):
        renderer.render(
            sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav", sample_rate=48000
        )


# --------------------------------------------------------------------------
# Robustness — ENGINEERING_STANDARDS §6
# --------------------------------------------------------------------------


def test_watchdog_times_out_on_hung_render(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    # A hung render must fail loud, never masquerade as "in progress".
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "hang"), timeout_s=1.0)
    with pytest.raises(RenderError, match="timed out"):
        renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")


def test_silent_zero_render_raises(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    # Fail-loud on Silent Zero — an identically-zero output is a structural defect.
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "silent"))
    with pytest.raises(RenderError, match="silent-zero"):
        renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")


def test_nonzero_exit_raises_with_diagnostics(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "fail"))
    with pytest.raises(RenderError, match="exited with code 3.*simulated render failure"):
        renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")


def test_missing_output_wav_raises(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "no_output"))
    with pytest.raises(RenderError, match="wrote no WAV"):
        renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")


def test_wrong_output_sample_rate_raises(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "wrong_sr"))
    with pytest.raises(RenderError, match="sample rate is 48000"):
        renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")


def test_nonfinite_output_raises(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    sfz, midi = dummy_inputs
    renderer = SfizzRenderer(binary=_make_fake_sfizz(tmp_path, "nan"))
    with pytest.raises(RenderError, match="NaN/Inf"):
        renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")


def test_unexecutable_binary_raises(
    tmp_path: Path, dummy_inputs: tuple[Path, Path]
) -> None:
    # A binary file that exists but cannot be executed must fail loud, not crash.
    sfz, midi = dummy_inputs
    binary = _make_fake_sfizz(tmp_path, "ok")
    binary.chmod(binary.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    renderer = SfizzRenderer(binary=binary)
    with pytest.raises(RenderError, match="cannot execute Sfizz binary"):
        renderer.render(sfz_path=sfz, midi_path=midi, wav_path=tmp_path / "out.wav")
    # Restore the executable bit so tmp cleanup is unaffected.
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
