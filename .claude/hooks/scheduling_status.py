#!/usr/bin/env python3
"""
SCHEDULING MONITOR — OP-NeuroTrigger (drum-trigger-fresh)

Hook SessionStart: calcola e inietta nel contesto dell'agente lo stato vivo
dello scheduling (countdown credito Azure, checkpoint imminenti o scaduti).

Uso:
  python3 scheduling_status.py           -> output JSON per l'hook SessionStart
  python3 scheduling_status.py --plain   -> output testuale leggibile (comando /scheduling)

NOTA: le date sono LOCKED (Decision Lock 2026-05-20).
Sincronizzare con 04_INTELLIGENCE/MASTER_SCHEDULING.md §1 e §3 se cambiano.
"""
import json
import sys
from datetime import date

# --- Date bloccate ---
AZURE_EXPIRY = date(2026, 6, 19)    # scadenza credito Azure $200
V1_TARGET = date(2026, 10, 20)      # orizzonte v1.0 Early-Access $99
CHECKPOINTS = [
    ("CP-1", date(2026, 5, 30)),
    ("CP-2", date(2026, 6, 9)),
    ("CP-3", date(2026, 6, 14)),
]


def human_delta(n):
    """Rende un numero di giorni in linguaggio naturale."""
    if n > 0:
        return f"tra {n} gg"
    if n == 0:
        return "OGGI"
    return f"{-n} gg fa"


def build_report():
    today = date.today()
    d_exp = (AZURE_EXPIRY - today).days
    d_v1 = (V1_TARGET - today).days

    lines = [
        "═══ SCHEDULING MONITOR — OP-NEUROTRIGGER ═══",
        f"Oggi: {today.isoformat()}",
        f"Credito Azure $200 — scade {AZURE_EXPIRY.isoformat()} ({human_delta(d_exp)})",
        "Checkpoint del credito:",
    ]

    next_cp_assigned = False
    for name, d in CHECKPOINTS:
        delta = (d - today).days
        if delta < 0:
            flag = "  ⚠️ passato — verifica che la review sia stata svolta"
        elif not next_cp_assigned:
            flag = "  ← PROSSIMO"
            next_cp_assigned = True
        else:
            flag = ""
        lines.append(f"  {name}  {d.isoformat()}  ({human_delta(delta)}){flag}")

    lines.append(f"Orizzonte v1.0 Early-Access: {V1_TARGET.isoformat()} ({human_delta(d_v1)})")
    lines.append(
        "Fase attiva, scenario credito e stato task: "
        "04_INTELLIGENCE/MASTER_SCHEDULING.md §7 (Tracking Board)"
    )

    alerts = []
    if d_exp < 0:
        alerts.append("⚠️ CREDITO AZURE SCADUTO — verificare il consumo effettivo.")
    elif d_exp <= 5:
        alerts.append(
            "⚠️ Scadenza credito imminente — fase credit-soak "
            "(deployment Tier 2/3, vedi MASTER_SCHEDULING §4)."
        )
    for name, d in CHECKPOINTS:
        delta = (d - today).days
        if 0 <= delta <= 2:
            alerts.append(
                f"⚠️ {name} imminente ({human_delta(delta)}) "
                "— preparare il bivio decisionale del checkpoint."
            )
    if alerts:
        lines.append("--- ALERT ---")
        lines.extend(alerts)

    return "\n".join(lines)


def main():
    report = build_report()
    if "--plain" in sys.argv:
        print(report)
    else:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": report,
            }
        }))


if __name__ == "__main__":
    main()
