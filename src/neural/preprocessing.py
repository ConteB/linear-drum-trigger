"""Preprocessing harness — P1 (pre-emphasis + z-score) + P2 (onset envelope).

Implementa il **Decision Lock CEO 2026-05-25** (F0-T4d B1+B2): un layer di
preprocessing DSP-grade davanti alla TCN che de-tona il segnale (P1) e
aggiunge un canale di evidenza onset pre-digerito (P2).

Risponde al fallimento mini-L3 cross-kit ([F0-T4c §6.5](docs/methodology/F0-T4c_DATA_PIPELINE_FIXES_SPEC.md)):
la rete TCN sui timbri fuori distribuzione collassava a "predici onset
ovunque" (Recall ≈ 1.00, Precision ≈ 0.01). Il preprocessing rimuove la
variabilità timbrica (z-score per-canale running) e fornisce un canale
"onset evidence" pre-computato (spectral flux differenziale, classico
MIREX) che la rete può imitare/raffinare.

**Compatibilità RTNeural (F4 plugin C++/JUCE)**:
- P1: biquad 1-pole HP + accumulatori running stats → ~30 LOC C++
- P2: STFT + mel + flux → ~150 LOC C++ (più pesante ma fattibile)

Spec: ``docs/methodology/F0-T4d_PREPROCESSING_HARNESS_AND_AUDIT_SPEC.md``
       ``docs/methodology/F0-T4a_TCN_TOPOLOGY_SPEC.md`` §3.3 (in_channels=9)
"""
from __future__ import annotations

import math

import torch
from torch import nn


#: Default pre-emphasis coefficient — Bock & Schedl 2014, madmom default.
#: y[t] = x[t] − α · x[t−1] → 1-pole HP attenuating DC + sub-bass.
DEFAULT_PRE_EMPHASIS_ALPHA: float = 0.97

#: EMA decay for the running per-channel mean/variance. Higher = slower
#: adaptation but more stable; 0.99 = ~100-step half-life.
DEFAULT_CHANNEL_NORM_DECAY: float = 0.99

#: STFT parameters for the onset envelope — hop=128 matches the encoder
#: stride so the 9th channel is naturally at R_target = 344 Hz (F0-T4a §3).
ONSET_FFT_SIZE: int = 2048
ONSET_HOP_SIZE: int = 128         # = ENCODER_STRIDE
ONSET_N_MELS: int = 80
ONSET_SAMPLE_RATE: int = 44100


class PreEmphasis(nn.Module):
    """1-pole high-pass pre-emphasis filter — `y[t] = x[t] − α · x[t−1]`.

    F0-T4d B1 (Decision Lock CEO 2026-05-25). Standard in onset detection
    literature: attenuates DC + sub-bass rumble that carries no transient
    information, evens out the spectral tilt. Differentiable (1-LOC, no
    learnable params). Replicable in C++ as a biquad section.
    """

    def __init__(self, alpha: float = DEFAULT_PRE_EMPHASIS_ALPHA) -> None:
        super().__init__()
        if not 0.0 <= alpha < 1.0:
            raise ValueError(f"alpha must be in [0, 1), got {alpha}")
        self.alpha = float(alpha)
        # Register as buffer so it moves with .to(device) but stays non-trainable.
        self.register_buffer(
            "_alpha", torch.tensor(self.alpha, dtype=torch.float32), persistent=False,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Apply pre-emphasis along the last dimension (time).

        Args:
            x: ``[..., T]`` audio tensor.
        Returns:
            ``[..., T]`` filtered tensor — same shape, same dtype, same device.
        """
        if x.shape[-1] < 2:
            return x
        # y[t] = x[t] − α · x[t−1]; pad first sample with zero (causal).
        prev = torch.cat(
            [torch.zeros_like(x[..., :1]), x[..., :-1]], dim=-1,
        )
        return x - self._alpha.to(x.dtype) * prev


class ChannelNorm(nn.Module):
    """Running per-channel z-score normalization (EMA running mean/var).

    F0-T4d B1 (Decision Lock CEO 2026-05-25). For each channel keeps an
    exponential moving average of mean and variance; at training time the
    EMA is updated; at eval time the stored EMA is used. Removes loudness
    and DC bias per channel, leaving the transient morphology intact.

    Reference: ADTOF (Zehren 2021) data pipeline, BatchNorm-with-running-stats
    flavour but per-channel only (no normalization across time within a
    batch — would destroy the cross-sample variance signal).
    """

    def __init__(
        self,
        num_channels: int,
        decay: float = DEFAULT_CHANNEL_NORM_DECAY,
        eps: float = 1e-5,
    ) -> None:
        super().__init__()
        if num_channels <= 0:
            raise ValueError(f"num_channels must be > 0, got {num_channels}")
        if not 0.0 < decay < 1.0:
            raise ValueError(f"decay must be in (0, 1), got {decay}")
        self.num_channels = num_channels
        self.decay = float(decay)
        self.eps = float(eps)
        # Initialise running stats to neutral (mean=0, var=1).
        self.register_buffer(
            "running_mean", torch.zeros(num_channels), persistent=True,
        )
        self.register_buffer(
            "running_var", torch.ones(num_channels), persistent=True,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Normalize ``[B, C, T]`` tensor per-channel using running stats.

        At training time updates the EMA from this batch's per-channel
        mean/var (averaged across batch and time). At eval uses the stored
        values verbatim.
        """
        if x.dim() != 3:
            raise ValueError(f"ChannelNorm expects [B, C, T], got {tuple(x.shape)}")
        if x.shape[1] != self.num_channels:
            raise ValueError(
                f"ChannelNorm channels mismatch: expected {self.num_channels}, "
                f"got {x.shape[1]}"
            )
        if self.training:
            # Compute per-channel stats over (batch, time) — keep channel dim.
            with torch.no_grad():
                m = x.mean(dim=(0, 2))                 # [C]
                v = x.var(dim=(0, 2), unbiased=False)  # [C]
                self.running_mean.mul_(self.decay).add_(m, alpha=1.0 - self.decay)
                self.running_var.mul_(self.decay).add_(v, alpha=1.0 - self.decay)
        # Use running stats for the actual normalization (train AND eval) — this
        # is the standard "BatchNorm running-stats only" pattern; gives
        # deterministic output that does NOT depend on the batch composition.
        mean = self.running_mean.to(x.dtype).view(1, -1, 1)
        std = (self.running_var + self.eps).sqrt().to(x.dtype).view(1, -1, 1)
        return (x - mean) / std


class OnsetEnvelope(nn.Module):
    """Spectral-flux onset envelope as an additional input channel (P2).

    F0-T4d B2 (Decision Lock CEO 2026-05-25). Computes the classic MIREX
    onset envelope per Bock & Schedl / madmom:

        1. STFT (n_fft=2048, hop=128 == ENCODER_STRIDE) on a per-sample basis
           — averaged across the 8 mic channels to get a single mono envelope.
        2. Magnitude → mel-band reduction (80 bands).
        3. log1p compression.
        4. Half-wave-rectified differential along time (positive spectral flux).
        5. Sum over mel bands → 1 scalar per frame.
        6. Min-max normalize to ``[0, 1]`` per-sample.
        7. Nearest-neighbour repeat ×128 to bring it back to audio sample rate
           so it can concat as the 9th channel of ``[B, 8, n_sample]`` audio.

    Output: ``[B, 1, n_sample]`` — concatenable along dim=1 with the 8 mic
    channels to form ``[B, 9, n_sample]`` input to the TCN (F0-T4a §3.3
    amendment).

    The envelope is the same signal the TCN tries to learn from scratch on
    the onset head — pre-providing it gives the model a strong inductive bias
    that survives cross-kit timbral changes (flux is a property of the
    transient, not the timbre).
    """

    def __init__(
        self,
        n_fft: int = ONSET_FFT_SIZE,
        hop_size: int = ONSET_HOP_SIZE,
        n_mels: int = ONSET_N_MELS,
        sample_rate: int = ONSET_SAMPLE_RATE,
    ) -> None:
        super().__init__()
        self.n_fft = int(n_fft)
        self.hop_size = int(hop_size)
        self.n_mels = int(n_mels)
        self.sample_rate = int(sample_rate)
        # Pre-compute the mel filterbank and Hann window as buffers (move
        # automatically with .to(device), are not learnable).
        self.register_buffer(
            "_window", torch.hann_window(self.n_fft, periodic=True), persistent=False,
        )
        mel_fb = _make_mel_filterbank(
            n_freqs=self.n_fft // 2 + 1,
            n_mels=self.n_mels,
            sample_rate=self.sample_rate,
        )
        self.register_buffer("_mel_fb", mel_fb, persistent=False)

    def forward(self, audio: torch.Tensor) -> torch.Tensor:
        """Compute the onset envelope from a multi-mic audio tensor.

        Args:
            audio: ``[B, n_mic, n_sample]`` audio. Channels are averaged
                (mean) to produce a mono signal before STFT — the onset
                event is the same across mics modulo phase, the average
                attenuates incoherent noise.

        Returns:
            ``[B, 1, n_sample]`` envelope at audio sample rate (NN-repeat
            of the frame-rate envelope). Values in ``[0, 1]`` per-sample.
        """
        if audio.dim() != 3:
            raise ValueError(f"OnsetEnvelope expects [B, C, T], got {tuple(audio.shape)}")
        B, C, T = audio.shape  # noqa: N806
        if T < self.n_fft:
            # Sample too short — return zeros (the encoder padding will
            # absorb; this preserves shape contract).
            return torch.zeros(B, 1, T, device=audio.device, dtype=audio.dtype)

        # 1. Average across mic channels → mono [B, T].
        mono = audio.mean(dim=1)
        # 2. STFT — centered=True so frame[i] covers samples [i*hop − n_fft/2,
        #    i*hop + n_fft/2). Output shape [B, n_freqs, n_frames].
        spec = torch.stft(
            mono,
            n_fft=self.n_fft,
            hop_length=self.hop_size,
            win_length=self.n_fft,
            window=self._window.to(mono.dtype),
            center=True,
            return_complex=True,
        )
        mag = spec.abs()                                  # [B, n_freqs, n_frames]
        # 3. Mel reduction → [B, n_mels, n_frames].
        mel = torch.einsum("bft,mf->bmt", mag, self._mel_fb.to(mag.dtype))
        # 4. log1p compression.
        log_mel = torch.log1p(mel)
        # 5. Half-wave-rectified differential along time.
        flux = torch.clamp_min(log_mel[..., 1:] - log_mel[..., :-1], 0.0)
        # Pad first frame with zero so shape stays [B, n_mels, n_frames].
        flux = torch.cat([torch.zeros_like(flux[..., :1]), flux], dim=-1)
        # 6. Sum across mel bands → [B, n_frames].
        env_frames = flux.sum(dim=1)
        # 7. Per-sample min-max normalize to [0, 1].
        emin = env_frames.amin(dim=-1, keepdim=True)
        emax = env_frames.amax(dim=-1, keepdim=True)
        env_frames = (env_frames - emin) / (emax - emin + 1e-9)
        # 8. NN-repeat ×hop to bring to audio sample rate → [B, 1, T'].
        env_samples = env_frames.unsqueeze(1).repeat_interleave(self.hop_size, dim=-1)
        # Pad/crop to match T exactly (STFT center=True introduces ±n_fft/2 padding).
        if env_samples.shape[-1] >= T:
            env_samples = env_samples[..., :T]
        else:
            pad = T - env_samples.shape[-1]
            env_samples = torch.cat(
                [env_samples, env_samples[..., -1:].repeat_interleave(pad, dim=-1)],
                dim=-1,
            )
        return env_samples


class PreprocessingFrontend(nn.Module):
    """Full F0-T4d preprocessing harness: P1 + P2 + concat.

    Composes:
        1. P1 PreEmphasis on the 8 mic channels (no preprocessing on the
           onset envelope, which is already band-limited).
        2. P2 OnsetEnvelope → 1 mono channel from the 8 mic input.
        3. Concat along channel dim → ``[B, 9, T]``.
        4. ChannelNorm on all 9 channels with running stats.

    Output shape: ``[B, 9, T]`` — feeds directly into the TCN's
    Input-Agnostic Projection (Conv1d k=1, in=9 → out=C).
    """

    def __init__(
        self,
        n_mic: int = 8,
        pre_emphasis_alpha: float = DEFAULT_PRE_EMPHASIS_ALPHA,
        channel_norm_decay: float = DEFAULT_CHANNEL_NORM_DECAY,
        onset_envelope: bool = True,
    ) -> None:
        super().__init__()
        self.n_mic = int(n_mic)
        self.use_onset_envelope = bool(onset_envelope)
        self.pre_emphasis = PreEmphasis(alpha=pre_emphasis_alpha)
        if self.use_onset_envelope:
            self.onset_envelope = OnsetEnvelope()
            total_channels = self.n_mic + 1
        else:
            self.onset_envelope = None  # type: ignore[assignment]
            total_channels = self.n_mic
        self.channel_norm = ChannelNorm(
            num_channels=total_channels, decay=channel_norm_decay,
        )
        self.total_channels = total_channels

    def forward(self, audio: torch.Tensor) -> torch.Tensor:
        """Apply the full pipeline. Input/output shape contract:

        Input:  ``[B, n_mic, T]`` (typically n_mic=8)
        Output: ``[B, n_mic+1, T]`` if onset_envelope=True else ``[B, n_mic, T]``
        """
        if audio.dim() != 3:
            raise ValueError(f"PreprocessingFrontend expects [B, C, T], got {tuple(audio.shape)}")
        if audio.shape[1] != self.n_mic:
            raise ValueError(
                f"PreprocessingFrontend: expected n_mic={self.n_mic} input channels, "
                f"got {audio.shape[1]}"
            )
        # P1: pre-emphasis on the 8 mic channels only.
        mics = self.pre_emphasis(audio)
        # P2: onset envelope from the ORIGINAL audio (not pre-emphasised —
        # the envelope is a property of the spectral flux of the raw signal).
        if self.use_onset_envelope:
            env = self.onset_envelope(audio)  # [B, 1, T]
            combined = torch.cat([mics, env], dim=1)  # [B, n_mic+1, T]
        else:
            combined = mics
        # ChannelNorm on the full stack (running stats).
        return self.channel_norm(combined)


# ----------------------------------------------------------------------------
# Helper: mel filterbank (replicates torchaudio.functional.melscale_fbanks
# behaviour with a small footprint — avoids any version dependency).
# ----------------------------------------------------------------------------


def _hz_to_mel(hz: torch.Tensor | float) -> torch.Tensor:
    """Slaney mel scale (matches librosa default)."""
    f = torch.as_tensor(hz, dtype=torch.float32)
    return 2595.0 * torch.log10(1.0 + f / 700.0)


def _mel_to_hz(mel: torch.Tensor) -> torch.Tensor:
    return 700.0 * (torch.pow(10.0, mel / 2595.0) - 1.0)


def _make_mel_filterbank(
    n_freqs: int,
    n_mels: int,
    sample_rate: int,
    f_min: float = 0.0,
    f_max: float | None = None,
) -> torch.Tensor:
    """Build a triangular mel filterbank ``[n_mels, n_freqs]``.

    Replicates ``torchaudio.functional.melscale_fbanks`` (HTK = False, i.e.
    Slaney) with no version-specific dependencies.
    """
    fmax = float(f_max) if f_max is not None else sample_rate / 2.0
    fft_freqs = torch.linspace(0.0, sample_rate / 2.0, n_freqs)
    mel_min = _hz_to_mel(f_min).item()
    mel_max = _hz_to_mel(fmax).item()
    mel_pts = torch.linspace(mel_min, mel_max, n_mels + 2)
    hz_pts = _mel_to_hz(mel_pts)
    fb = torch.zeros(n_mels, n_freqs)
    for m in range(n_mels):
        f_low, f_ctr, f_hi = hz_pts[m], hz_pts[m + 1], hz_pts[m + 2]
        # Left slope
        left = (fft_freqs - f_low) / (f_ctr - f_low + 1e-12)
        # Right slope
        right = (f_hi - fft_freqs) / (f_hi - f_ctr + 1e-12)
        tri = torch.clamp_min(torch.minimum(left, right), 0.0)
        # Slaney normalize: divide by triangle area so each filter has unit weight.
        norm = 2.0 / (f_hi - f_low + 1e-12)
        fb[m] = tri * norm
    return fb


__all__ = [
    "DEFAULT_CHANNEL_NORM_DECAY",
    "DEFAULT_PRE_EMPHASIS_ALPHA",
    "ONSET_FFT_SIZE",
    "ONSET_HOP_SIZE",
    "ONSET_N_MELS",
    "ONSET_SAMPLE_RATE",
    "ChannelNorm",
    "OnsetEnvelope",
    "PreEmphasis",
    "PreprocessingFrontend",
]
