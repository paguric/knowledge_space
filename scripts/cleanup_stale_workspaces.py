#!/usr/bin/env python3
"""Pulisce l'indice globale dei workspace rimuovendo le entry sotto /tmp.

Lo script è idempotente: rieseguirlo non rimuove nulla oltre il /tmp.
Prima di scrivere salva un backup (.bak, .bak1, .bak2, …).

Esecuzione: ``uv run python scripts/cleanup_stale_workspaces.py``
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from knowledge_space.runtime_paths import RuntimePaths


def _next_backup_path(target: Path) -> Path:
    """Restituisce il prossimo path di backup disponibile (.bak, .bak1, …)."""
    bak = target.with_suffix(target.suffix + ".bak")
    if not bak.exists():
        return bak
    i = 1
    while True:
        candidate = target.with_suffix(target.suffix + f".bak{i}")
        if not candidate.exists():
            return candidate
        i += 1


def main() -> None:
    rp = RuntimePaths.default()
    index_path: Path = rp.workspaces_index

    if not index_path.exists():
        print(f"Indice non trovato: {index_path}")
        return

    data = json.loads(index_path.read_text(encoding="utf-8"))
    workspaces: list[str] = data.get("workspaces", [])
    last_ws: str | None = data.get("last_workspace")

    kept: list[str] = []
    removed: list[str] = []
    for ws in workspaces:
        if ws.startswith("/tmp"):
            removed.append(ws)
        else:
            kept.append(ws)

    if not removed:
        print("Nessuna entry sotto /tmp da rimuovere. Indice già pulito.")
        return

    # Aggiorna last_workspace se è stato rimosso
    new_last = last_ws
    if last_ws and last_ws.startswith("/tmp"):
        new_last = kept[0] if kept else None

    # Backup
    backup_path = _next_backup_path(index_path)
    shutil.copy2(index_path, backup_path)
    print(f"Backup salvato: {backup_path}")

    # Scrivi indice pulito
    data["workspaces"] = kept
    data["last_workspace"] = new_last
    index_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Report
    print(f"\n--- Report ---")
    print(f"Entry rimosse: {len(removed)}")
    for r in removed:
        print(f"  - {r}")
    print(f"Entry tenute: {len(kept)}")
    for k in kept:
        print(f"  - {k}")
    print(f"last_workspace: {new_last}")


if __name__ == "__main__":
    main()
