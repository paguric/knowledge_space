"""Comandi base.

``ks base add <path>`` — aggiunge base
``ks base list`` — elenca basi
``ks base remove <name>`` — rimuove
``ks base info <name>`` — config + statistiche
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

logger = logging.getLogger(__name__)

from knowledge_base.base_config import ensure_base_toml, ensure_defaults_toml
from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    normalize_base_name,
    output_json,
    output_table,
    resolve_base_name,
)

app = typer.Typer(help="Gestione basi di conoscenza.")


@app.command()
def add(
    path: str = typer.Argument(help="Path della cartella base."),
    sync: bool = typer.Option(False, "--sync", "-s", help="Indicizza automaticamente i file."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Aggiunge una nuova base al workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)

    try:
        logger.info("Aggiunta base: %s", path)
        kb = manager.add(Path(path))
        base_name = Path(path).name
        logger.info("Base aggiunta: %s", base_name)
        typer.echo(f"Base aggiunta: {base_name}")

        # Scaffolding TOML (idempotente)
        _, ws_created = ensure_defaults_toml(ws.path, ctx.runtime_paths.dot_folder_name)
        if ws_created:
            typer.echo(f"  defaults.toml creato")
        _, base_created = ensure_base_toml(Path(path), ctx.runtime_paths.dot_folder_name)
        if base_created:
            typer.echo(f"  base.toml creato per {base_name}")

        if sync:
            indexed = 0
            logger.info("Sync automatico file per base %s", base_name)
            for entry in Path(path).iterdir():
                if not entry.is_file() or entry.name.startswith("."):
                    continue
                try:
                    file_entry = manager.add_file(base_name, entry)
                    logger.debug("File %s indicizzato: %d chunk", entry.name, len(file_entry.chunks))
                    typer.echo(f"  {file_entry.name} → {len(file_entry.chunks)} chunk")
                    indexed += 1
                except Exception as exc:
                    logger.error("Errore indicizzazione %s: %s", entry.name, exc)
                    typer.echo(f"  {entry.name}: errore — {exc}", err=True)
            logger.info("Sync completato: %d file indicizzati", indexed)
            typer.echo(f"{indexed} file indicizzati")
    except ValueError as exc:
        logger.error("Errore aggiunta base: %s", exc)
        typer.echo(f"Errore: {exc}", err=True)
        raise typer.Exit(1)


@app.command("list")
def list_bases(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Elenca le basi del workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Elenco basi del workspace")

    if json_output:
        output_json([
            {
                "name": name,
                "path": str(kb.path),
                "active": kb.active,
                "files": len(kb.files),
                "chunks": sum(len(f.chunks) for f in kb.files.values()),
                "embedding_model": kb.embedding_model,
            }
            for name, kb in ws.bases.items()
        ])
    else:
        if not ws.bases:
            typer.echo("Nessuna base nel workspace.")
            return
        headers = ["Nome", "Path", "Attiva", "File", "Chunk", "Modello"]
        rows = [
            [
                name,
                str(kb.path),
                "✓" if kb.active else "✗",
                str(len(kb.files)),
                str(sum(len(f.chunks) for f in kb.files.values())),
                kb.embedding_model or "-",
            ]
            for name, kb in ws.bases.items()
        ]
        output_table(headers, rows)


@app.command()
def remove(
    name: str = typer.Argument(help="Nome della base."),
    force: bool = typer.Option(False, "--force", "-y", help="Salta la conferma."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Rimuove una base dal workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)

    name = normalize_base_name(name)
    logger.info("Rimozione base: %s", name)

    # Mostra warning con conferma se la base contiene file/chunk
    if not force:
        kb = ws.bases.get(name)
        n_files = len(kb.files) if kb else 0
        n_chunks = sum(len(f.chunks) for f in kb.files.values()) if kb else 0

        if n_files > 0 or n_chunks > 0:
            typer.echo(
                f"Attenzione: la base '{name}' contiene {n_files} file "
                f"e {n_chunks} chunk indicizzati."
            )
            typer.echo(
                "L'operazione eliminerà definitivamente tutti i chunk "
                "e gli embedding calcolati."
            )
            conferma = typer.confirm("Procedere con la rimozione?", default=False)
            if not conferma:
                logger.info("Rimozione base annullata dall'utente")
                typer.echo("Operazione annullata.")
                raise typer.Exit(0)

    removed = manager.remove(name)
    if removed:
        logger.info("Base rimossa: %s", name)
        typer.echo(f"Base rimossa: {name}")
    else:
        logger.warning("Base non trovata: %s", name)
        typer.echo(f"Base non trovata: {name}", err=True)
        raise typer.Exit(1)


@app.command()
def info(
    name: str = typer.Argument(help="Nome della base."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Mostra dettagli e configurazione di una base."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    name = resolve_base_name(name, workspace=ws)
    logger.info("Info base: %s", name)

    if name not in ws.bases:
        typer.echo(f"Base non trovata: {name}", err=True)
        raise typer.Exit(1)

    kb = ws.bases[name]

    # Carica config se possibile
    config_info = {}
    try:
        config_loader = ctx.base_config_loader_factory(ws.path)
        config = config_loader.load(name)
        config_info = {
            "ingestion_library": config.ingestion.library,
            "chunking_method": config.chunking.method,
            "chunking_size": config.chunking.chunk_size,
            "chunking_overlap": config.chunking.chunk_overlap,
            "embedding_model": config.embedding.model,
        }
    except Exception:
        pass

    n_files = len(kb.files)
    n_chunks = sum(len(f.chunks) for f in kb.files.values())
    active_files = sum(1 for f in kb.files.values() if f.active)

    if json_output:
        output_json({
            "name": name,
            "path": str(kb.path),
            "active": kb.active,
            "files": n_files,
            "active_files": active_files,
            "chunks": n_chunks,
            "registered_model": kb.embedding_model,
            "registered_chunking": kb.chunking_method,
            "registered_ingestion": kb.ingestion_library,
            **config_info,
        })
    else:
        typer.echo(f"Base: {name}")
        typer.echo(f"  Path: {kb.path}")
        typer.echo(f"  Attiva: {'✓' if kb.active else '✗'}")
        typer.echo(f"  File: {n_files} ({active_files} attivi)")
        typer.echo(f"  Chunk: {n_chunks}")
        typer.echo(f"  Modello embedding (registrato): {kb.embedding_model or '-'}")
        typer.echo(f"  Metodo chunking (registrato): {kb.chunking_method or '-'}")
        typer.echo(f"  Libreria ingestion (registrata): {kb.ingestion_library or '-'}")
        if config_info:
            typer.echo("  Configurazione TOML:")
            typer.echo(f"    ingestion.library = {config_info.get('ingestion_library', '-')}")
            typer.echo(f"    chunking.method = {config_info.get('chunking_method', '-')}")
            typer.echo(f"    chunking.chunk_size = {config_info.get('chunking_size', '-')}")
            typer.echo(f"    embedding.model = {config_info.get('embedding_model', '-')}")
