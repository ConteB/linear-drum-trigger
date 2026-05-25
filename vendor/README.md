# Vendored assets — render toolchain & drum kits

Asset vendorizzati per **`ENGINEERING_STANDARDS §4`**: copia locale dei binari di
render e delle librerie di campioni (SFZ + kit DrumGizmo), così la sparizione di un
repository a monte non rende il dataset Gold non riproducibile.

I binari pesanti sono **git-ignored** (vedi `/.gitignore`). Questo manifest è il record
di re-fetch: chiunque (sviluppatore locale, VM Azure di F2-T1, futuro maintainer) può
ricostruire `vendor/` dagli URL + checksum qui sotto.

**Roster operativo (`F0-T1b` v1.1):** 10 kit di batteria (5 DrumGizmo CC-BY-4.0 + 5 SFZ
CC0). Salamander Drumkit (CC-BY-**SA**-3.0, ShareAlike) e Sommerhack 2016-Kit (non più
sul wiki drumgizmo.org) **esclusi** all'amendment 2026-05-23 — vedi
[`docs/compliance/F0-T1b_KIT_ROSTER_SURVEY.md` §8](../docs/compliance/F0-T1b_KIT_ROSTER_SURVEY.md#).

**Partizione train/val** (Decision Lock CEO 2026-05-23 — Opzione B,
[`DOSSIER §10.2`](../docs/methodology/DOSSIER_TECNICO.md#validation-set)):
8 kit nel training, **ShittyKit + Swirly Drums** tenuti vergini per il Val Gold.

**Stato locale:**

| Marker | Significato |
| :-- | :-- |
| 📦 **localmente vendorizzato** | Estratto in `vendor/` su questo Mac → smoke test render disponibile |
| 🌐 **manifest-only** | sha256 verificato in streaming (zero disco locale); sarà scaricato su VM Azure al provisioning F2-T1 (sotto-task T1-prep-D) |

---

## Render toolchain

### `vendor/sfizz/` — CLI di rendering Sfizz

| Campo | Valore |
| :-- | :-- |
| Binario | `sfizz_render` (+ man page `sfizz_render.1`) |
| Versione | sfizz **1.2.3** |
| Sorgente | `https://github.com/sfztools/sfizz/releases/download/1.2.3/sfizz-1.2.3-macos.tar.gz` |
| Licenza | BSD-2-Clause (sfizz) |
| Architettura | x86_64 — eseguibile autonomo (solo system libs); gira sotto **Rosetta 2** su Apple Silicon |
| sha256 (`sfizz_render`) | `db3e788ed38a96d9fb866081215b08b1a195c1068d52700ae8794da064c4a6a5` |

### `drumgizmo` — CLI di rendering DrumGizmo

| Campo | Valore |
| :-- | :-- |
| Binario | `drumgizmo` (CLI) |
| Versione | DrumGizmo **0.9.20** (`0.9.20-3build3`) |
| Provisioning | **apt** nella VM OrbStack `ubuntu` — `apt-get install drumgizmo` |
| Licenza | LGPL-3.0 (DrumGizmo) |
| Architettura | arm64 (VM Linux) |

A differenza di Sfizz, DrumGizmo non ha un prebuilt macOS. Gira su **Linux** — parità
d'ambiente col render F2 su Azure — provisionato via `apt` (versione pinnata sopra).
L'adapter `DrumGizmoRenderer` lo risolve su `PATH`; gli oracoli §6.3 skippano dove il
binario è assente (host macOS) e girano dentro OrbStack.

---

## Kit SFZ — Sfizz

### `vendor/sfz/frankensnare/` 📦 **localmente vendorizzato**

| Campo | Valore |
| :-- | :-- |
| Kit | Karoryfer — **Frankensnare v2.100** |
| Sorgente | `https://github.com/sfzinstruments/karoryfer.frankensnare/releases/download/v2.100/Frankensnare_2100.zip` |
| Licenza | **CC0-1.0** (public domain — nessuna attribuzione richiesta) |
| sha256 (zip) | `03defbfbc5232a5eafa69e839e43b33f8e0746ea9a098fc2b4f411e8112a732a` |
| Contenuto | 309 file `.sfz` (`Programs/`), `Samples/`, `Presets/` — snare su GM key **38** |
| Ruolo | Varietà snare; kit di sviluppo F0-T2b · Train Gold |

### `vendor/sfz/unruly-drums/` 📦 **localmente vendorizzato**

| Campo | Valore |
| :-- | :-- |
| Kit | Karoryfer — **Unruly Drums v1.100** |
| Sorgente | `https://github.com/sfzinstruments/karoryfer.unruly-drums/releases/download/v1.100/Unruly_Drums_1100.zip` |
| Licenza | **CC0-1.0** |
| sha256 (zip, 645 MB) | `8d8d8075570088658cfce5de6cc6df1fa1340cac9ec808da130e19b1463b1f90` |
| Contenuto | `Programs/01-kit-sticks.sfz`, `02-kit-brushes.sfz`, `03-kit-complete.sfz`, `04-kick.sfz`, kit dispatcher · `Samples/`, 10 round-robin |
| Ruolo | Kit batteria multi-mic completo · Train Gold |

### `vendor/sfz/big-rusty-drums/` 📦 **localmente vendorizzato**

| Campo | Valore |
| :-- | :-- |
| Kit | Karoryfer — **Big Rusty Drums v1.100** |
| Sorgente | `https://github.com/sfzinstruments/karoryfer.big-rusty-drums/releases/download/v1.100/Big_Rusty_Drums_1100.zip` |
| Licenza | **CC0-1.0** |
| sha256 (zip, 591 MB) | `d4a9990acd19376d91ce446dae415c81428728b5adebb6a88eddbb3a6aac8744` |
| Contenuto | `Programs/01-full.sfz`, `02-basic.sfz`, kick/snare alternates · `Samples/`, drumkit vintage rusty timbre |
| Ruolo | Kit batteria vintage (timbro distinto da Unruly/Frankensnare) · Train Gold |

### `vendor/sfz/swirly-drums/` 🌐 **manifest-only**

| Campo | Valore |
| :-- | :-- |
| Kit | Karoryfer — **Swirly Drums v1.104** |
| Sorgente | `https://github.com/sfzinstruments/karoryfer.swirly-drums/releases/download/v1.104/Swirly.Drums_1104.zip` |
| Licenza | **CC0-1.0** |
| sha256 (zip, 828 MB) | `c709acc76260e559d8fd542d2c92b0ec6e3d507efc20fbb5d213427c49fb474a` |
| Ruolo | **Val Gold (kit "vergine")** — Decision Lock CEO 2026-05-23 Opzione B · timbro atmospheric/effettato, fuori standard rispetto al training |
| Provisioning | da scaricare su VM Azure in T1-prep-D (zero disco locale) |

### `vendor/sfz/vsco-2-ce/` 📦 **localmente vendorizzato**

| Campo | Valore |
| :-- | :-- |
| Kit | **VSCO-2 Community Edition v1.1.0** (Versilian Studios Chamber Orchestra) |
| Sorgente | `https://github.com/sgossner/VSCO-2-CE/archive/refs/tags/1.1.0.zip` (source archive — repo completo) |
| Licenza | **CC0-1.0** |
| sha256 (zip, 2.30 GB) | `4a4446628df0e1a12aaee58e9f65f8fa7cde51971e961abb1b43083a6d3a8ab7` |
| Contenuto | Orchestra completa; per il progetto Drum Trigger interessano `Percussion/`, `VSCO 1 Percussion/`, `GM-StylePerc.sfz` |
| Ruolo | Percussioni accessorie sintetiche ([`DOSSIER §3.4`](../docs/methodology/DOSSIER_TECNICO.md#aug-l3)) · Train Gold |

---

## ⚠️ Midimap patches — Decision Lock CEO 2026-05-25 (Plan A)

I 5 kit DrumGizmo del mini-L3 hanno avuto i loro `midimap.xml` patchati per coprire note GM mancanti e correggere mappature semantically wrong. **Causa root**: il listening test del 2026-05-25 ha mostrato che ~9.2 % degli onset target del mini-L3 erano "fantasma" (target dice "TOM!" ma audio silente). Si veda `docs/gates/F0-T4c_MINI_L3/LOSS_COMPETITION_2026-05-25.md` (addendum Plan A) e l'audit JSON in `docs/gates/F0-T4c_MINI_L3/kitaware_audit_2026-05-25.json`.

**11 patches applicate** (tool `tools/patch_midimaps.py`, idempotente; backup `*.orig` preservato):

| Kit | Patch applicate |
| :-- | :-- |
| DRSKit | + GM 48 → `Tom1`, + GM 50 → `Tom1`, + GM 45 → `Tom2` |
| MuldjordKit3 | + GM 50 → `Tom1`, + GM 43 → `Tom4` |
| CrocellKit | + GM 50 → `Tom1`, + GM 45 → `Tom2` |
| Aasimonster | ~ GM 50: `crash1_stop` → `tom_1`; ~ GM 41: `hihat_closed2` → `tom_4` |
| ShittyKit | + GM 48 → `Tom-RH`, + GM 50 → `Tom-RH` |

**Per F2-T1**: questi patches devono essere applicati a ogni kit del render Azure 1.5 TB (provisioning automatico via `tools/patch_midimaps.py` come step pre-render). Altrimenti il bug "tom-fantasma" si riproduce a scala 1000×.

---

## Kit DrumGizmo (multi-mic)

### `vendor/drumgizmo/DRSKit/` 📦 **localmente vendorizzato**

| Campo | Valore |
| :-- | :-- |
| Kit | DrumGizmo — **DRSKit v2.1** |
| Sorgente | `https://drumgizmo.org/kits/DRSKit/DRSKit2_1.zip` |
| Licenza | **CC-BY-4.0** (uso commerciale con attribuzione) |
| sha256 (zip, 2.6 GB) | `529f2dcad836593167d0cab218f125f591cd71199748fa681e05e3866667f090` |
| md5 (zip) | `8c4d4b61ad9d354b3b845edd5da9c133` (fonte: drumgizmo.org) |
| Contenuto | kit XML (`DRSKit_full/basic/minimal/no_whiskers`) + midimap (`Midimap_<variant>.xml`) + `Samples/` |
| Canali mic | **13** — AmbL/R, Kdrum back/front, Hihat, OHL/R, Ride, Snare top/bottom, Tom1-3 |
| Ruolo | Kit di sviluppo F0-T2c · Train Gold |

### `vendor/drumgizmo/MuldjordKit3/` 📦 **localmente vendorizzato**

| Campo | Valore |
| :-- | :-- |
| Kit | DrumGizmo — **MuldjordKit v3** (Tama Superstar moderno) |
| Sorgente | `https://drumgizmo.org/kits/MuldjordKit/MuldjordKit3.zip` |
| Licenza | **CC-BY-4.0** — attribution: *"Drum samples provided by DrumGizmo.org"* |
| sha256 (zip, 2.42 GB) | `db94f910913185ee17c5abb77d285a27476dee979db0ccebdc7ed68404514c96` |
| md5 (zip) | `8a66a3e90bbf15687b2d34fd355024f2` (fonte: drumgizmo.org) |
| Contenuto | `MuldjordKit3.xml` (kit principale, **non variant-suffixed**) + `Midimap.xml` singolo + `Samples/` |
| Ruolo | Kit Tama Superstar moderno (timbro production-grade) · Train Gold |
| ⚠️ Nota integrazione | Convenzione di naming `Midimap.xml` (no variant suffix) — `DrumGizmoRenderer._resolve_drumgizmo_midimap` va esteso in T1-prep-A per supportare entrambe le convenzioni (`Midimap_<variant>.xml` per DRSKit, `Midimap.xml` per MuldjordKit). |

### `vendor/drumgizmo/CrocellKit/` 📦 **localmente vendorizzato** (2026-05-25)

| Campo | Valore |
| :-- | :-- |
| Kit | DrumGizmo — **CrocellKit v1.1** |
| Sorgente | `https://drumgizmo.org/kits/CrocellKit/CrocellKit1_1.zip` |
| Licenza | **CC-BY-4.0** |
| Size zip | 5.5 GB (`Content-Length: 5646502341` su nginx drumgizmo.org) |
| sha256 (zip) | `341d1f23e5867fd9d465bbcf3e4cd2f805bb7d7c4f519ba9ec73daae8161d5c6` *(re-computed 2026-05-25; il valore precedente nel manifest era stale)* |
| Entrypoint XML | `vendor/drumgizmo/CrocellKit/CrocellKit_full.xml` |
| Size estratto | 8.4 GB |
| Ruolo | Kit DrumGizmo grande, multi-mic ricchi · **Train Gold + mini-L3 cross-kit train** (Decision Lock CEO 2026-05-24) |
| Provisioning | localmente sul Mac del CEO 2026-05-25 (mini-L3) + ri-scaricabile su VM Azure in T1-prep-D |
| Mappatura mic | `docs/specs/kit_mic_mapping.yaml` (CrocellKit entry: kick=KDrumInside, snare=SnareTop, hihat=Hihat, tom=Tom1, floor=FTom1, OH=OHLeft/OHRight, room=AmbLeft) |

### `vendor/drumgizmo/Aasimonster/` 📦 **localmente vendorizzato** (2026-05-25)

| Campo | Valore |
| :-- | :-- |
| Kit | DrumGizmo — **The Aasimonster v2.1** |
| Sorgente | `https://drumgizmo.org/kits/Aasimonster/aasimonster2_1.zip` |
| Licenza | **CC-BY-4.0** |
| Size zip | 2.3 GB (`Content-Length: 2416291882` · `Last-Modified: 2018-11-28T18:13:25Z`) |
| md5 (zip) | `910aa5a789d34f85c2e7c4a5c5a6b2f9` *(verificato sul download canonical 2026-05-25)* |
| sha256 (zip) | `e0eb6337dae3602c8a4f735e6b5245cf35e1e4909242cfaf5517eb2d725207df` *(re-computed 2026-05-25; il valore precedente nel manifest era stale — il file su drumgizmo.org è datato 2018-11-28, mai cambiato, l'hash storico era stato annotato senza re-compute)* |
| Entrypoint XML | `vendor/drumgizmo/Aasimonster/aasimonster.xml` |
| n. mic | 16 (8 selezionati: KdrumL/Snare_top/Hihat/Tom1/Tom4/OHL/OHR/AmbL — vedi `docs/specs/kit_mic_mapping.yaml`) |
| Ruolo | Kit DrumGizmo multi-mic, timbro distinto · Train Gold + **mini-L3 cross-kit expansion** (Decision Lock CEO 2026-05-25) |
| Provisioning | localmente sul Mac del CEO 2026-05-25 (mini-L3 4° DG train kit) + ri-scaricabile su VM Azure in T1-prep-D |

### `vendor/drumgizmo/ShittyKit/` 📦 **localmente vendorizzato** (2026-05-24)

| Campo | Valore |
| :-- | :-- |
| Kit | DrumGizmo — **ShittyKit v1.2** |
| Sorgente | `https://drumgizmo.org/kits/ShittyKit/ShittyKit1_2.zip` |
| Licenza | **CC-BY-4.0** |
| Size zip | 353 MB (`Content-Length: 369655148` su nginx drumgizmo.org) |
| md5 (zip) | `cbab008a3a4413c6e85b1439d36fe63f` *(MATCH con fonte drumgizmo.org — verificato 2026-05-24)* |
| sha256 (zip) | `acf7c4b0fb01b9c764dca176a3603c25cd9685e5e82a5f7119d16cec7e7af807` *(re-computed 2026-05-24; il valore precedente nel manifest era stale)* |
| Entrypoint XML | `vendor/drumgizmo/ShittyKit/ShittyKit.xml` |
| Ruolo | **Val Gold (kit "vergine")** — Decision Lock CEO 2026-05-23 Opzione B + **mini-L3 cross-kit val** (Decision Lock CEO 2026-05-24) · timbro lo-fi/vintage, fuori standard rispetto al training |
| Provisioning | localmente sul Mac del CEO 2026-05-24 (mini-L3) + ri-scaricabile su VM Azure in T1-prep-D |
| Nota | Usa formato drumkit più datato (velocity-group fissi), ma compatibile con DrumGizmo 0.9.20 |

---

## Riepilogo manifest

| # | Kit | Engine | Licenza | sha256 (zip) | Stato locale | Split |
| --: | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | Frankensnare v2.100 | Sfizz | CC0 | `03defbfb…2a732a` | 📦 | Train |
| 2 | Unruly Drums v1.100 | Sfizz | CC0 | `8d8d8075…3b1f90` | 📦 | Train |
| 3 | Big Rusty Drums v1.100 | Sfizz | CC0 | `d4a9990a…aac8744` | 📦 | Train |
| 4 | Swirly Drums v1.104 | Sfizz | CC0 | `c709acc7…9fb474a` | 🌐 | **Val** |
| 5 | VSCO-2 CE v1.1.0 | Sfizz | CC0 | `4a444662…3a8ab7` | 📦 | Train (accessorie) |
| 6 | DRSKit v2.1 | DrumGizmo | CC-BY-4.0 | `529f2dca…667f090` | 📦 | Train |
| 7 | MuldjordKit v3 | DrumGizmo | CC-BY-4.0 | `db94f910…4514c96` | 📦 | Train |
| 8 | CrocellKit v1.1 | DrumGizmo | CC-BY-4.0 | `65d6f3aa…77813d` | 🌐 | Train |
| 9 | Aasimonster v2.1 | DrumGizmo | CC-BY-4.0 | `cdbaf1ca…070f987` | 🌐 | Train |
| 10 | ShittyKit v1.2 | DrumGizmo | CC-BY-4.0 | `383673954af9…afd77` | 🌐 | **Val** |

**Volume locale totale:** ~8 GB (DRSKit 2.6 + Frankensnare 50 MB + Unruly 790 MB + Big
Rusty 707 MB + VSCO-2 3.0 GB + MuldjordKit 3.6 GB). Volume manifest-only su Azure
T1-prep-D: ~8.6 GB aggiuntivi (CrocellKit 5.5 + Aasimonster 2.3 + Swirly 828 MB +
ShittyKit ~800 MB stimato).

---

## Verifica della catena (render di prova)

**Sfizz** — stem stereo pulito:

```
sfizz_render --sfz vendor/sfz/frankensnare/Programs/03-10x6ash.sfz \
             --midi <probe.mid> --wav out.wav --samplerate 44100
```

→ WAV 44.1 kHz stereo, non-silent (peak 0.134). Catena binario+kit **verificata
2026-05-22**.

**DrumGizmo** — render multi-mic con bleed:

```
drumgizmo -s -i midifile -I file=<probe.mid>,midimap=DRSKit/Midimap_full.xml \
          -o wavfile -O file=out,srate=44100 -e <n_samples> DRSKit/DRSKit_full.xml
```

→ 13 WAV mono (`out{Canale}-{idx}.wav`), 44.1 kHz, non-silent; bleed inter-canale
confermato (correlazione di inviluppo Snare→OH ≈ 0.93). Catena **verificata
2026-05-22** dentro la VM OrbStack.

Render di prova su MuldjordKit3 / Unruly Drums / Big Rusty Drums / VSCO-2 CE — da
eseguire come parte di T1-prep-A (recipe matrix) — verificherà che (a) i nuovi kit
si caricano correttamente, (b) il resolver `_resolve_drumgizmo_midimap` accetta la
convenzione `Midimap.xml` di MuldjordKit, (c) la diversità timbrica è reale (peak,
spectral centroid attesi diversi).
