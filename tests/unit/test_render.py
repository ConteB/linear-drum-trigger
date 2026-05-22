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

import numpy as np
import pytest
import soundfile as sf  # type: ignore[import-untyped]

from data_engineering.gold.recipe import MIC_CONFIG_CHANNELS, MicConfig
from data_engineering.gold.render import (
    DRSKIT_MULTITRACK8,
    DrumGizmoRenderer,
    RenderError,
    SfizzRenderer,
)

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


# ==========================================================================
# DrumGizmo render adapter (F0-T2c)
# ==========================================================================

#: A fake ``drumgizmo`` that accepts the real CLI surface and simulates one
#: behaviour. It writes one mono WAV per channel — ``{prefix}{Name}-{idx}.wav``
#: — exactly as the real ``wavfile`` output engine does (observed 2026-05-22).
_FAKE_DRUMGIZMO = '''\
#!{python}
import argparse
import sys

BEHAVIOR = "{behavior}"

parser = argparse.ArgumentParser()
parser.add_argument("-s", action="store_true")
parser.add_argument("-i")
parser.add_argument("-I")
parser.add_argument("-o")
parser.add_argument("-O")
parser.add_argument("-e")
parser.add_argument("kit")
args, _ = parser.parse_known_args()

if BEHAVIOR == "fail":
    sys.stderr.write("fake drumgizmo: simulated render failure\\n")
    sys.exit(4)
if BEHAVIOR == "hang":
    import time
    time.sleep(30)
    sys.exit(0)
if BEHAVIOR == "no_output":
    sys.exit(0)

oparms = dict(kv.split("=", 1) for kv in args.O.split(","))
prefix = oparms["file"]
sr = int(oparms.get("srate", 44100))

import numpy as np
import soundfile as sf

n = sr // 2
channels = ["Kick", "Snare", "OH"]
for idx, name in enumerate(channels):
    if BEHAVIOR == "silent":
        data = np.zeros(n, dtype=np.float32)
    elif BEHAVIOR == "nan" and idx == 0:
        data = np.zeros(n, dtype=np.float32)
        data[0] = np.nan
    else:
        t = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32)
        data = (0.3 * (idx + 1)) * np.sin(2.0 * np.pi * (110.0 * (idx + 1)) * t)
    length = n - 100 if (BEHAVIOR == "ragged" and idx == 1) else n
    sr_out = 48000 if (BEHAVIOR == "wrong_sr" and idx == 0) else sr
    sf.write("%s%s-%d.wav" % (prefix, name, idx), data[:length], sr_out, subtype="FLOAT")
sys.exit(0)
'''


def _make_fake_drumgizmo(tmp_path: Path, behavior: str) -> Path:
    """Write an executable fake ``drumgizmo`` with the given behaviour."""
    script = tmp_path / f"fake_drumgizmo_{behavior}"
    script.write_text(_FAKE_DRUMGIZMO.format(python=sys.executable, behavior=behavior))
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture
def dgz_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A (kit, midimap, midi) triple — content is irrelevant to the fakes."""
    kit = tmp_path / "kit.xml"
    midimap = tmp_path / "midimap.xml"
    midi = tmp_path / "probe.mid"
    kit.write_text("<drumkit/>\n")
    midimap.write_text("<midimap/>\n")
    midi.write_bytes(b"MThd")
    return kit, midimap, midi


def _dgz_render(renderer: DrumGizmoRenderer, dgz_inputs: tuple[Path, Path, Path],
                wav: Path):
    """Invoke ``renderer.render`` with the standard fake inputs."""
    kit, midimap, midi = dgz_inputs
    return renderer.render(
        kit_path=kit, midimap_path=midimap, midi_path=midi, wav_path=wav,
        duration_s=0.5,
    )


# --- Happy path -----------------------------------------------------------


def test_drumgizmo_render_assembles_multichannel_wav(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    result = _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")
    assert result.sample_rate == 44100
    assert result.n_channels == 3
    assert result.n_frames > 0
    assert result.peak > 0.0
    assert result.wav_path.is_file()


def test_drumgizmo_channel_labels_follow_kit_channel_order(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    # The ``-{idx}`` suffix is the kit channel order; labels must follow it.
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    result = _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")
    assert result.channel_labels == ("Kick", "Snare", "OH")


def test_drumgizmo_render_creates_missing_parent_directory(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    nested = tmp_path / "deep" / "nested" / "out.wav"
    result = _dgz_render(renderer, dgz_inputs, nested)
    assert result.wav_path == nested
    assert nested.is_file()


# --- Input validation — fail loud before invoking the CLI -----------------


def test_drumgizmo_nonpositive_timeout_is_rejected() -> None:
    with pytest.raises(RenderError, match="timeout_s must be positive"):
        DrumGizmoRenderer(timeout_s=0.0)


def test_drumgizmo_missing_binary_raises(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    renderer = DrumGizmoRenderer(binary="no_such_drumgizmo_binary_xyz")
    with pytest.raises(RenderError, match="binary not found on PATH"):
        _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")


def test_drumgizmo_missing_kit_raises(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    _, midimap, midi = dgz_inputs
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    with pytest.raises(RenderError, match="kit file not found"):
        renderer.render(
            kit_path=tmp_path / "missing.xml", midimap_path=midimap,
            midi_path=midi, wav_path=tmp_path / "out.wav", duration_s=0.5,
        )


def test_drumgizmo_missing_midimap_raises(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    kit, _, midi = dgz_inputs
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    with pytest.raises(RenderError, match="MIDI map file not found"):
        renderer.render(
            kit_path=kit, midimap_path=tmp_path / "missing.xml",
            midi_path=midi, wav_path=tmp_path / "out.wav", duration_s=0.5,
        )


def test_drumgizmo_missing_midi_raises(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    kit, midimap, _ = dgz_inputs
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    with pytest.raises(RenderError, match="MIDI file not found"):
        renderer.render(
            kit_path=kit, midimap_path=midimap,
            midi_path=tmp_path / "missing.mid", wav_path=tmp_path / "out.wav",
            duration_s=0.5,
        )


def test_drumgizmo_invalid_sample_rate_is_rejected(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    kit, midimap, midi = dgz_inputs
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    with pytest.raises(RenderError, match="no resampling"):
        renderer.render(
            kit_path=kit, midimap_path=midimap, midi_path=midi,
            wav_path=tmp_path / "out.wav", duration_s=0.5, sample_rate=48000,
        )


def test_drumgizmo_nonpositive_duration_is_rejected(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    kit, midimap, midi = dgz_inputs
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    with pytest.raises(RenderError, match="duration_s must be positive"):
        renderer.render(
            kit_path=kit, midimap_path=midimap, midi_path=midi,
            wav_path=tmp_path / "out.wav", duration_s=0.0,
        )


# --- Robustness — ENGINEERING_STANDARDS §6 --------------------------------


def test_drumgizmo_watchdog_times_out_on_hung_render(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    renderer = DrumGizmoRenderer(
        binary=_make_fake_drumgizmo(tmp_path, "hang"), timeout_s=1.0
    )
    with pytest.raises(RenderError, match="timed out"):
        _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")


def test_drumgizmo_silent_zero_render_raises(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "silent"))
    with pytest.raises(RenderError, match="silent-zero"):
        _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")


def test_drumgizmo_nonzero_exit_raises_with_diagnostics(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "fail"))
    with pytest.raises(RenderError, match="exited with code 4.*simulated render failure"):
        _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")


def test_drumgizmo_no_output_wavs_raises(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "no_output"))
    with pytest.raises(RenderError, match="wrote no channel WAVs"):
        _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")


def test_drumgizmo_nonfinite_output_raises(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "nan"))
    with pytest.raises(RenderError, match="NaN/Inf"):
        _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")


def test_drumgizmo_ragged_channels_raise(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    # Channels that disagree on length are a structural defect — fail loud.
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ragged"))
    with pytest.raises(RenderError, match="differ in length"):
        _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")


def test_drumgizmo_wrong_channel_sample_rate_raises(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "wrong_sr"))
    with pytest.raises(RenderError, match="sample rate is 48000"):
        _dgz_render(renderer, dgz_inputs, tmp_path / "out.wav")


# --- Channel selection — 13->8 standardisation (F0-T2c) -------------------


def test_drumgizmo_channel_map_selects_and_reorders(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    # The fake renders channels Kick/Snare/OH; the map selects two of them in
    # a new order with canonical labels — proving selection + reorder.
    kit, midimap, midi = dgz_inputs
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    wav = tmp_path / "out.wav"
    result = renderer.render(
        kit_path=kit, midimap_path=midimap, midi_path=midi, wav_path=wav,
        duration_s=0.5, channel_map=(("low", "OH"), ("kik", "Kick")),
    )
    assert result.n_channels == 2
    assert result.channel_labels == ("low", "kik")
    # The fake makes OH the loudest channel and Kick the quietest; after the
    # reorder column 0 ('low'<-OH) must out-peak column 1 ('kik'<-Kick).
    audio, _ = sf.read(str(wav), dtype="float32", always_2d=True)
    assert np.abs(audio[:, 0]).max() > np.abs(audio[:, 1]).max()


def test_drumgizmo_channel_map_unknown_channel_raises(
    tmp_path: Path, dgz_inputs: tuple[Path, Path, Path]
) -> None:
    # A map naming a channel the kit never rendered must fail loud.
    kit, midimap, midi = dgz_inputs
    renderer = DrumGizmoRenderer(binary=_make_fake_drumgizmo(tmp_path, "ok"))
    with pytest.raises(RenderError, match="did not render"):
        renderer.render(
            kit_path=kit, midimap_path=midimap, midi_path=midi,
            wav_path=tmp_path / "out.wav", duration_s=0.5,
            channel_map=(("x", "NoSuchChannel"),),
        )


def test_drskit_multitrack8_aligns_with_locked_spec() -> None:
    """DRSKIT_MULTITRACK8's canonical labels are exactly multitrack_full (F0-T2a §2.3)."""
    canonical = tuple(label for label, _ in DRSKIT_MULTITRACK8)
    assert canonical == MIC_CONFIG_CHANNELS[MicConfig.MULTITRACK_FULL]
    # Every DRSKit source channel is named once — no slot fed twice.
    sources = [kit_channel for _, kit_channel in DRSKIT_MULTITRACK8]
    assert len(sources) == len(set(sources))
