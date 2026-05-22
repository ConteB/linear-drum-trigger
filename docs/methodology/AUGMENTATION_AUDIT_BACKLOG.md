---
id: LIN-DT-AUGAUDIT-001
title: Augmentation — Audit Backlog (gap analysis post/pre-render)
type: registro
status: DRAFT
phase: F0
domain: Data Engineering
version: 0.4.0
updated: 2026-05-23
tags: [augmentation, audit, backlog, dataset, input-agnostic, F0-T15]
related: [LIN-DT-DOSSIER-001, LIN-DT-SPEC-F0T2a, LIN-DT-SPEC-F0T4a]
supersedes: []
---

# 🧪 AUGMENTATION — AUDIT BACKLOG

> **Documento di lavoro — NON un Decision Lock.** Raccoglie i candidati di
> augmentation emersi dalla revisione informale del 2026-05-22 (osservazione del
> CEO) perché non vadano persi. È il *materiale d'ingresso* del task
> [`F0-T15`](../../04_INTELLIGENCE/MASTER_SCHEDULING.md#tasks) (audit della
> dottrina di augmentation). Nessuna voce qui è approvata: l'arbitraggio
> valore/costo e il Decision Lock avvengono in F0-T15 via STRP-001, e solo
> allora la dottrina [`DOSSIER §3`](DOSSIER_TECNICO.md#aug-prerender) viene
> aggiornata.

## 1. L'assunzione implicita da verificare

Il piano di augmentation del DOSSIER §3 è costruito — implicitamente — attorno a
**un solo tipo di input: una batteria tracciata e mixata in studio
professionale.** Su quell'asse (la "Studio Mutilation" §3.3 e l'"Inferno" §3.4)
è solido. Ma il plugin, in produzione, riceverà segnali da uno spazio più ampio:
file passati per codec, registrazioni amatoriali, materiale lo-fi. L'audit
F0-T15 deve decidere quanto di quello spazio coprire.

## 2. Assi comuni scoperti (augmentation post-render / dominio-audio)

| Asse | Cosa manca | Razionale | Costo impl. |
| :-- | :-- | :-- | :-- |
| **Delivery / codec** | Artefatti di compressione lossy — MP3/AAC/Opus a vari bitrate | Spalmano il transiente e introducono pre-echo: colpiscono **direttamente** il core onset-detection. Gran parte dell'audio reale è passata per un codec. Augmentation standard nello stato dell'arte. | basso |
| **Rumore di fondo / elettrico** | Hiss broadband, rumore di preamp, **ronzio di rete 50/60 Hz + armoniche**, ground-loop buzz | Il piano copre "Foley / rumore di palco" (FSD50K) — ma è rumore *impulsivo/ambientale*. Il noise floor *stazionario* e il hum sono un'altra famiglia, presente in **ogni** registrazione reale. | basso |
| **Cattura amatoriale** | Microfono di telefono/laptop, **AGC che pompa**, banda limitata, comb-filtering di stanza | È un *caso d'uso* reale e probabile: trascrivere una clip di prove. Si modella come scenario composito (bandlimiting + AGC + codec + IR di stanza piccola). | medio |

## 3. Tecniche puntuali mancanti (sull'asse "studio", già presidiato dal piano)

- **Noise gating / batteria gated.** Ubiquo sui mix reali. Il gate *rimuove coda
  e bleed* — l'esatto opposto del materiale del Livello 1. Se la rete non vede
  mai segnale gated, rischia di appoggiarsi alle code di decadimento come
  feature. *(Alto valore.)*
- **Limiting di bus / master ("loudness war").** Il mix intero schiacciato a
  muro da un brick-wall limiter + saturazione di master. Distinto dalla
  compressione *per-stem* che §3.3 già prevede. *(Medio-alto.)*
- **Delay / echo + riverbero algoritmico** (plate, spring, **gated reverb anni
  '80**). La convoluzione §3.4 copre solo ambienti reali; lo slap-back sul
  rullante e il gated reverb sono un'altra famiglia di code. *(Medio.)*
- **Sidechain pumping.** Modulazione periodica del guadagno agganciata alla
  cassa (produzione moderna / EDM): può indurre falsa struttura ritmica
  correlata agli onset. *(Medio.)*
- **Lo-fi / tape / vinile** — **wow & flutter**, crackle, pops, bitcrush, tape
  saturation + roll-off HF. Un genere intero (lo-fi hip hop). Nota fine: il
  *wow & flutter* perturba il **timing**, quindi tocca direttamente un
  trascrittore timing-preciso. Da includere *se* il lo-fi è un mercato-target —
  decisione di prodotto, non solo tecnica. *(Medio, condizionato.)*

- **Phase-flip e canali assenti** (emerso 2026-05-22). Il `multitrack_full`
  riallineato allo standard di settore (F0-T2a §2.3) **non ha più un canale
  `snare_bot` dedicato** — `snare_bot` è stato scambiato con `hihat`. Il
  phase-flip del microfono snare-bottom (DOSSIER §3.3, *«essenziale per i
  microfoni Snare Bottom»*) resta quindi senza canale-bersaglio nel layout a 8.
  F0-T15 deve decidere: il phase-flip opera sui canali esistenti, oppure serve
  un canale snare-bottom dedicato — il che riaprirebbe la tensione col tetto di
  8 canali. *(Basso costo decisionale, va solo chiuso.)*

- **Randomizzazione del bilanciamento di mix / gain-staging d'ingresso**
  (emerso 2026-05-23 — osservazione del CEO). Il piano §3.1 disaccoppia dal
  volume *assoluto* (Global Gain Shift, pre-render, sull'intero kit insieme) e
  §3.3 comprime/EQ-a i singoli stem — ma **nessun asse randomizza il
  bilanciamento *relativo* tra i canali/bus**. Oggi il Gold tensor porta la
  "house balance" del renderer: la rete può imparare *quella* proporzione
  cassa/rullante/overhead come feature implicita. Un utente reale fornisce un
  mix qualsiasi — cassa sepolta o in faccia, overhead dominanti, stem a livelli
  arbitrari, gain-staging casuale. Il livello e il bilanciamento sono
  variabili-disturbo: la rete deve trascrivere l'evento fisico **a prescindere
  dal mix**, non leggerlo. Rimedio: un vettore di guadagno casuale per-canale
  (più un guadagno globale) applicato allo stadio audio. È augmentation
  **sicura per il timing delle etichette** — il guadagno non sposta gli onset,
  a differenza del time-stretch (§5.1) — e a costo quasi nullo.
  **Vincolo critico (sottrattivo).** La randomizzazione va costruita in modo da
  **non rendere mai inudibile un bus che ha un onset nel target**: se uno
  strumento è presente nel MIDI ed è catturato da un **solo microfono**,
  portare quel canale a zero lascia il target nella loss ma toglie alla rete
  ogni segnale da ascoltare — la si punisce per un compito impossibile. Il
  bleed multi-mic mitiga il rischio *solo* per gli strumenti che suonano su più
  microfoni; il caso single-mic non ha ridondanza. Va prevenuto **a priori**,
  non riparato dopo (rimuovere il target qui sarebbe sbagliato — è ground-truth
  legittima): un limite inferiore, **quantitativo e misurabile**, al rapporto
  fra i guadagni dei canali / all'evidenza superstite di ogni bus etichettato.
  Dettaglio in §5, regola 3. *(Alto valore, costo bassissimo.)*

## 4. Casi particolari ma verosimili nel caso d'uso

- **Bleed del click / metronomo.** Un click track nella registrazione è un
  *transient saboteur perfetto* — e non è nella lista §3.4. Realistico in demo e
  registrazioni di prove.
- **Conteggio con le bacchette / talkback del batterista** prima del groove
  (il "1-2-3-4"). Parente del rejection-su-voce (LibriSpeech) ma con transienti
  percussivi reali.
- **Collasso in mono.** L'utente fornisce un input mono (somma L+R): caso di
  routing d'ingresso da non dare per scontato.
- **DC offset.** Banale, reale, a costo nullo.

## 5. Il confine dell'augmentation — tre regole da fissare

L'audit F0-T15 deve fissare esplicitamente i limiti, non solo le tecniche:

1. **Il time-stretch sposta la ground truth.** Lo stretch temporale è
   augmentation comune, ma cambia la *posizione* assoluta degli onset: è usabile
   **solo** se il target viene ri-temporizzato in modo coerente, altrimenti
   corrompe le etichette. Il piano attuale fa pitch-shift e **non** time-stretch
   — scelta corretta, da rendere esplicita come regola.
2. **Il masking ha un tetto di integrità (additivo).** Se lo "Stealth Mix"
   copre una ghost note fino a renderla *davvero* inudibile, l'etichetta diventa
   una bugia. Regola: l'augmentation non può mascherare un colpo sotto la sua
   soglia di rilevabilità senza rimuoverne anche il target corrispondente.
3. **L'attenuazione non può rendere inudibile un'etichetta (sottrattivo).**
   Distinta dalla regola 2: lì il colpo è coperto da un interferente *aggiunto*;
   qui è la randomizzazione del guadagno (§3, voce mix-balance) che abbassa
   l'evidenza dello strumento stesso sotto la soglia di rilevabilità. Se uno
   strumento è presente nel MIDI — quindi ha un target — ed è catturato da un
   **solo microfono**, portare quel canale a zero lascia il target nella loss
   ma toglie alla rete ogni segnale: la si addestra su un compito impossibile.
   A differenza della regola 2, **rimuovere il target NON è la soluzione** — lo
   strumento c'è davvero, l'etichetta è ground-truth legittima; cancellarla
   insegnerebbe alla rete a ignorare colpi reali. La soluzione è **preventiva e
   misurabile**: la randomizzazione del guadagno è vincolata in modo che, per
   ogni bus con un onset nel target, l'evidenza superstite resti sopra una
   soglia di rilevabilità quantitativa.
   - *Forma rigorosa (label-aware):* per ogni onset del bus `b`, il picco del
     transiente nel canale più forte **dopo** il guadagno deve restare ≥ un
     margine SNR sopra il noise floor effettivo del mix. È calcolabile: il
     renderer espone i canali per-microfono e il target dice quali bus suonano,
     quindi l'energia per-strumento per-canale è **nota e misurabile**.
   - *Forma proxy (economica):* un limite inferiore fisso al rapporto fra i
     guadagni dei canali — uno spread massimo di attenuazione — senza analisi
     per-onset.
   F0-T15 sceglie la forma, fissa la soglia, e decide come misurare il "noise
   floor effettivo". Caso peggiore da coprire esplicitamente: `mic_config: mono`
   e gli strumenti single-mic, dove non esiste ridondanza di bleed.

## 6. Pre-render (MIDI Jittering, §3.1) — da auditare a parte

Il CEO ha indicato che l'audit dovrebbe toccare *forse anche* l'augmentation
**pre-render** (§3.1 — Time/Velocity Jittering, Component Dropping, Flams).
Voce di backlog da espandere in F0-T15: verificare che la distribuzione del
jitter MIDI sia realistica (es. groove umani reali vs. uniforme), e che la
"Machine-Gun Chaos" e i flam coprano densità di colpi estreme senza degenerare.

## 7. Agnosticità d'ingresso — permutazione canali & conteggi variabili

*(Origine: revisione del CEO 2026-05-22 — coniugata a questo audit perché è la
stessa famiglia di decisioni: varietà dei dati di training a monte di F2-T2.)*

**Il problema.** Il design "Input-Agnostico" ([`DOSSIER §2.1`](DOSSIER_TECNICO.md#input-agnostic),
[`F0-T4a §4`](F0-T4a_TCN_TOPOLOGY_SPEC.md#input-agnostic-slots)) è oggi agnostico al **conteggio** dei
canali (1–8, zero-fill dei mancanti) ma **non all'assegnazione**: gli 8 slot hanno
semantica fissa (slot 0 = kick, 1 = snare, …) e il training rende solo i conteggi
canonici {1,2,4,8} in ordine fisso. Un utente reale fornisce però configurazioni
arbitrarie — mono, stereo, 5 mic, 7 mic con due microfoni sul kick — in ordine
qualsiasi, e oggi dovrebbe mappare a mano i suoi canali sugli slot (UI, F4).
*(Nota: i mic mancanti NON richiedono ri-registrazione — lo zero-fill li gestisce già.)*

**La soluzione (training-side, nessuna riprogettazione della rete).**
- **Permutazione dei canali** in training — mescolare l'ordine dei canali: il Conv1D
  k=1 della Input-Agnostic Projection non può più affidarsi a "slot 0 = kick" → diventa
  invariante all'ordine.
- **Conteggi variabili {1…8}** — non solo {1,2,4,8}: 5 e 7 entrano in distribuzione.

**Conseguenza.** L'utente scarica N tracce in qualsiasi ordine, lascia vuoti gli slot
mancanti, non riregistra e non mappa mai a mano — vera agnosticità (input come *insieme*
di canali, non 8 posizioni etichettate). La semantica fissa per-slot di F0-T4a §4 si
dissolve in "porte" d'ingresso → **amendment a F0-T4a §4** da mettere a valle del
Decision Lock F0-T15. Voce **alto valore**: è una promessa di prodotto.

## 8. Prioritizzazione provvisoria (da ratificare in F0-T15)

Ordine indicativo per rapporto **valore / costo** — i primi tre sono alto
impatto e costo basso:

1. Randomizzazione del bilanciamento di mix / gain-staging d'ingresso.
2. Artefatti di codec lossy.
3. Noise floor stazionario + hum di rete.
4. Noise gating.
5. Limiting di bus / master.
6. Click/metronomo come saboteur · collasso mono · DC offset.
7. Delay / riverbero algoritmico · sidechain pumping.
8. Lo-fi / wow & flutter (condizionato alla decisione di mercato).
9. Scenario composito "cattura amatoriale".

---
*Backlog aperto 2026-05-22 — input del task F0-T15. Aggiornare `status` a
`SUPERSEDED` quando F0-T15 chiude e la dottrina `DOSSIER §3` è aggiornata.*
