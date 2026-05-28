---
title: "F0-T19 — Canonical I/O Mapping Layer (STRP-001)"
id: LIN-DT-F0T19-001
status: LOCKED v1.0.0
created: 2026-05-28
locked: 2026-05-28  # Decision Lock CEO — D1..D12 ratified; AS-IS/TO-BE gate (DRSKit) passed
supersedes_practice: "Plan-A midimap patching (2026-05-25); 'assume-GM-for-all-kits' render path; flat-25 8-bus output taxonomy"
related:
  - F0-T18_MIDI_STANDARD_TRANSLATION_SPEC.md
  - F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md
  - F0-T4a_TCN_TOPOLOGY_SPEC.md
---

# F0-T19 — Canonical I/O Mapping Layer (STRP-001)

> **Thesis (CEO, 2026-05-28).** There are *two* semantic-mapping problems and they
> are the same problem: (1) our training MIDI must be translated *into* each render
> kit's dialect; (2) the network's *output* must be a coherent class vocabulary the
> user can remap onto their kit. Both ride on one shared canonical vocabulary of
> **(class, articulation)**. Stop patching; design the layer organically.

<a id="three-arrows"></a>
## 0. The three arrows

```
        ┌──────────────── ARROW 1 (input, lossless) ────────────────┐
GMD  ───┤  Roland TD-11  ──read──►  CANONICAL (class, articulation)  │
        └────────────────────────────────────────────────────────────┘
                                          │
        ┌──── ARROW 2 (canonical → kit dialect, per kit, for RENDER) ─┐
        │  CANONICAL ──► DrumGizmo instr names | Sfizz keys           │ ──► audio (8-ch, agnostic)
        └────────────────────────────────────────────────────────────┘
                                          │
                                     NEURAL NET
                                          │
        ┌──── ARROW 3 (canonical classes → output MIDI) ─────────────┐
        │  7 type-classes + articulations  ──►  GM-compatible MIDI    │ ──► user remaps to their kit
        └────────────────────────────────────────────────────────────┘
```

**Canonical = Roland TD-11, by convenience (CEO Decision).** The GMD source is
already Roland TD-11, so Arrow 1 is a direct read into the `(class, articulation)`
vocabulary — no input remap. Only Arrow 2 (render-time, per kit) and Arrow 3
(output) are genuine translations.

<a id="two-storture"></a>
### 0.1 The two structural defects this fixes

1. **Arrow 2 missing (input dialect).** The pipeline canonicalised everything to one
   GM note set and sent the *same* MIDI to every kit, assuming all kits speak GM.
   They don't: `vendor/drumgizmo/DRSKit/Midimap_full.xml` wants `closed=56, open=58`;
   `vendor/sfz/big-rusty-drums` declares its own `keymap.sfz` (and ships `default/`
   + `ekit/` layouts). Mismatch → silent drops/phantoms → Plan-A vendor patches
   (`*.orig` backups). The `audit_kit_coherence` probe (2026-05-28) found 4 phantom
   hi-hat articulations on 3 DG kits this way.
2. **Arrow 3 incoherent (output taxonomy).** The `flat-25` target used 8 buses sized
   to mirror the 8 mic channels, mixing two grouping principles: it *split* toms by
   position (rack vs floor on bus 4/5) yet *lumped* crash+china+splash on bus 8; and
   it collapsed **articulation** (snare head 38, rimshot 40, sidestick 37 all → "bus 2
   onset"; ride bow 51 vs bell 53 → "bus 6"). Only hi-hat articulation survived.

<a id="output-taxonomy"></a>
### 0.2 Output taxonomy — 7 type-classes, articulations preserved

**Principle (CEO).** Group by **type** (collapse *physical identity* — which tom,
which crash — not in the audio, user remaps); **preserve articulation** (*how* the
same drum was struck — acoustically real, must be predicted).

| # | class | onset notes (Roland src) | articulation output |
|:--:|:--|:--|:--|
| 1 | kick | 36 | — |
| 2 | snare | 38, 40, 37 | head / rimshot / sidestick |
| 3 | hihat | 22, 42, 26, 46, 44 | closed / open / pedal **+ CC4 continuous openness** |
| 4 | tom | 41,43,45,47,48,50,58 | — (all toms collapsed; no register head — deferred to future models, CEO 2026-05-28) |
| 5 | ride | 51, 59, 53 | bow / bell |
| 6 | crash | 49, 57 | — (all crashes collapsed) |
| 7 | aux | 52, 55 | — (china + splash merged: secondary, 0.74 % of GMD onsets) |

**The "8 in / 7 out" is deliberate, not symmetric.** Input = *up to 8* audio
channels, agnostic to count and order (F0-T4e). Output = 7 semantic classes. The old
"8" coincided with the mic count — that coincidence was the defect. 7 also removes
the in/out ambiguity.

**Output MIDI is its own standard, not Roland.** The net is `audio → classes`; it
cannot reconstruct info absent from the audio (which specific tom). Output is a
**GM-compatible reduced note set** — one default GM note per class (kick 36, snare 38
+rim/sidestick, hihat 42/46/44+CC4, tom 47, ride 51+bell 53, crash 49, aux 55) — so it
plays out-of-the-box on any GM instrument; the user remaps the single tom/crash/aux
note onto their kit's specific pieces. The output map is the mirror of Arrow 2 (same
`(class, articulation)` SSoT) and becomes a configurable preset in the v1.0 plugin.

---

## 1. Competitor & Market Analysis (STRP-001 §1)

- **GM/GM2 percussion** = the interchange lingua franca; exists precisely because
  every instrument has its own native layout.
- **Superior Drummer 3 / EZdrummer / Addictive Drums 2** ship a **MIDI-mapping
  engine** (Roland TD, Yamaha DTX, GM presets) — a CANONICAL↔native translation
  layer, first-class and swappable. Validates Arrows 2 & 3.
- **Academic drum transcription** (MIREX ADT, onsets-and-frames-for-drums) outputs a
  *type* vocabulary (classic KD/SD/HH; extended adds toms/cymbals) — never per-piece
  identity. Validates the 7-class **type** taxonomy and the identity-collapse.

## 2. Open-Source Codebase Analysis (STRP-001 §2)

- **DrumGizmo** separates kit XML (instrument→samples) from **midimap XML**
  (note→instrument), the latter passed per-render (`-m`). Designed for generated
  per-use maps. → Arrow 2 generates a midimap; never patches the vendor's.
- **SFZ / sfizz**: `key`/`lokey`/`hikey` + `#define`/`#include` parametrise the
  layout (Big Rusty Drums: `key=$sncenterkey` from `keymap.sfz`). → Arrow 2 remaps
  MIDI to the keys the `.sfz` declares.
- **mido** (existing dep): deterministic MIDI rewriting for Arrows 1/2/3.

## 3. UX/UI Impact (STRP-001 §3)

Arrow 3 *is* the prototype of the v1.0 plugin's output mapping (input-agnostic
plugin, user picks output target). "Laboratory Precision": every arrow is one
versioned, inspectable YAML; validated by the coherence gate; **fail-loud, never a
silent drop** (the cardinal F0-T18 principle). Collapsing identity is explicit;
preserving articulation is explicit.

## 4. Tech Implementation Matrix (STRP-001 §4) — all Python (F0), off audio thread

| Component | Complexity | Risk |
|:--|:--|:--|
| `kit_dialect_map.yaml` SSoT (canonical→{DG instr | SFZ key}) per kit | Low | authoring × 6 kits |
| DG midimap generator (canonical note → kit instrument) | Low | typos → caught by gate |
| SFZ keymap parser + MIDI remap | Med | `#define`/`#include` edge cases |
| **Output taxonomy redefinition (7 classes + articulations)** | **Med-High** | target tensor `flat-25` → new layout; TCN heads (F0-T4a); re-run mini-L3 |
| `orchestrate` integration + retire Plan-A (`*.orig`) | Low | verify no other consumer |
| Coherence gate acceptance + audio proof | Done/Low | — |

## 5. Decisions for CEO Decision Lock (STRP-001 §5)

**Input / render (Arrows 1–2):**
| # | Decision | Rec |
|:--|:--|:--|
| D1 | Canonical = Roland TD-11 (input read directly into `(class, articulation)`; no input remap) | Yes |
| D2 | DrumGizmo: **generate** per-kit midimap; never patch vendor; restore `*.orig` | Yes |
| D3 | Sfizz: translate by **remapping MIDI** to the `.sfz`'s declared keys | Yes |
| D4 | One versioned `kit_dialect_map.yaml`, authored from kit files, validated by gate | Yes |
| D5 | Missing articulations declared explicitly (`absent`/`substitute`); fail-loud on unmapped | Yes |
| D6 | Scope = all 6 mini-DB kits, both engines | Yes |

**Output (Arrow 3):**
| # | Decision | Rec |
|:--|:--|:--|
| D7 | Output taxonomy = **7 type-classes** (kick, snare, hihat, tom, ride, crash, aux=splash+china) | Yes |
| D8 | **Preserve articulations** within class: snare {head/rim/sidestick}, ride {bow/bell}, hihat continuous openness + pedal | Yes |
| D9 | **Collapse physical identity** (all toms→1, all crashes→1, china+splash→1); **no tom register head** (deferred to future models) | Yes |
| D10 | Output MIDI = GM-compatible reduced set (1 default note/class + articulation notes); output map = mirror of Arrow 2 | Yes |
| D11 | Audio proof = 4–5 varied GMD grooves × 6 kits through new layer + isolated-articulation sweep per kit, as listenable WAVs | Yes |
| D12 | **Velocity contract.** Train target = the MIDI velocity (intent, kit-independent, normalized). Kit-invariance via input level-norm (P1) + gain-aug + cross-kit (measured spread: same velocity → up to 4.5× loudness across kits) → net reads intensity from timbre + relative dynamics. Output = standard MIDI velocity (the user's instrument applies its own curve — nothing to load); optional global Sensitivity/Dynamics trim. The kit velocity curve is the "dynamics dialect", applied at output. | Yes |

## 6. Ripple & cost

`flat-25` (8 bus × 3 + HH) → new layout (7 classes × {onset,vel,microtiming} +
articulation heads + HH continuous). Touches: target builder (`target_builder.py`),
TCN output heads (F0-T4a §3), loss, and re-runs the mini-L3. **All local, $0 Azure,
and pre-F2** — exactly the stortura that is cheap to fix now and expensive after the
burn.

## 7. Docs Update (STRP-001 §6 — post-approval)

Stamp `LOCKED v1.0.0`; add F0-T19 to `MASTER_SCHEDULING.md` §6/§7 as a hard gate of
F2-T1 **and** F2-T3 (the output taxonomy changes the trained model's heads); note it
supersedes Plan-A patching and the flat-25 taxonomy; amend `F0-T4a §3` (output heads)
and `F0-T2a §3.3` (target contract); cross-link from `F0-T18`.
