"""Comandi base.

``ks base add <path>`` — aggiunge base
``ks base list`` — elenca basi
``ks base remove <name>`` — rimuove
``ks base info <name>`` — config + statistiche
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    output_json,
    output_table,
)

app = typer.Typer(help="Gestione basi di conoscenza.")


@app.command()
def add(
    path: str = typer.Argument(help="Path della cartella base."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Aggiunge una nuova base al workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)

    try:
        kb = manager.add(Path(path))
        typer.echo(f"Base aggiunta: {Path(path).name}")
    except ValueError as exc:
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
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Rimuove una base dal workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)

    removed = manager.remove(name)
    if removed:
        typer.echo(f"Base rimossa: {name}")
    else:
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
