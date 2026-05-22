# Vendored assets — render toolchain & drum kits

Asset vendorizzati per **`ENGINEERING_STANDARDS §4`**: copia locale dei binari di
render e delle librerie di campioni (SFZ + kit DrumGizmo), così la sparizione di un
repository a monte non rende il dataset Gold non riproducibile.

I binari pesanti sono **git-ignored** (vedi `/.gitignore`). Questo manifest è il
record di re-fetch: chiunque può ricostruire `vendor/` dagli URL + checksum qui sotto.

## `vendor/sfizz/` — CLI di rendering Sfizz

| Campo | Valore |
| :-- | :-- |
| Binario | `sfizz_render` (+ man page `sfizz_render.1`) |
| Versione | sfizz **1.2.3** |
| Sorgente | `https://github.com/sfztools/sfizz/releases/download/1.2.3/sfizz-1.2.3-macos.tar.gz` |
| Licenza | BSD-2-Clause (sfizz) |
| Architettura | x86_64 — eseguibile autonomo (solo system libs); gira sotto **Rosetta 2** su Apple Silicon |
| sha256 (`sfizz_render`) | `db3e788ed38a96d9fb866081215b08b1a195c1068d52700ae8794da064c4a6a5` |

## `vendor/sfz/frankensnare/` — kit SFZ (roster F0-T1b)

| Campo | Valore |
| :-- | :-- |
| Kit | Karoryfer — **Frankensnare v2.100** |
| Sorgente | `https://github.com/sfzinstruments/karoryfer.frankensnare/releases/download/v2.100/Frankensnare_2100.zip` |
| Licenza | **CC0-1.0** (public domain — nessuna attribuzione richiesta) |
| sha256 (zip) | `03defbfbc5232a5eafa69e839e43b33f8e0746ea9a098fc2b4f411e8112a732a` |
| Contenuto | 309 file `.sfz` (`Programs/`), `Samples/`, `Presets/` — snare su GM key **38** |

Roster completo dei kit approvati: `docs/compliance/F0-T1b_KIT_ROSTER_SURVEY.md` §3.
Gli altri kit SFZ del roster (Unruly/Big Rusty/Swirly Drums) si vendorano alla
bisogna — Frankensnare è il primo, scelto come kit di sviluppo per F0-T2b.

## `drumgizmo` — CLI di rendering DrumGizmo (F0-T2c)

| Campo | Valore |
| :-- | :-- |
| Binario | `drumgizmo` (CLI) |
| Versione | DrumGizmo **0.9.20** (`0.9.20-3build3`) |
| Provisioning | **apt** nella VM OrbStack `ubuntu` — `apt-get install drumgizmo` |
| Licenza | LGPL-3.0 (DrumGizmo) |
| Architettura | arm64 (VM Linux) |

**Non vendorizzato come file**: a differenza di Sfizz, DrumGizmo non ha un prebuilt
macOS. Gira su **Linux** — parità d'ambiente col render F2 su Azure — provisionato via
`apt` (versione pinnata sopra). L'adapter `DrumGizmoRenderer` lo risolve su `PATH`; gli
oracoli §6.3 skippano dove il binario è assente (host macOS) e girano dentro OrbStack.

## `vendor/drumgizmo/DRSKit/` — kit multi-mic (roster F0-T1b)

| Campo | Valore |
| :-- | :-- |
| Kit | DrumGizmo — **DRSKit v2.1** |
| Sorgente | `https://drumgizmo.org/kits/DRSKit/DRSKit2_1.zip` |
| Licenza | **CC-BY-4.0** (uso commerciale con attribuzione) |
| sha256 (zip) | `529f2dcad836593167d0cab218f125f591cd71199748fa681e05e3866667f090` |
| md5 (zip) | `8c4d4b61ad9d354b3b845edd5da9c133` (fonte: drumgizmo.org) |
| Contenuto | kit XML (`DRSKit_full/basic/minimal/no_whiskers`) + midimap + `Samples/` |
| Canali mic | **13** — AmbL/R, Kdrum back/front, Hihat, OHL/R, Ride, Snare top/bottom, Tom1-3 |

Lo zip (2.6 GB) **non è conservato**: estratto in `vendor/drumgizmo/DRSKit/`, è la
sorgente del bleed reale. Re-fetch: scaricare lo zip dall'URL, verificare lo sha256,
estrarre. Kit di sviluppo per F0-T2c — gli altri 5 kit DrumGizmo del roster si
vendorano alla bisogna (in F2, render dell'intero dataset).

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
