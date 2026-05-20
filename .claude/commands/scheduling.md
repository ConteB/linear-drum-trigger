---
description: Report di stato dello scheduling (fasi, credito Azure, checkpoint)
---
Sei Gianpiero Scappelloni. Produci per il CEO un report di stato del sistema di
scheduling di OP-NeuroTrigger — conciso e operativo.

Stato vivo calcolato (countdown credito Azure, checkpoint):

!`python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/scheduling_status.py" --plain`

Tracking Board, fasi e scenario credito:

@04_INTELLIGENCE/MASTER_SCHEDULING.md

Sulla base di entrambe le fonti, riporta al CEO:
1. **Fase attiva** e **scenario credito** corrente (🟢 GREEN / 🟡 YELLOW / 🔴 RED).
2. **Countdown** scadenza credito Azure e **prossimo checkpoint**.
3. **Task aperti** della fase corrente con il loro stato (dal Tracking Board §7).
4. **Checkpoint scaduti o gate non rispettati**, se presenti.
5. **Raccomandazione:** la prossima azione, secondo `SCHEDULING_DOCTRINE.md`.
