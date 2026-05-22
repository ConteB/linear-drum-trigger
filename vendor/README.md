# Vendored assets — render toolchain & SFZ kits

Asset vendorizzati per **`ENGINEERING_STANDARDS §4`**: copia locale dei binari di
render e delle librerie SFZ, così la sparizione di un repository a monte non rende
il dataset Gold non riproducibile.

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
Gli altri kit del roster (Unruly/Big Rusty/Swirly Drums, kit DrumGizmo) si vendorano
alla bisogna — Frankensnare è il primo, scelto come kit di sviluppo per F0-T2b.

## Verifica della catena (render di prova)

```
sfizz_render --sfz vendor/sfz/frankensnare/Programs/03-10x6ash.sfz \
             --midi <probe.mid> --wav out.wav --samplerate 44100
```

→ WAV 44.1 kHz stereo, non-silent (peak 0.134). Catena binario+kit **verificata
2026-05-22**.
