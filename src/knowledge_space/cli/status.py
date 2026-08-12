"""Comando status.

``ks status`` — panoramica workspace attivo, basi, file, chunk
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

logger = logging.getLogger(__name__)

from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    output_json,
    resolve_workspace_path,
)


def status_command(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Mostra una panoramica dello stato del workspace."""
    ctx = get_context(verbose=verbose)
    logger.info("Visualizzazione stato workspace")

    # Workspace info
    ws_path = None
    try:
        ws_path = resolve_workspace_path(ctx, workspace)
    except Exception:
        pass

    if ws_path is None:
        logger.warning("Nessun workspace trovato")
        if json_output:
            output_json({"error": "Nessun workspace trovato."})
        else:
            typer.echo("Nessun workspace trovato. Usa 'ks workspace add <path>'.")
        return

    ws = get_workspace(ctx, workspace, sync=True)

    # Il workspace "attivo" è l'ultimo usato nel GlobalIndex
    active_ws = ctx.workspace_manager.get_last_workspace()
    is_active = active_ws is not None and Path(active_ws).resolve() == Path(ws.path).resolve()

    # Statistiche
    n_bases = len(ws.bases)
    n_domains = len(ws.domains)
    n_files = sum(len(kb.files) for kb in ws.bases.values())
    n_chunks = sum(
        sum(len(f.chunks) for f in kb.files.values())
        for kb in ws.bases.values()
    )
    active_bases = sum(1 for kb in ws.bases.values() if kb.active)
    active_files = sum(
        sum(1 for f in kb.files.values() if f.active)
        for kb in ws.bases.values()
    )

    # Modelli in uso
    models = set()
    for kb in ws.bases.values():
        if kb.embedding_model:
            models.add(kb.embedding_model)

    if json_output:
        output_json({
            "workspace": str(ws.path),
            "active": is_active,
            "bases": n_bases,
            "active_bases": active_bases,
            "domains": n_domains,
            "files": n_files,
            "active_files": active_files,
            "chunks": n_chunks,
            "embedding_models": sorted(models),
        })
    else:
        attivo = " [attivo]" if is_active else " [inattivo]"
        typer.echo(f"Workspace: {ws.path}{attivo}")
        if active_ws is not None and not is_active:
            typer.echo(f"  Attivo:    {active_ws}")
        typer.echo()
        typer.echo(f"  Basi:         {n_bases} ({active_bases} attive)")
        typer.echo(f"  Domini:       {n_domains}")
        typer.echo(f"  File:         {n_files} ({active_files} attivi)")
        typer.echo(f"  Chunk:        {n_chunks}")
        if models:
            typer.echo(f"  Modelli:      {', '.join(sorted(models))}")
        typer.echo()

        # Dettaglio basi
        if ws.bases:
            typer.echo("  Basi:")
            for name, kb in ws.bases.items():
                status_icon = "✓" if kb.active else "✗"
                n_kb_files = len(kb.files)
                n_kb_chunks = sum(len(f.chunks) for f in kb.files.values())
                model = kb.embedding_model or "-"
                typer.echo(
                    f"    [{status_icon}] {name}: "
                    f"{n_kb_files} file, {n_kb_chunks} chunk, modello={model}"
                )
