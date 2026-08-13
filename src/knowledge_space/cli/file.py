"""Comandi file.

``ks file add <base> <path>`` — ingestion file
``ks file list [--base <name>]`` — elenca file
``ks file remove <base> <name>`` — rimuove
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
    normalize_base_name,
    output_json,
    output_table,
    resolve_base_name,
    save_workspace_state,
)

app = typer.Typer(help="Gestione file indicizzati.")


@app.command()
def add(
    base_name: str = typer.Argument(help="Nome della base."),
    path: str = typer.Argument(help="Path del file da indicizzare."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Esegue la pipeline di ingestion su un file."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)
    base_name = resolve_base_name(base_name, workspace=ws)
    logger.info("Aggiunta file %s alla base %s", path, base_name)

    try:
        entry = manager.add_file(base_name, Path(path))
        logger.info("File indicizzato: %s (%d chunk)", entry.name, len(entry.chunks))
        typer.echo(
            f"File indicizzato: {entry.name} "
            f"(file_id={entry.file_id}, chunk={len(entry.chunks)})"
        )
    except FileNotFoundError as exc:
        logger.error("File non trovato: %s", exc)
        typer.echo(f"Errore: {exc}", err=True)
        raise typer.Exit(1)
    except KeyError as exc:
        logger.error("Base non trovata: %s", exc)
        typer.echo(f"Errore: base non trovata: {exc}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        logger.error("Errore durante l'ingestion: %s", exc)
        typer.echo(f"Errore durante l'ingestion: {exc}", err=True)
        raise typer.Exit(1)


@app.command("list")
def list_files(
    base_name: Optional[str] = typer.Option(None, "--base", "-b", help="Filtra per base."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Elenca i file indicizzati."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Elenco file indicizzati")

    # Raccogli file da tutte le basi o da una specifica
    bases_to_scan = {}
    if base_name:
        base_name = resolve_base_name(base_name, workspace=ws)
        if base_name not in ws.bases:
            typer.echo(f"Base non trovata: {base_name}", err=True)
            raise typer.Exit(1)
        bases_to_scan[base_name] = ws.bases[base_name]
    else:
        bases_to_scan = ws.bases

    all_files = []
    for bname, kb in bases_to_scan.items():
        for fname, entry in kb.files.items():
            all_files.append({
                "base": bname,
                "name": fname,
                "file_id": entry.file_id,
                "active": entry.active,
                "chunks": len(entry.chunks),
                "mtime": entry.mtime,
            })

    if json_output:
        output_json(all_files)
    else:
        if not all_files:
            typer.echo("Nessun file indicizzato.")
            return
        headers = ["Base", "File", "Attivo", "Chunk", "File ID"]
        rows = [
            [
                f["base"],
                f["name"],
                "✓" if f["active"] else "✗",
                str(f["chunks"]),
                f["file_id"][:8] + "..." if f["file_id"] else "-",
            ]
            for f in all_files
        ]
        output_table(headers, rows)


@app.command()
def sync(
    base_name: Optional[str] = typer.Argument(None, help="Nome della base (tutte se omesso)."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Scopre e indicizza i nuovi file nelle basi."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)
    logger.info("Sync file per basi")

    # Senza base specifica, delega a sync_and_ingest del workspace
    # manager: scopre basi nuove, tenta l'adozione dello stato di basi
    # copiate/spostate (bug 020, anche cross-workspace) e indicizza.
    if base_name is None:
        ws = ctx.workspace_manager.sync_and_ingest(ws)
        total_indexed = 0
        for bname, kb in ws.bases.items():
            for fe in kb.files.values():
                total_indexed += len(fe.chunks) if fe.chunks else 0
        logger.info(
            "Sync and ingest completato: %d basi, %d chunk",
            len(ws.bases), total_indexed,
        )
        typer.echo(
            f"Sync completato: {len(ws.bases)} basi, {total_indexed} chunk"
        )
        return

    bases_to_scan = {}
    if base_name:
        base_name = resolve_base_name(base_name, workspace=ws)
        if base_name not in ws.bases:
            typer.echo(f"Base non trovata: {base_name}", err=True)
            raise typer.Exit(1)
        bases_to_scan[base_name] = ws.bases[base_name]
    else:
        bases_to_scan = ws.bases

    total_indexed = 0
    total_skipped = 0

    for bname, kb in bases_to_scan.items():
        base_path = kb.path
        if not base_path.is_dir():
            continue

        for entry in base_path.iterdir():
            if not entry.is_file() or entry.name.startswith("."):
                continue
            if entry.name in kb.files:
                total_skipped += 1
                continue

            # Nuovo file: indicizza
            try:
                file_entry = manager.add_file(bname, entry)
                logger.info("File %s indicizzato in %s: %d chunk", file_entry.name, bname, len(file_entry.chunks))
                typer.echo(
                    f"  [{bname}] {file_entry.name} → "
                    f"{len(file_entry.chunks)} chunk"
                )
                total_indexed += 1
            except Exception as exc:
                logger.error("Errore sync file %s in %s: %s", entry.name, bname, exc)
                typer.echo(f"  [{bname}] {entry.name}: errore — {exc}", err=True)

    if total_indexed == 0 and total_skipped == 0:
        typer.echo("Nessun file trovato nelle basi.")
    else:
        logger.info("Sync completato: %d indicizzati, %d già presenti", total_indexed, total_skipped)
        typer.echo(f"\nIndicizzati: {total_indexed}, già presenti: {total_skipped}")


@app.command()
def remove(
    base_name: str = typer.Argument(help="Nome della base."),
    file_name: str = typer.Argument(help="Nome del file da rimuovere."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Rimuove un file dalla base."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)
    base_name = resolve_base_name(base_name, workspace=ws)
    logger.info("Rimozione file %s dalla base %s", file_name, base_name)

    try:
        removed = manager.remove_file(base_name, file_name)
        if removed:
            logger.info("File rimosso: %s", file_name)
            typer.echo(f"File rimosso: {file_name}")
        else:
            logger.warning("File non trovato: %s", file_name)
            typer.echo(f"File non trovato: {file_name}", err=True)
            raise typer.Exit(1)
    except KeyError as exc:
        logger.error("Base non trovata: %s", exc)
        typer.echo(f"Errore: base non trovata: {exc}", err=True)
        raise typer.Exit(1)


# --------------------------------------------------------------------------- #
# activate / deactivate
# --------------------------------------------------------------------------- #


def _set_file_active(
    base_name: str,
    file_name: str,
    active: bool,
    workspace: Optional[str],
    verbose: bool,
) -> None:
    """Imposta lo stato attivo di un file e salva lo stato."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    base_name = resolve_base_name(base_name, workspace=ws)
    if base_name not in ws.bases:
        typer.echo(f"Base non trovata: {base_name}", err=True)
        raise typer.Exit(1)
    kb = ws.bases[base_name]
    if file_name not in kb.files:
        typer.echo(f"File non trovato: {file_name}", err=True)
        raise typer.Exit(1)
    kb.files[file_name].active = active
    save_workspace_state(ctx, ws)
    azione = "attivato" if active else "disattivato"
    logger.info("File %s: %s", file_name, azione)
    typer.echo(f"File {azione}: {file_name}")


@app.command()
def activate(
    base_name: str = typer.Argument(help="Nome della base."),
    file_name: str = typer.Argument(help="Nome del file."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Attiva un file (incluso nella ricerca)."""
    _set_file_active(base_name, file_name, True, workspace, verbose)


@app.command()
def deactivate(
    base_name: str = typer.Argument(help="Nome della base."),
    file_name: str = typer.Argument(help="Nome del file."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Disattiva un file (escluso dalla ricerca)."""
    _set_file_active(base_name, file_name, False, workspace, verbose)
