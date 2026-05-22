"""§6.3 acceptance oracles — Sfizz render engine (F0-T2b).

These exercise :class:`~data_engineering.gold.render.SfizzRenderer` end-to-end
against the **real** vendored ``sfizz_render`` binary and a vendored SFZ kit
(Karoryfer Frankensnare, CC0 — ``vendor/README.md``). They are skipped where
that toolchain is absent so the suite still runs on a bare checkout; the
robustness paths are covered binary-free by ``tests/unit/test_render.py``.

Acceptance criteria (TESTING_DOCTRINE §6.3, F0-T2b):
* render is deterministic — same SFZ + same MIDI ⇒ bit-identical audio;
* output sample rate is 44.1 kHz;
* channel count is the Sfizz clean stereo stem (F0-T2a §2.1);
* amplitude stays within the unit range ``[-1, 1]`` (F0-T2a §3.5).
"""
from __future__ import annotations

from pathlib import Path

import mido
import numpy as np
import pytest
import soundfile as sf  # type: ignore[import-untyped]

from data_engineering.gold.render import DEFAULT_SFIZZ_BINARY, RenderResult, SfizzRenderer

pytestmark = pytest.mark.acceptance

#: Vendored SFZ kit used as the F0-T2b development instrument (vendor/README.md).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_KIT_SFZ = _REPO_ROOT / "vendor" / "sfz" / "frankensnare" / "Programs" / "03-10x6ash.sfz"

#: GM note for the acoustic snare — Frankensnare maps the snare here.
_SNARE_NOTE = 38

# Skip the whole module unless the vendored render toolchain is present.
pytestmark = [
    pytestmark,
    pytest.mark.skipif(
        not DEFAULT_SFIZZ_BINARY.is_file(),
        reason="vendored sfizz_render binary absent — see vendor/README.md",
    ),
    pytest.mark.skipif(
        not _KIT_SFZ.is_file(),
        reason="vendored Frankensnare SFZ kit absent — see vendor/README.md",
    ),
]


@pytest.fixture(scope="module")
def probe_midi(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A short MIDI of six snare hits — the render's deterministic input."""
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    midi.tracks.append(track)
    for hit in range(6):
        track.append(
            mido.Message("note_on", note=_SNARE_NOTE, velocity=100, time=0 if hit == 0 else 240)
        )
        track.append(mido.Message("note_off", note=_SNARE_NOTE, velocity=64, time=120))
    track.append(mido.MetaMessage("end_of_track", time=0))
    path = tmp_path_factory.mktemp("probe") / "snare_probe.mid"
    midi.save(str(path))
    return path


@pytest.fixture(scope="module")
def rendered(probe_midi: Path, tmp_path_factory: pytest.TempPathFactory) -> RenderResult:
    """One render of the probe MIDI through the vendored kit."""
    wav = tmp_path_factory.mktemp("render") / "out.wav"
    return SfizzRenderer().render(sfz_path=_KIT_SFZ, midi_path=probe_midi, wav_path=wav)


def test_sfizz_render_sample_rate_is_44100(rendered: RenderResult) -> None:
    """Rendered WAV is 44.1 kHz (F0-T2a §1.1 — no resampling)."""
    assert rendered.sample_rate == 44100
    assert rendered.n_frames > 0


def test_sfizz_render_produces_stereo_stem(rendered: RenderResult) -> None:
    """Sfizz emits a clean stereo stem — 2 channels, no bleed (F0-T2a §2.1).

    The mic-config-driven channel counts (4/8 mic) are DrumGizmo's concern and
    are checked by the F0-T2c acceptance oracle.
    """
    assert rendered.n_channels == 2


def test_sfizz_render_amplitude_within_unit_range(rendered: RenderResult) -> None:
    """Amplitude stays inside the contract range [-1, 1] (F0-T2a §3.5)."""
    assert 0.0 < rendered.peak <= 1.0


def test_sfizz_render_is_deterministic(
    probe_midi: Path, tmp_path: Path
) -> None:
    """Same SFZ + same MIDI ⇒ bit-identical audio (TESTING_DOCTRINE §6.3).

    Equality is asserted on the decoded samples — the meaningful determinism
    property (ENGINEERING_STANDARDS §1) — not on raw file bytes.
    """
    renderer = SfizzRenderer()
    first = renderer.render(
        sfz_path=_KIT_SFZ, midi_path=probe_midi, wav_path=tmp_path / "a.wav"
    )
    second = renderer.render(
        sfz_path=_KIT_SFZ, midi_path=probe_midi, wav_path=tmp_path / "b.wav"
    )
    audio_a, _ = sf.read(str(first.wav_path), dtype="float32", always_2d=True)
    audio_b, _ = sf.read(str(second.wav_path), dtype="float32", always_2d=True)
    assert np.array_equal(audio_a, audio_b)
