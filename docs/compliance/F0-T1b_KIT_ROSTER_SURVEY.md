---
id: LIN-DT-ROSTER-F0T1b
title: F0-T1b — Survey & Selezione Kit (Roster di Training)
type: registro
status: ACTIVE
phase: F0
domain: Legal / Compliance
version: 1.1.0
updated: 2026-05-23
tags: [compliance, kit-roster, F0-T1b]
related: [LIN-DT-DPL-001, LIN-DT-SPEC-F0T2a]
supersedes: []
---

# 🥁 F0-T1b — SURVEY & SELEZIONE KIT (Roster di Training)
**Task:** F0-T1b · **Avviato:** 2026-05-20 · **Stato:** ◐ IN CORSO → proposta di roster per Decision Lock
**Origine:** osservazione del CEO — SM Drums è un solo kit; serve diversità timbrica.
**Riferimenti:** `DATA_PROVENANCE_LOG.md` · `F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md` §2

## 1. Dottrina applicata — "Self-Evident Commercial License"
> **Decision Lock CEO (2026-05-20):** si include un asset **solo** se la sua licenza
> **già pubblicata** concede **inequivocabilmente** l'uso commerciale. **Zero
> corrispondenza** con i creatori. **Zero divulgazione** del progetto. Se la sola licenza
> pubblica non dà tranquillità → asset **fuori**. Niente "donationware da verificare",
> niente conferme via email.

**Conseguenza operativa:** sono ammessi solo asset con licenza formale **CC0** o **CC-BY**
(o equivalente public-domain) leggibile direttamente alla fonte.

## 2. Il problema (perché questo task esiste)
Inventario di training *precedente*: SM Drums (1 kit Ludwig) + Salamander (1 kit Yamaha) +
"DrumGizmo Kits" generico. Diversità timbrica reale ≈ 2 timbri nominati. Una rete di
trascrizione addestrata su pochi kit **impara il timbro, non l'evento fisico** → crolla
sul mondo reale. Il *test set* (registrazioni reali) è vario; il *training set* no →
**generalization gap**.

## 3. Matrice licenze — kit verificati

| Kit | Engine | Licenza pubblicata | Uso commerciale | Multi-mic | Verdetto |
| :-- | :-- | :-- | :-- | :-- | :-- |
| **DrumGizmo — CrocellKit** | DrumGizmo | CC-BY-4.0 | ✅ sì (con attribuzione) | ✅ sì | 🟢 INCLUSO |
| **DrumGizmo — DRSKit** | DrumGizmo | CC-BY-4.0 | ✅ sì | ✅ sì | 🟢 INCLUSO |
| **DrumGizmo — MuldjordKit** (Tama Superstar) | DrumGizmo / SFZ | CC-BY-4.0 | ✅ sì | ✅ sì (anche SFZ stereo via FreePats) | 🟢 INCLUSO |
| **DrumGizmo — The Aasimonster** | DrumGizmo | CC-BY-4.0 | ✅ sì | ✅ sì | 🟢 INCLUSO |
| **DrumGizmo — ShittyKit** | DrumGizmo | CC-BY-4.0 | ✅ sì | ✅ sì | 🟢 INCLUSO |
| **DrumGizmo — Sommerhack 2016-Kit** | DrumGizmo | era CC-BY-4.0 | — | — | 🔴 **ESCLUSO** (amendment 2026-05-23 — non più sul wiki drumgizmo.org) |
| **Karoryfer — Big Rusty Drums** | SFZ | **CC0** | ✅ sì (nessuna attribuzione) | parziale | 🟢 INCLUSO |
| **Karoryfer — Unruly Drums** | SFZ | **CC0** | ✅ sì | ✅ sì (10 round-robin) | 🟢 INCLUSO |
| **Karoryfer — Swirly Drums** | SFZ | **CC0** | ✅ sì | parziale | 🟢 INCLUSO |
| **Karoryfer — Frankensnare** | SFZ | **CC0** | ✅ sì | — (solo rullante) | 🟢 INCLUSO (varietà snare) |
| **Salamander Drumkit** (Yamaha) | SFZ | **CC-BY-SA-3.0** | ⚠️ ShareAlike → opera derivata vincolata | parziale | 🔴 **ESCLUSO** (amendment 2026-05-23 — vedi §8) |
| **VSCO-2 CE** | SFZ | CC0 | ✅ sì | — | 🟢 INCLUSO (percussioni accessorie, §3.4) |
| **SM Drums** (Ludwig '60س) | SFZ | *nessuna licenza formale* — solo dichiarazione informale dell'autore | ⚠️ dichiarato ma non formalizzato | ✅ sì | 🔴 **ESCLUSO** — non supera la dottrina §1 |

## 4. Roster-target proposto

**11 kit di batteria + 1 libreria snare**, tutti con licenza **formale** e uso commerciale
**inequivocabile** — zero corrispondenza, zero divulgazione:

- **Backbone multi-mic (bleed reale):** 6 kit DrumGizmo CC-BY-4.0 — è la sorgente primaria
  del rientro microfonico, il moat del prodotto.
- **Backbone SFZ pulito:** Karoryfer (3 kit + Frankensnare, CC0) + Salamander (CC-BY-3.0).
- **Accessorie sintetiche:** VSCO-2 CE (CC0), come da DOSSIER §3.4.

→ Da ~2 timbri nominati a **~11 kit** con legni, epoche e catene di ripresa diversi
(Tama Superstar moderna, kit "rusty" vintage, Yamaha pop/clean, ecc.). Il generalization
gap si chiude in modo sostanziale, **senza alcun rischio legale residuo**.

## 5. Effetto collaterale strategico — de-risking compliance
Con 11 kit formalmente CC, **SM Drums smette di essere un single point of failure**: la
sua decadenza a CP-1 (era il rischio dell'outreach) diventa irrilevante. Il roster non
dipende più da nessun asset "informale". F0-T1 si semplifica: niente email, niente attesa.

## 6. ⚠️ Questione aperta — NON risolta da questo task
ENST-Drums e MedleyDB sono **esclusi** dalla dottrina §1 (research-only / NonCommercial).
Erano gli asset dello **Holdout reale** (`DOSSIER_TECNICO` §10.3, `MASTER_CHECKLIST` §1).
**Il Validation Protocol va ridisegnato** — serve una fonte di registrazioni reali con
ground-truth a licenza commerciale chiara, oppure il Piano B (registrazioni proprietarie
annotate). Questo è un task a sé, da portare al CEO separatamente.

## 7. Stato DoD
- [x] Survey kit completato; licenze verificate alla fonte.
- [x] Matrice licenze + roster-target proposto.
- [ ] Decision Lock del CEO sul roster (§4).
- [ ] A valle: aggiornare `DATA_PROVENANCE_LOG.md` §2.A con i kit confermati.

## 8. Amendment 2026-05-23 — verifica alla fonte pre-vendoring

Prima del vendoring fisico (sotto-task pre F2-T1: download + sha256 + manifest), ogni
kit del roster è stato ri-verificato alla fonte ufficiale. **2 esclusioni** rispetto
al survey 2026-05-20:

### Salamander Drumkit (Yamaha) — escluso per licenza CC-BY-**SA**
- Pagina ufficiale: `https://sfzinstruments.github.io/drums/salamander/`
- Mirror Internet Archive (`archive.org/details/SalamanderDrumkit`)
- **Licenza reale:** CC-BY-**SA**-3.0 (ShareAlike) — non CC-BY-3.0 come registrato nella
  matrice originale §3. ShareAlike è una clausola copyleft: un'opera derivata deve
  essere distribuita sotto la **stessa licenza** CC-BY-SA.
- **Rischio per il prodotto:** se un avvocato del licenziante sostiene che il modello
  TCN trainato è "opera derivata" del kit (interpretazione plausibile), saremmo
  obbligati a rilasciare il modello sotto CC-BY-SA → ovvero **gratis con sorgente
  aperta**, contro la natura commerciale del plugin Early-Access $99.
- **Verdetto:** la licenza non è "Self-Evident Commercial" nel senso della dottrina
  §1 → **escluso senza eccezioni**. La diversità timbrica Yamaha pop/clean può
  essere ricostruita via augmentation IR + EQ sui kit CC0/CC-BY ammessi.

### Sommerhack 2016-Kit — escluso per indisponibilità
- Pagina wiki ufficiale `https://drumgizmo.org/wiki/doku.php?id=kits:sommerhack-2016-kit`
  restituisce *"This topic does not exist yet"* — il kit è stato rimosso o non è mai
  stato pubblicato.
- **Verdetto:** asset di fatto non disponibile alla fonte → **escluso**.

### Roster operativo aggiornato (10 kit)

Dei 12 voci della matrice §3, restano **10 attivi**:

| Engine | Kit attivi |
| :-- | :-- |
| **DrumGizmo** (5 kit, CC-BY-4.0) | DRSKit · CrocellKit · MuldjordKit · Aasimonster · ShittyKit |
| **SFZ** (5 kit) | Frankensnare (CC0) · Unruly Drums (CC0) · Big Rusty Drums (CC0) · Swirly Drums (CC0) · VSCO-2 CE (CC0, percussioni accessorie) |

Diversità timbrica: 4 kit batteria DrumGizmo multi-mic (vs. 1 originale) + 4 kit
batteria SFZ + 1 libreria accessorie. Il generalization gap resta chiuso anche senza
Salamander e Sommerhack.

### Partizione train/val (Decision Lock CEO 2026-05-23 — Opzione B)

Vedi [`DOSSIER §10.2`](../methodology/DOSSIER_TECNICO.md#validation-set):

- **Train (8 kit):** DRSKit · CrocellKit · MuldjordKit · Aasimonster · Frankensnare ·
  Unruly Drums · Big Rusty Drums · VSCO-2 CE.
- **Val (2 kit "vergini"):** ShittyKit · Swirly Drums — misura la generalizzazione
  cross-kit, non solo cross-session. Holdout esterno = E-GMD (§10.3, F0-T1c).

---
*F0-T1b v1.0 — survey roster kit (2026-05-20). v1.1 — amendment 2026-05-23 (verifica
fonte pre-vendoring + partizione train/val). Licenze rilevate da: drumgizmo.org/wiki,
sfzinstruments.github.io, shop.karoryfer.com, archive.org, github.com (2026-05-20/23).*
