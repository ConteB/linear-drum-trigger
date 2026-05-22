---
title: L2 Ocular Proof — inspection 2026-05-23
owner: F0-T3
date: 2026-05-23
scope: F0
status: APPROVED
---

# Gate L2 — Ocular Proof (2026-05-23)

Gate `L2` per `F0-T3`: ispezione manuale del mini-batch Gold prodotto
da `tools/run_mini_batch.py` (F0-T2e). DoD del task — checklist firmata e
registrata in [`REGISTRO_AVANZAMENTO.md`](../../../04_INTELLIGENCE/REGISTRO_AVANZAMENTO.md).

## Campioni ispezionati

| # | Engine | Sample key | mic | durata | drift max | bleed max off-diag |
| :-- | :-- | :-- | :--: | :--: | :--: | :--: |
| 1 | `sfizz` | `GMD001-V0T0-SFZ-R0-L1-NONE` | 2 | 8.61 s | 2.90 ms | +1.00 |
| 2 | `drumgizmo` | `GMD000-V0T0-DGZ-R0-L1-NONE` | 8 | 10.10 s | 0.00 ms | +0.99 |

## Checklist L2

*Per ogni campione vai al PNG e al `.integrity.txt` corrispondenti e firma.*

### Campione 1 — `GMD001-V0T0-SFZ-R0-L1-NONE` (sfizz)

- Waveform multi-mic: `GMD001-V0T0-SFZ-R0-L1-NONE.waveform.png`
- Target piano-roll:  `GMD001-V0T0-SFZ-R0-L1-NONE.target.png`
- Integrity report:   `GMD001-V0T0-SFZ-R0-L1-NONE.integrity.txt`

- [x] **Waveform multi-mic coerente** (nessun canale silenzioso ingiustificato; ampiezze in range; nessun click anomalo).
- [x] **Allineamento target ↔ MIDI ±3 ms** (39 / 39 onsets entro tolleranza; drift max 2.90 ms).
- [x] **Integrità FP16** (nessun NaN/inf, peak ∈ (0,1], onset/HH in [0,1] — vedi `.integrity.txt`).
- [x] **DNA-Trace lineage** (audio/target shape match; sha256 presenti; recipe_sha256 traccia la lineage — vedi `.integrity.txt`).
- [x] **Bleed multi-mic — N/A per Sfizz.** Il `mic_config: solo_stereo` è una sola sorgente duplicata su L/R, quindi la correlazione +1.00 è attesa e *non* è bleed multi-mic. La falsificazione del bleed è valutata sul campione DrumGizmo (campione 2).

### Campione 2 — `GMD000-V0T0-DGZ-R0-L1-NONE` (drumgizmo)

- Waveform multi-mic: `GMD000-V0T0-DGZ-R0-L1-NONE.waveform.png`
- Target piano-roll:  `GMD000-V0T0-DGZ-R0-L1-NONE.target.png`
- Integrity report:   `GMD000-V0T0-DGZ-R0-L1-NONE.integrity.txt`

- [x] **Waveform multi-mic coerente** (nessun canale silenzioso ingiustificato; ampiezze in range; nessun click anomalo).
- [x] **Allineamento target ↔ MIDI ±3 ms** (26 / 26 onsets entro tolleranza; drift max 0.00 ms).
- [x] **Integrità FP16** (nessun NaN/inf, peak ∈ (0,1], onset/HH in [0,1] — vedi `.integrity.txt`).
- [x] **DNA-Trace lineage** (audio/target shape match; sha256 presenti; recipe_sha256 traccia la lineage — vedi `.integrity.txt`).
- [x] **Bleed multi-mic** falsificabile via envelope-RMS correlation: off-diagonal max **+0.99** → bleed **presente**.

## Evidenza accessoria (non-bloccante per L2, utile a CP-1)

Calibrazione di throughput del render (locale, €0) — `tools/calibrate_render.py`:

| Engine | platform | render factor | bytes/sample | bytes/s wall |
| :-- | :-- | :--: | :--: | :--: |
| `sfizz`     | macOS arm64 (Mac M5)     | 0.03× | 1.15 MB | 5.62 MB/s |
| `drumgizmo` | Linux arm64 (OrbStack)   | 0.12× | 5.85 MB | 5.58 MB/s |

CSV grezzi committati come evidenza: [`sfizz.csv`](sfizz.csv) · [`drumgizmo.csv`](drumgizmo.csv).

Proiezione su 1.5 TB Gold (single-thread, ARM) — ordine di grandezza:

| Cores ideali | wall-clock |
| :--: | :--: |
| 1   | ~3.2 d |
| 8   | ~9.7 h |
| 16  | ~4.9 h |
| 32  | ~2.4 h |
| 64  | ~1.2 h |

**Caveat onesto:** misurata su 12 grooves sintetici brevi (~7-10 s) con un solo
kit per engine; il roster F0-T1b ha 11 kit e i grooves reali di GMD/E-GMD sono
più lunghi e densi. La cifra serve a dimensionare F1-T1 (taglia VM Azure), non
a impegnare il preventivo della spesa F2-T1.

## Decisione del CEO

- [x] **L2 SUPERATO** — sblocca lo spend RENDER (F1 + F2-T1).
- [ ] **L2 NON SUPERATO** — annotare causa e ri-pianificare F0-T2 a valle.

**Data firma:** **2026-05-23**  **Firma CEO:** **Decision Lock CEO — L2 superato**

Tracciato in [`REGISTRO_AVANZAMENTO.md`](../../../04_INTELLIGENCE/REGISTRO_AVANZAMENTO.md) come `F0-T3`
COMPLETATO. Sblocca **F1-T1** (Setup Azure) e **F2-T1** (Render Gold 1.5 TB).
