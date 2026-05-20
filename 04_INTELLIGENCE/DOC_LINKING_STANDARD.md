---
id: LIN-DT-DOCSTD-001
title: OP-NEUROTRIGGER Doc Standard — Documentation Linking Layer
type: standard
status: LOCKED
phase: cross-cutting
domain: Operations / Knowledge Management
version: 1.1.0
updated: 2026-05-20
tags: [documentation, governance, standard, tooling]
related: [LIN-DT-MSCHED-001, LIN-DT-SCHED-001, LIN-DT-TESTDOC-001]
supersedes: []
---

# OP-NEUROTRIGGER DOC STANDARD — Documentation Linking Layer

> Standard di documentazione del progetto. Definisce *come i documenti si legano tra
> loro* perché la consultazione (in particolare quella dell'agente AI) sia rapida,
> deterministica e a prova di marciume. Decision Lock 2026-05-20 (Executive Briefing
> STRP-001). Vincolante per ogni documento nuovo; retrofit incrementale per gli esistenti.

## 1. Principi

1. **Riferimenti simbolici, non posizionali.** Un riferimento punta a un'**ancora
   nominale stabile**, mai a un numero di sezione ("§6.1") — i numeri si rinumerano e il
   riferimento marcisce. È la radice delle ~30 incoerenze trovate nell'audit del 2026-05-20.
2. **Plain-text, zero build.** Frontmatter YAML + Markdown standard. Nessun generatore di
   sito, nessuno step di compilazione. I documenti restano leggibili e cliccabili su
   GitHub e in locale.
3. **L'indice è generato, non scritto a mano.** Un indice manuale diverge dai documenti.
4. **La coerenza è un gate, non un audit.** I link rotti li trova una macchina (`lychee`),
   in continuo — non un audit umano periodico.

## 2. Frontmatter — blocco YAML obbligatorio

Ogni documento `.md` di progetto inizia con un blocco frontmatter:

```yaml
---
id: LIN-DT-SPEC-F0T4a
title: F0-T4a — Spec Topologia TCN Concreta
type: spec
status: LOCKED
phase: F0
domain: AI / Neural Engineering
version: 1.0.0
updated: 2026-05-20
tags: [tcn, topology, neural, F0-T4a]
related: [LIN-DT-SPEC-F0T2a, LIN-DT-DOSSIER-001, LIN-DT-CHKLST-001]
supersedes: []
---
```

| Campo | Obbl. | Valori |
| :-- | :-- | :-- |
| `id` | sì | `LIN-DT-<TYPE>-<NAME>` (§6) — univoco, immutabile |
| `title` | sì | titolo leggibile |
| `type` | sì | `doctrine` \| `standard` \| `spec` \| `checklist` \| `scheduling` \| `governance` \| `registro` \| `reference` |
| `status` | sì | `DRAFT` \| `ACTIVE` \| `LOCKED` \| `ARCHIVED` \| `SUPERSEDED` |
| `phase` | no | `F0`…`F5` \| `cross-cutting` |
| `domain` | no | dominio funzionale |
| `version` | no | semver del documento |
| `updated` | sì | data ISO `YYYY-MM-DD` dell'ultima modifica |
| `tags` | no | lista — vocabolario libero ma riusato |
| `related` | no | lista di `id` — i documenti legati (alimenta il grafo dell'INDEX) |
| `supersedes` | no | lista di `id` — documenti che questo rende obsoleti |

`related` è la **fonte del grafo**: va tenuto accurato. Un `id` in `related` che non
esiste è un errore segnalato dal generatore dell'INDEX.

## 3. Ancore stabili

<a id="anchors"></a>
Ogni sezione che può essere referenziata da un altro documento espone un'**ancora HTML
nominale**, sulla riga immediatamente sopra l'heading:

```markdown
<a id="loss"></a>
## 6. Loss & Ground Truth
```

- L'ancora è in `kebab-case`, **semanticamente stabile**: non cambia anche se l'heading
  viene rinumerato o riformulato.
- Si usa l'ancora HTML (non la sintassi `{#id}`, che GitHub non renderizza nei file `.md`).
- Non tutte le sezioni necessitano un'ancora — solo quelle effettivamente referenziate.

## 4. Cross-reference — link relativi standard

Un riferimento a un altro documento è un **link Markdown relativo** verso l'ancora stabile:

```markdown
Vedi [F0-T2a — contratto dati §3.4](../docs/methodology/F0-T2a_RECIPE_DATA_CONTRACT_SPEC.md#r-target).
```

- Link relativi standard → **cliccabili su GitHub e in locale, zero build**.
- I wikilink `[[ ]]` sono **vietati** nei file di progetto: GitHub non li renderizza
  (resterebbero testo morto) e processarli richiederebbe un build step.
- Il testo del link porta il riferimento umano ("§3.4"); il target porta l'ancora stabile.

## 5. INDEX generato

<a id="index"></a>
`docs/INDEX.md` è **generato** da `tools/gen_docs_index.py` a partire dai frontmatter:
- tabella di tutti i documenti (`id`, `title`, `type`, `status`, `phase`, path);
- indice per `tag`;
- grafo `related` + **backlink** (chi punta a un documento).

È il primo file da consultare per orientarsi. Può essere importato in `CLAUDE.md` via `@`
per restare sempre in contesto. **Non si edita a mano** — si rigenera.

## 6. Schema degli `id`

`LIN-DT-<TYPE>-<NAME>` · `LIN-DT` = Linear Division / Drum-Trigger.
Esempi in uso: `LIN-DT-MSCHED-001`, `LIN-DT-SCHED-001`, `LIN-DT-SPEC-F0T4a`,
`LIN-DT-TESTDOC-001`, `LIN-DT-DOCSTD-001`. L'`id` è **immutabile** una volta assegnato:
i rename di file non lo toccano, così i `related` non si rompono.

## 7. Validatore — lychee

<a id="validator"></a>
[`lychee`](https://github.com/lycheeverse/lychee) (link checker Rust, binario singolo)
verifica link **e ancore** (`include_fragments = "anchor-only"` in `lychee.toml`).
- **Gate BLOCKING — attivo (F0-T10, 2026-05-20).** Il pre-commit hook `tools/pre-commit`
  esegue `lychee --offline` a ogni commit: un link o un'ancora rotti fanno fallire il
  commit. Rigenera anche `docs/INDEX.md` e blocca se è disallineato dal frontmatter.
- **Installazione del hook:** `sh tools/install-hooks.sh` (collega `.git/hooks/pre-commit`).

## 8. Rollout (Decision Lock — incrementale)

| Stadio | Contenuto | Stato |
| :-- | :-- | :-- |
| **Bootstrap** | Standard + `gen_docs_index.py` + `lychee.toml` + frontmatter sul hot-set | ☑ |
| **F0-T10 (corpo)** | Ancore stabili + conversione riferimenti prosa → link sul hot-set | ☑ 2026-05-20 |
| **Retrofit completo** | Frontmatter su **tutti** i documenti di progetto (33 indicizzati) | ☑ 2026-05-20 |
| **A regime** | `lychee` → **blocking** (pre-commit hook); frontmatter mandatorio per ogni doc nuovo | ☑ 2026-05-20 |

> **F0-T10 chiuso (Decision Lock CEO 2026-05-20).** Il retrofit non è più "opportunistico":
> tutti i documenti di progetto portano il frontmatter, l'INDEX li copre al 100 %, il gate
> `lychee` è blocking. Da qui in avanti il rispetto dello standard è imposto dalla macchina,
> non dalla disciplina manuale.

*Hot-set (entry point di navigazione, ancore + cross-ref convertiti):* `MASTER_SCHEDULING`,
`MASTER_CHECKLIST`, `DOSSIER_TECNICO`, le spec `F0-T*a`, le doctrine (`SCHEDULING`,
`TESTING`), `SUB_AGENT_GOVERNANCE`, questo standard.

---

## 9. Decision Lock (2026-05-20)
Approvato dal CEO (Executive Briefing STRP-001 — Documentation Linking Layer):
1. ✅ Frontmatter YAML obbligatorio (§2).
2. ✅ Ancore HTML nominali stabili (§3); riferimenti simbolici, mai per numero di sezione.
3. ✅ Cross-ref = link relativi Markdown standard (§4); wikilink `[[ ]]` vietati.
4. ✅ `docs/INDEX.md` generato dal frontmatter (§5).
5. ✅ `lychee` come validatore (§7), warn → blocking.
6. ✅ Task `F0-T10` (P2), rollout incrementale (§8).

---
*OP-NEUROTRIGGER Doc Standard v1.0 — STRP-001. **LOCKED 2026-05-20.** Vincolante per ogni
documento nuovo.*
