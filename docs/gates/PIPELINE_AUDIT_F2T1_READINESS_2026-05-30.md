---
title: "Pipeline Audit — F2-T1 Azure Render Readiness (2026-05-30)"
tags: [audit, F2-T1, azure, render, readiness, gold]
status: REVIEW
---

# Pipeline Audit — F2-T1 Azure Render Readiness

**Data:** 2026-05-30 (sessione "caffeina", CEO in viaggio)
**Richiesta CEO:** revisione della pipeline in cerca di discrepanze e verifica che
*tutto sia allineato per la generazione su Azure* (F2-T1, render Gold ~1.5 TB).
**Metodo:** trace end-to-end del percorso di render che girerà sulla VM Azure
(`build_recipe_matrix.py` → `run_f2_t1_render.py` → `orchestrate.build_gold_sample`
→ `ShardWriter` → `dvc push`), cross-check contro la pipeline canonica validata
F0-T18 (canonicalizzazione) + F0-T19 (dialect render + flat-28).

## Verdetto

> ## ❌ F2-T1 **NON è pronto** per il render.
> Gli artefatti Azure (`build_recipe_matrix.py`, `provision_render_vm.sh`, runbook —
> tutti del **23-05**) **precedono** F0-T18 (28-05) e F0-T19 (28/29-05) e sono
> **fuori sincrono** con la pipeline canonica validata su 3 assi: (1) la
> canonicalizzazione **non viene attivata**, (2) **5 dei 10 kit** del roster non
> sono coperti dal dialect map validato, (3) **nomi/path kit stale**. Renderizzare
> ora produrrebbe Gold rotto a scala 1000× — esattamente lo spreco che la doctrine
> "use-it-or-lose-it" §1.1 vieta. **Nessun fix applicato in autonomia** (artefatti
> del burn $200 → ratifica CEO richiesta, cultura Decision-Lock).

## Findings (ranked)

| # | Sev | Titolo | Effetto a scala |
| :- | :- | :- | :- |
| B1 | 🔴 BLOCKER | Canonicalizzazione **saltata** su tutto il render | hihat GM 22/26 droppato in silenzio (10% onset / 34% hihat) + remap Roland→canonico mai applicati |
| B2 | 🔴 BLOCKER | **5/10 kit** non nel dialect map validato | phantom notes / articolazioni sbagliate sui kit non coperti |
| B3 | 🔴 BLOCKER | Nomi/path kit **stale** in `build_recipe_matrix.py` | MuldjordKit3 path inesistente → render fail-loud; Aasimonster/ShittyKit `_full.xml` mismatch |
| H4 | 🟠 HIGH | Coherence gate **non eseguito** come pre-flight | nessuna rete di sicurezza automatica prima del burn |
| M5 | 🟡 MED | `bus_mapping` metadata `@1.0` (ora schema 2.0) | innocuo (non validato) ma fuorviante |
| M6 | 🟡 MED | `gold_writer` non valida **peak ≤ 1.0** | 8-21% render DG clippano (violazione contratto F0-T2a) |
| M7 | 🟡 MED | Watchdog Sfizz 120s su grooves densi | drop silenzioso dei grooves più densi (vedi memoria `sfizz-rare-china-timeout`) |
| Q8 | 🔵 DECIS | F2-T1 include i MIDI **sintetici** (rare/chaos)? | i 4 canali rari restano affamati in produzione se no |

---

### B1 — 🔴 Canonicalizzazione saltata su tutto il render F2-T1

**Causa.** `build_recipe_matrix.py` emette il blocco `midi_source` **senza il campo
`standard`** (`build_recipe_matrix.py:169-172`). In `recipe.py` `standard` è
opzionale (default `None`). In `orchestrate.py:406` la canonicalizzazione è gated:

```python
if recipe.midi_source.standard is not None:   # orchestrate.py:406
    ... canonicalize_midi(..., standard=recipe.midi_source.standard) ...
```

→ con `standard = None` (esattamente ciò che il builder produce) la
canonicalizzazione **viene saltata**.

**Prova del contrasto.** `mini_l3_runner.py:426` — il path che ha prodotto Gold
canonico corretto (hihat +51%, 0 phantom) — imposta esplicitamente
`standard="roland_td11"`. Il builder F2-T1 no. I due percorsi di render
costruiscono il recipe in modo divergente; solo la mini-L3 attiva F0-T18.

**Effetto a scala.** Il bug F0-T18 (la GMD è Roland TD-11, gli onset hihat "edge"
GM 22/26 cadono fuori da ogni consumatore e vengono droppati in silenzio = **10,1%
di TUTTI gli onset, 34% di tutto l'hihat**, su 50,7% dei file) **si riproduce sul
render 1.5 TB**. Inoltre ogni rimappatura Roland→canonico salta → tutto il lavoro
F0-T18/T19 è inerte per la produzione.

**Fix proposto (ratifica CEO).** In `build_recipe_matrix._recipe_yaml` emettere
`midi_source.standard: roland_td11` (la GMD è Roland TD-11). 2 righe, mirror del
pattern validato di `mini_l3_runner`.

---

### B2 — 🔴 5 dei 10 kit del roster non sono nel dialect map validato

`kit_dialect.has_kit()` è **match esatto** (`kit_label in kits`). Cross-check
roster F2-T1 (`build_recipe_matrix._TRAIN_KITS`/`_VAL_KITS`) vs
`docs/specs/kit_dialect_map.yaml`:

| kit | split | engine | nel dialect map |
| :- | :- | :- | :- |
| DRSKit | train | DG | ✅ |
| CrocellKit | train | DG | ✅ |
| **MuldjordKit3** | train | DG | ❌ (map ha `MuldjordKit`) |
| Aasimonster | train | DG | ✅ |
| **Frankensnare** | train | SFZ | ❌ mai validato |
| **UnrulyDrums** | train | SFZ | ❌ mai validato |
| BigRustyDrums | train | SFZ | ✅ |
| **VSCO2CE** | train | SFZ | ❌ mai validato |
| ShittyKit | val | DG | ✅ |
| **SwirlyDrums** | val | SFZ | ❌ mai validato |

**Effetto.** I kit non coperti cadono nel **path legacy** (`orchestrate._render`,
ramo `else`): DG → vendor midimap (quello **non patchato** — Plan-A ritirato in
F0-T19, quindi i phantom tornano); SFZ → MIDI canonico grezzo → `.sfz` assumendo
GM (mai verificato per questi kit). **I 4 kit SFZ Karoryfer (Frankensnare,
UnrulyDrums, VSCO2CE, SwirlyDrums) non sono MAI passati per la pipeline canonica
F0-T18/T19** — la mini-L3 ha validato solo BigRustyDrums lato SFZ.

**Fix proposto (ratifica CEO — non banale).** Due opzioni:
- **(A) Estendere + validare il dialect map** ai 5 kit (autorare la mappa
  canonico→dialetto da ogni keymap kit, poi `audit_midi_coherence` 0-blocker per
  ciascuno). È lavoro reale (richiede ispezione dei file kit), $0 Azure.
- **(B) Primo render F2-T1 col roster ridotto a 5 kit validati** (DRSKit,
  CrocellKit, Aasimonster, BigRustyDrums, ShittyKit), aggiungere gli altri in un
  secondo render dopo la validazione. Sblocca il burn subito, copertura timbrica
  ridotta. *(Nota: con 5 kit la partizione train/val DOSSIER §10.2 va rivista —
  val = solo ShittyKit.)*

---

### B3 — 🔴 Nomi/path kit stale in `build_recipe_matrix.py`

Il builder (23-05) precede tutto il lavoro di kit-resolution cross-kit
(`kit_mic_mapping.yaml` alias, resolver `_find_main_kit_xml`, fallback single-XML).

- **MuldjordKit3**: `build_recipe_matrix` usa nome `MuldjordKit3` + path
  `MuldjordKit3_full.xml`. Il kit vendorizzato ship **`MuldjordKit3.xml`** (non
  `_full.xml`) → `DrumGizmoRenderer` fallirebbe fail-loud sul file inesistente.
  Il dialect map + `kit_mic_mapping` usano la chiave **`MuldjordKit`**.
- **Aasimonster / ShittyKit**: recipe path `*_full.xml` ma il dialect map punta a
  `Aasimonster.xml` / `ShittyKit.xml` → da verificare quale XML esista sulla VM
  (la mini-L3 risolveva via `_find_main_kit_xml`, il builder hardcoda `_full.xml`).

**Fix proposto.** Riconciliare nomi/path del roster con `kit_mic_mapping.yaml` +
`kit_dialect_map.yaml` + realtà vendor — idealmente riusando la logica di
risoluzione XML di `mini_l3_runner` invece di path hardcoded.

---

### H4 — 🟠 Coherence gate non eseguito come pre-flight

`tools/audit_midi_coherence.py` è un **tool manuale, non wired nella pipeline**
(handoff F0-T18). Intercetterebbe B1/B2 (note unmapped → BLOCKER). **Va eseguito
sulla recipe matrix F2-T1 prima del burn** come gate (0 BLOCKER per procedere).
Oggi nulla lo fa automaticamente prima di spendere il credito.

### M5 — 🟡 `bus_mapping: midi_mapping_table.yaml@1.0` stale
La tabella è ora **schema 2.0** (GM→9 canali, F0-T19). Stringa non validata
(la mappatura reale è caricata dal codice via `load_bus_mapping`), quindi innocua,
ma fuorviante. Aggiornare a `@2.0`.

### M5b — 🟡 `bronze/gmd/full` non esiste (runbook/esempio stale)
Il runbook e il docstring di `build_recipe_matrix.py` usano `--midi-source-dir
bronze/gmd/full`, ma **quella dir non esiste**: la GMD piena reale è
**`bronze/gmd/v1`** (1150 MIDI CC-BY-4.0). Seguendo il runbook alla lettera il
render fallirebbe (FileNotFoundError fail-loud). Aggiornare runbook + esempio a
`bronze/gmd/v1` (o creare il simlink `full`).

### M6 — 🟡 `gold_writer` non valida peak ≤ 1.0
Carry-over da [`PIPELINE_AUDIT_2026-05-29`](PIPELINE_AUDIT_2026-05-29.md) F3:
8-21% dei render DG hanno peak > 1.0 (violazione contratto F0-T2a §3). P1
(pre-emphasis + z-score) mitiga in training, ma il Gold scritto è non-conforme.
A scala 1.5 TB vale la pena aggiungere un check/normalize o almeno un warning.

### M7 — 🟡 Watchdog Sfizz 120s su grooves densi
Nel render sintetico i grooves `rare-china` densi su Sfizz hanno mandato in
timeout il watchdog 120s (14 drop, vedi la memoria `sfizz-rare-china-timeout`). F2-T1 è
**GMD-only** (no sintetico), quindi non morde direttamente — ma i grooves GMD più
densi sui kit SFZ andrebbero spot-checkati contro i 120s: un drop silenzioso a
scala = sample persi.

### Q8 — 🔵 Decisione: F2-T1 include i MIDI sintetici (rare/chaos)?
`build_recipe_matrix --midi-source-dir bronze/gmd/full` = **solo GMD reale**. La
sessione 30-05 ha mostrato che i 4 canali rari (sidestick/ride_bell/crash/aux)
sono affamati nella GMD (crash 7 onset in 248 sample val) e che i MIDI sintetici
li popolano. **Domanda strategica per il CEO:** F2-T1 deve includere il pool
sintetico (rare_emphasis + chaos) per popolare i canali rari nel Gold di
produzione (→ migliore detection rari a L4), o la frequenza GMD reale basta?
*(Se sì: M7 — watchdog Sfizz — diventa BLOCKER perché i chaos sono densi.)*

---

## Cosa è risultato SANO (verificato)

- `orchestrate.build_gold_sample` **è** F0-T19-aware (canonicalize → dialect →
  flat-28 → tail-std), *quando* il recipe ha `standard` e il kit è nel dialect map.
- `run_f2_t1_render.py` è solido: resume-safe (manifest), fail-loud per recipe /
  fail-soft per run, dvc push periodico, SIGTERM-drain, state.json per il monitor.
- `ShardWriter` è flat-28-agnostico (impacca triple opache) → nessun problema.
- `provision_render_vm.sh` **scarica tutti i 10 kit** del roster (sha256-verified)
  → la copertura kit lato *provisioning* è ok; il gap è nel *dialect map*, non nei
  binari.
- `parse_recipe` accetta il recipe stale senza crashare (`standard` opzionale) —
  per questo il bug è **silenzioso**, non un fail-loud.

## Raccomandazione operativa (per ratifica CEO)

Sequenza $0 Azure, prima di qualunque burn:
1. **B1** — aggiungere `standard: roland_td11` al recipe builder (fix banale).
2. **B3** — riconciliare nomi/path kit con i config validati.
3. **B2** — decidere fra (A) estendere+validare il dialect map ai 5 kit mancanti,
   o (B) primo render col roster ridotto a 5 kit validati.
4. **H4** — eseguire `audit_midi_coherence.py` sulla recipe matrix F2-T1 come gate
   pre-burn (0 BLOCKER richiesto).
5. **M5** — bump metadata `@2.0`.
6. **Q8** — Decision Lock sul sintetico in F2-T1.
7. **M6/M7** — opzionali, ma a scala 1.5 TB conviene chiuderli.

Solo dopo 1-4 il render Azure è sicuro. Il **costo dell'attesa è ZERO**; il costo
di evitarlo sarebbe ~$60 di render + un Gold da buttare.

---
*Audit prodotto in autonomia ("caffeina"). Nessuna modifica al codice applicata —
tutte le proposte attendono ratifica CEO (cultura Decision-Lock, artefatti del
burn $200).*

---

## UPDATE 2026-05-30 (post-direttiva CEO "procedi + scarica solo i keymap")

### ✅ B1 — FIXED
`build_recipe_matrix._recipe_yaml` ora emette `midi_source.standard: roland_td11`
→ `orchestrate` esegue la canonicalizzazione F0-T18 su tutto F2-T1. Smoke verde
(recipe emesso + `parse_recipe` accetta). Il bug hihat a scala è chiuso.

### ✅ M5 — FIXED
`bus_mapping: midi_mapping_table.yaml@2.0` (era `@1.0`).

### B2 — analisi SFZ da KEYMAP REALI (no allucinazione, download leggero ~KB)

Scaricati i `.sfz`/keymap reali dei 4 kit non coperti dai repo GitHub Karoryfer/VSCO
(**solo testo, nessun WAV**, in `/tmp/sfz_keymap_audit`). Punto cardine: la canonica
F0-T18 produce **note GM** (36 kick · 38 snare · 42/44/46 hh · 51/53 ride · 49/57
crash · 52 china · 55 splash). Un kit SFZ **GM-keyed** funziona col **path legacy
senza dialect entry → zero invenzione**; la dialect serve solo per i NON-GM (es.
BigRustyDrums, che infatti è nel map).

| kit SFZ | tipo (dai file) | key reali | GM-keyed | adatto a kit-render | serve dialect |
| :- | :- | :- | :- | :- | :- |
| **Frankensnare** | **solo rullanti** | tutti `key=37` (6/6) | n/a | ❌ **NO** | — (scartare) |
| **VSCO2CE** | **percussione orchestrale** (Brass/Strings/Woodwinds/Perc); path `Programs/percussion.sfz` **inesistente** | n/a | n/a | ❌ **NO** | — (scartare) |
| **UnrulyDrums** | kit completo | kick36 snare38 ss37 hh42/44/46 ride51 bell53 crash49/57 china52 splash55 | ✅ **sì** | ✅ sì | **no** (legacy ok; gap minore: tom GM 48 assente → WARN) |
| **SwirlyDrums** | kit completo (Full_kit.sfz, keymap modulari kick/snare/hh/tom/cymbal + variante e-kit `td25`); path `01-full.sfz` **stale** | da confermare col coherence gate | probabile | ✅ sì | probabile no |

**Conclusione B2 (evidence-based).** Le 2 voci problematiche **non sono un problema di
dialect map** ma di **roster**: Frankensnare è una libreria di soli rullanti su un
singolo tasto, VSCO2CE è percussione orchestrale — entrambe **inadatte** a renderizzare
grooves di batteria completi (produrrebbero quasi-silenzio / suoni sbagliati). Le altre
2 (UnrulyDrums, SwirlyDrums) sono kit completi **GM-keyed** → funzionano col path
legacy **senza autorare nulla** (la canonica li alimenta con note GM corrette).

**Roster F2-T1 raccomandato (per ratifica CEO) — 8 kit, tutti su evidenza reale:**
- **Train (7):** DRSKit, CrocellKit, MuldjordKit, Aasimonster (DG, dialect ✓) +
  BigRustyDrums (SFZ, dialect ✓) + UnrulyDrums, SwirlyDrums (SFZ, GM-keyed → legacy).
- **Val (1):** ShittyKit (DG, dialect ✓).
- **SCARTARE:** Frankensnare (solo-snare) + VSCO2CE (orchestrale). *(Per il side-stick e
  la varietà di rullante, Frankensnare semmai è materiale da layering in augmentation
  post-render, non da render primario.)*
- **Gate obbligatorio prima del burn:** `audit_midi_coherence.py` su UnrulyDrums +
  SwirlyDrums (confermare 0 BLOCKER; i gap tipo tom-48 sono WARN accettabili).

### B3 — path/nomi stale confermati (da correggere nel roster ratificato)
- `MuldjordKit3` → nome **`MuldjordKit`** (chiave dialect map) + path
  `MuldjordKit3/MuldjordKit3.xml` (non `_full.xml`).
- `SwirlyDrums` path → **`Programs/Full_kit.sfz`** (non `01-full.sfz`).
- `VSCO2CE` → scartato (path inesistente comunque).
- `Aasimonster` / `ShittyKit`: il dialect map usa `Aasimonster.xml` / `ShittyKit.xml`
  (non `_full.xml`) — allineare il `kit_path` del recipe alla realtà vendor / al
  resolver `_find_main_kit_xml` di `mini_l3_runner` invece di hardcodare `_full.xml`.

> **Decisione richiesta al CEO:** ratificare il roster a 8 kit (scartare Frankensnare +
> VSCO2CE). Su OK, applico B3 (nomi/path) + `audit_midi_coherence` su Unruly/Swirly e
> F2-T1 è render-ready. **Nessuna dialect entry autorata** (i kit tenuti sono o
> già-nel-map o GM-keyed-legacy → zero invenzione, come da tua avvertenza).
