"""§6.3 acceptance oracles — DrumGizmo render engine (F0-T2c).

These exercise :class:`~data_engineering.gold.render.DrumGizmoRenderer`
end-to-end against the **real** ``drumgizmo`` CLI and the vendored DRSKit
multi-mic kit (CC-BY-4.0 — ``vendor/README.md``). They are skipped where that
toolchain is absent so the suite still runs on a bare checkout; ``drumgizmo``
has no macOS prebuilt and is provisioned on Linux (OrbStack VM / Azure), so on
a macOS host these skip and the robustness paths are covered binary-free by
``tests/unit/test_render.py``.

Acceptance criteria (TESTING_DOCTRINE §6.3, F0-T2c — rectified 2026-05-22):

* the render is standardised onto the industry-standard 8-channel layout
  (F0-T2a §2.3 ``multitrack_full``) via :data:`DRSKIT_MULTITRACK8`;
* the engine-faithful mode (no channel map) still exposes every kit mic;
* output sample rate is 44.1 kHz;
* **bleed is present** — proven *falsifiably* by the **envelope correlation**
  between two distinct mic channels (a polarity-free metric: raw waveform
  cross-correlation gives false negatives, as the DRSKit probe showed), with an
  uncorrelated-signal control that must collapse to ~0.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import mido
import numpy as np
import pytest
import soundfile as sf  # type: ignore[import-untyped]

from data_engineering.gold.recipe import MIC_CONFIG_CHANNELS, MicConfig
from data_engineering.gold.render import (
    DRSKIT_MULTITRACK8,
    DrumGizmoRenderer,
    RenderResult,
)

pytestmark = pytest.mark.acceptance

#: Vendored DRSKit — the F0-T2c development kit (vendor/README.md).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_KIT_DIR = _REPO_ROOT / "vendor" / "drumgizmo" / "DRSKit"
_KIT_XML = _KIT_DIR / "DRSKit_full.xml"
_MIDIMAP_XML = _KIT_DIR / "Midimap_full.xml"

#: GM notes mapped by Midimap_full.xml (verified 2026-05-22).
_KICK_NOTE = 36
_SNARE_NOTE = 38

# Skip the whole module unless the real toolchain is present.
pytestmark = [
    pytestmark,
    pytest.mark.skipif(
        shutil.which("drumgizmo") is None,
        reason="drumgizmo CLI not on PATH — provisioned on Linux, see vendor/README.md",
    ),
    pytest.mark.skipif(
        not _KIT_XML.is_file(),
        reason="vendored DRSKit kit absent — see vendor/README.md",
    ),
]


def _envelope(signal: np.ndarray, win: int = 512) -> np.ndarray:
    """Windowed-RMS amplitude envelope — polarity-free, slowly varying."""
    n_win = len(signal) // win
    frames = signal[: n_win * win].reshape(n_win, win)
    return np.sqrt((frames**2).mean(axis=1))


def _envelope_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation of the two signals' amplitude envelopes.

    The bleed metric (TESTING_DOCTRINE §6.3): the same physical hits raise the
    envelope of every mic that captures them, regardless of inter-mic polarity
    or delay — so a bleeding pair correlates strongly, an isolated/uncorrelated
    pair collapses to ~0.
    """
    ea = _envelope(a) - _envelope(a).mean()
    eb = _envelope(b) - _envelope(b).mean()
    denom = np.linalg.norm(ea) * np.linalg.norm(eb)
    return float(np.dot(ea, eb) / denom) if denom > 0 else 0.0


@pytest.fixture(scope="module")
def probe_midi(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A short kick/snare beat — the render's deterministic MIDI input."""
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    midi.tracks.append(track)
    for hit in range(8):
        note = _KICK_NOTE if hit % 2 == 0 else _SNARE_NOTE
        track.append(
            mido.Message("note_on", note=note, velocity=100, time=0 if hit == 0 else 240)
        )
        track.append(mido.Message("note_off", note=note, velocity=64, time=120))
    track.append(mido.MetaMessage("end_of_track", time=0))
    path = tmp_path_factory.mktemp("probe") / "beat_probe.mid"
    midi.save(str(path))
    return path


@pytest.fixture(scope="module")
def rendered(probe_midi: Path, tmp_path_factory: pytest.TempPathFactory) -> RenderResult:
    """One DrumGizmo render of the probe beat, standardised to the 8 channels."""
    wav = tmp_path_factory.mktemp("render") / "drumgizmo_out.wav"
    midi_len = mido.MidiFile(str(probe_midi)).length
    return DrumGizmoRenderer().render(
        kit_path=_KIT_XML,
        midimap_path=_MIDIMAP_XML,
        midi_path=probe_midi,
        wav_path=wav,
        duration_s=midi_len + 5.0,  # tail for cymbal / ambience decay
        channel_map=DRSKIT_MULTITRACK8,
    )


def test_drumgizmo_render_sample_rate_is_44100(rendered: RenderResult) -> None:
    """Rendered WAV is 44.1 kHz (F0-T2a §1.1 — no resampling)."""
    assert rendered.sample_rate == 44100
    assert rendered.n_frames > 0


def test_drumgizmo_render_standardised_to_industry_8(rendered: RenderResult) -> None:
    """The 13-mic kit is selected onto the industry-standard 8 (F0-T2a §2.3)."""
    assert rendered.n_channels == 8
    assert rendered.channel_labels == MIC_CONFIG_CHANNELS[MicConfig.MULTITRACK_FULL]


def test_drumgizmo_engine_faithful_mode_exposes_all_kit_mics(
    probe_midi: Path, tmp_path: Path
) -> None:
    """Without a channel map the render keeps every kit mic (the Pro path)."""
    midi_len = mido.MidiFile(str(probe_midi)).length
    full = DrumGizmoRenderer().render(
        kit_path=_KIT_XML,
        midimap_path=_MIDIMAP_XML,
        midi_path=probe_midi,
        wav_path=tmp_path / "full.wav",
        duration_s=midi_len + 5.0,
    )
    kit_channels = _KIT_XML.read_text(encoding="utf-8").count("<channel ")
    assert kit_channels > 8, "DRSKit must declare more mics than the standard 8"
    assert full.n_channels == kit_channels


def test_drumgizmo_bleed_is_present_falsifiably(rendered: RenderResult) -> None:
    """Bleed is proven by envelope correlation, not eyeballed (§6.3).

    The snare hits land in the dedicated snare mic *and* in the overheads —
    that cross-mic energy is the bleed. The metric is falsifiable: an
    uncorrelated control signal must collapse the correlation to ~0.
    """
    assert rendered.channel_labels is not None
    labels = rendered.channel_labels
    audio, _ = sf.read(str(rendered.wav_path), dtype="float32", always_2d=True)
    snare = audio[:, labels.index("snare")]
    overhead = audio[:, labels.index("oh_L")]

    bleed = _envelope_correlation(snare, overhead)
    rng = np.random.default_rng(0)
    control = _envelope_correlation(snare, rng.standard_normal(len(snare)))

    assert bleed > 0.5, f"snare->overhead bleed too weak: {bleed:.3f}"
    assert control < 0.2, f"uncorrelated control should be ~0, got {control:.3f}"
    assert bleed > control, "bleed must dominate the uncorrelated control"
