"""Comando reindex.

``ks reindex <base>`` — reindicizza base
``ks reindex --all`` — tutte le basi
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
    resolve_base_name,
)


def reindex_command(
    base_name: Optional[str] = typer.Argument(None, help="Nome della base da reindicizzare."),
    all_bases: bool = typer.Option(False, "--all", "-a", help="Reindicizza tutte le basi."),
    model_change: bool = typer.Option(False, "--model-change", help="Modello embedding cambiato: riusa il Markdown salvato (nessuna riconversione)."),
    chunking_change: bool = typer.Option(False, "--chunking-change", help="Chunking cambiato: riusa il Markdown salvato (nessuna riconversione)."),
    ingestion_change: bool = typer.Option(False, "--ingestion-change", help="Ingestion cambiata: riconverte tutto dal sorgente."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Reindicizza una o tutte le basi.

    I flag indicano quale parte della pipeline è cambiata e quindi quanto
    deve essere rifatto (feat-007):

    - nessun flag: pipeline completa (docling se il sorgente è cambiato,
      Markdown salvato altrimenti);
    - ``--chunking-change`` / ``--model-change``: rilegge il Markdown
      salvato, ri-chunka / ri-embedda senza riconvertire;
    - ``--ingestion-change``: riconverte tutto dal sorgente.
    """
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)
    logger.info("Reindicizzazione basi")

    if ingestion_change:
        markdown_mode = "reconvert"
    elif model_change or chunking_change:
        markdown_mode = "reuse"
    else:
        markdown_mode = "auto"
    # Con un flag esplicito il reindex è il comando di sblocco: bypassa il
    # blocco cambio config (altrimenti ConfigChangeBlockedError non lascerebbe
    # mai sbloccare la base).
    skip_block = markdown_mode != "auto"

    if not all_bases and not base_name:
        logger.warning("Nessuna base specificata per reindex")
        typer.echo("Specifica una base o usa --all.", err=True)
        raise typer.Exit(1)

    bases_to_reindex = []
    if all_bases:
        bases_to_reindex = list(ws.bases.keys())
    elif base_name:
        requested = base_name
        base_name = resolve_base_name(base_name, workspace=ws)
        # Bug-024: basi annidate (clienti/cliente-a) — resolve riduce il
        # path; se la chiave non esiste riprova col nome raw.
        if base_name not in ws.bases and requested in ws.bases:
            base_name = requested
        if base_name not in ws.bases:
            typer.echo(f"Base non trovata: {base_name}", err=True)
            raise typer.Exit(1)
        bases_to_reindex.append(base_name)

    for bname in bases_to_reindex:
        kb = ws.bases[bname]
        logger.info("Reindicizzazione base: %s", bname)
        typer.echo(f"Reindicizzazione base: {bname}")

        if not kb.files:
            logger.info("Nessun file nella base %s, skip", bname)
            typer.echo(f"  Nessun file nella base {bname}, skip.")
            continue

        file_names = list(kb.files.keys())
        logger.info("File da reindicizzare in %s: %d", bname, len(file_names))
        typer.echo(f"  File da reindicizzare: {len(file_names)}")

        errors = 0
        for fname in file_names:
            entry = kb.files[fname]
            file_path = kb.path / fname
            if not file_path.exists():
                typer.echo(f"  ⚠ File non trovato su disco: {fname}", err=True)
                errors += 1
                continue

            try:
                result = manager.add_file(
                    bname, file_path,
                    markdown_mode=markdown_mode,
                    skip_config_change_block=skip_block,
                )
                logger.info("File %s reindicizzato: %d chunk", fname, len(result.chunks))
                typer.echo(f"  ✓ {fname} ({len(result.chunks)} chunk)")
            except Exception as exc:
                logger.error("Errore reindicizzazione %s: %s", fname, exc)
                typer.echo(f"  ✗ {fname}: {exc}", err=True)
                errors += 1

        if errors:
            logger.warning("Reindicizzazione %s completata con %d errori", bname, errors)
            typer.echo(f"  Completato con {errors} errori.")
        else:
            logger.info("Reindicizzazione %s completata con successo", bname)
            typer.echo(f"  Completato con successo.")
