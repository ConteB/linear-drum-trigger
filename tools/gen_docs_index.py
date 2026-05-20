#!/usr/bin/env python3
"""gen_docs_index.py — genera docs/INDEX.md dal frontmatter dei documenti.

Parte dell'OP-NEUROTRIGGER Doc Standard (LIN-DT-DOCSTD-001 §5).
Nessuna dipendenza esterna: il frontmatter ha uno schema piatto e si parsa a mano.

Uso:  python3 tools/gen_docs_index.py        (dalla root del repo)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Radici scansionate per i documenti di progetto.
ROOTS = ["04_INTELLIGENCE", "docs"]
ROOT_FILES = ["MASTER_CHECKLIST.md"]
OUTPUT = Path("docs/INDEX.md")
LIST_FIELDS = {"tags", "related", "supersedes"}


def parse_frontmatter(text: str) -> dict | None:
    """Estrae il blocco frontmatter YAML piatto. None se assente."""
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None
    fm: dict = {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return fm
        raw = lines[i].strip()
        if not raw or raw.startswith("#") or ":" not in raw:
            continue
        key, _, val = raw.partition(":")
        key, val = key.strip(), val.strip()
        if key in LIST_FIELDS:
            val = val.strip("[]").strip()
            fm[key] = [v.strip() for v in val.split(",") if v.strip()] if val else []
        else:
            fm[key] = val
    return None  # blocco non chiuso


def collect(repo: Path) -> tuple[list[dict], list[Path]]:
    """Restituisce (documenti con frontmatter, file senza frontmatter)."""
    md_files: list[Path] = []
    for root in ROOTS:
        md_files += sorted((repo / root).rglob("*.md"))
    md_files += [repo / f for f in ROOT_FILES if (repo / f).exists()]

    docs, no_fm = [], []
    for path in md_files:
        if path.resolve() == (repo / OUTPUT).resolve():
            continue
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        if fm and "id" in fm:
            fm["_path"] = path.relative_to(repo).as_posix()
            docs.append(fm)
        else:
            no_fm.append(path.relative_to(repo))
    return docs, no_fm


def build_index(docs: list[dict], no_fm: list[Path]) -> tuple[str, list[str]]:
    by_id = {d["id"]: d for d in docs}
    warnings: list[str] = []

    # Backlink: chi dichiara `related` verso un dato id.
    backlinks: dict[str, list[str]] = {d["id"]: [] for d in docs}
    for d in docs:
        for rel in d.get("related", []):
            if rel in backlinks:
                backlinks[rel].append(d["id"])
            else:
                warnings.append(f"{d['id']}: related '{rel}' inesistente")

    out = [
        "---",
        "id: LIN-DT-INDEX-001",
        "title: Documentation Index — OP-NEUROTRIGGER",
        "type: reference",
        "status: ACTIVE",
        "phase: cross-cutting",
        "updated: auto-generato",
        "tags: [index, documentation]",
        "related: [LIN-DT-DOCSTD-001]",
        "---",
        "",
        "# 🗂️ DOCUMENTATION INDEX — OP-NEUROTRIGGER",
        "",
        "> **File generato** da `tools/gen_docs_index.py` (Doc Standard LIN-DT-DOCSTD-001 §5).",
        "> Non editare a mano — rigenerare. Rilancia lo script dopo ogni modifica al frontmatter.",
        "",
        f"Documenti indicizzati: **{len(docs)}** · senza frontmatter: **{len(no_fm)}**.",
        "",
        "## Documenti",
        "",
        "| id | title | type | status | phase | path |",
        "| :-- | :-- | :-- | :-- | :-- | :-- |",
    ]
    for d in sorted(docs, key=lambda x: x["id"]):
        out.append(
            f"| `{d['id']}` | {d.get('title','')} | {d.get('type','')} "
            f"| {d.get('status','')} | {d.get('phase','—')} | `{d['_path']}` |"
        )

    # Indice per tag.
    tags: dict[str, list[str]] = {}
    for d in docs:
        for t in d.get("tags", []):
            tags.setdefault(t, []).append(d["id"])
    out += ["", "## Indice per tag", ""]
    for t in sorted(tags):
        out.append(f"- **{t}** — " + ", ".join(f"`{i}`" for i in sorted(tags[t])))

    # Grafo: related + backlink.
    out += ["", "## Grafo dei riferimenti", "",
            "| documento | related → | ← backlink |", "| :-- | :-- | :-- |"]
    for d in sorted(docs, key=lambda x: x["id"]):
        rel = ", ".join(f"`{r}`" for r in d.get("related", [])) or "—"
        bl = ", ".join(f"`{b}`" for b in sorted(backlinks[d["id"]])) or "—"
        out.append(f"| `{d['id']}` | {rel} | {bl} |")

    # supersedes
    sup = [(d["id"], d["supersedes"]) for d in docs if d.get("supersedes")]
    if sup:
        out += ["", "## Catena di supersession", ""]
        for did, s in sorted(sup):
            out.append(f"- `{did}` supersedes " + ", ".join(f"`{x}`" for x in s))

    if no_fm:
        out += ["", "## ⚠️ Documenti senza frontmatter (backlog retrofit F0-T10)", ""]
        for p in sorted(no_fm):
            out.append(f"- `{p.as_posix()}`")

    out += ["", "---", "*Generato da `tools/gen_docs_index.py`.*", ""]
    return "\n".join(out), warnings


def main() -> int:
    repo = Path.cwd()
    docs, no_fm = collect(repo)
    content, warnings = build_index(docs, no_fm)
    (repo / OUTPUT).write_text(content, encoding="utf-8")
    print(f"✓ {OUTPUT} generato — {len(docs)} doc con frontmatter, {len(no_fm)} senza.")
    for w in warnings:
        print(f"  ⚠️  {w}", file=sys.stderr)
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
