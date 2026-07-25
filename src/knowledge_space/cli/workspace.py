"""Comandi workspace.

``ks workspace add <path>`` — registra workspace
``ks workspace list`` — elenca workspace
``ks workspace remove <path>`` — rimuove
``ks workspace info [<path>]`` — mostra stato
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from knowledge_space.cli.common import (
    get_context,
    output_json,
    output_table,
    resolve_workspace_path,
)

app = typer.Typer(help="Gestione workspace.")


@app.command()
def add(
    path: str = typer.Argument(help="Path del workspace da registrare."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Registra un nuovo workspace."""
    ctx = get_context(verbose=verbose)
    ws_path = Path(path).resolve()

    if not ws_path.is_dir():
        typer.echo(f"Errore: la cartella non esiste: {ws_path}", err=True)
        raise typer.Exit(1)

    added = ctx.workspace_manager.add(ws_path)
    if added:
        typer.echo(f"Workspace registrato: {ws_path}")
    else:
        typer.echo(f"Workspace già registrato: {ws_path}")


@app.command("list")
def list_workspaces(
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Elenca i workspace registrati."""
    ctx = get_context(verbose=verbose)
    workspaces = ctx.workspace_manager.list()

    if json_output:
        output_json([str(p) for p in workspaces])
    else:
        if not workspaces:
            typer.echo("Nessun workspace registrato.")
            return
        for ws in workspaces:
            typer.echo(str(ws))


@app.command()
def remove(
    path: str = typer.Argument(help="Path del workspace da rimuovere."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Rimuove un workspace dal registro (non cancella i file)."""
    ctx = get_context(verbose=verbose)
    ws_path = Path(path).resolve()

    removed = ctx.workspace_manager.remove(ws_path)
    if removed:
        typer.echo(f"Workspace rimosso: {ws_path}")
    else:
        typer.echo(f"Workspace non trovato: {ws_path}", err=True)
        raise typer.Exit(1)


@app.command()
def info(
    path: Optional[str] = typer.Argument(None, help="Path del workspace (opzionale)."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Mostra informazioni sul workspace."""
    ctx = get_context(verbose=verbose)
    ws_path = resolve_workspace_path(ctx, path)
    workspace = ctx.workspace_manager.load(ws_path)

    n_bases = len(workspace.bases)
    n_domains = len(workspace.domains)
    n_files = sum(len(kb.files) for kb in workspace.bases.values())
    n_chunks = sum(
        sum(len(f.chunks) for f in kb.files.values())
        for kb in workspace.bases.values()
    )

    if json_output:
        output_json({
            "path": str(workspace.path),
            "bases": n_bases,
            "domains": n_domains,
            "files": n_files,
            "chunks": n_chunks,
        })
    else:
        typer.echo(f"Workspace: {workspace.path}")
        typer.echo(f"  Basi: {n_bases}")
        typer.echo(f"  Domini: {n_domains}")
        typer.echo(f"  File: {n_files}")
        typer.echo(f"  Chunk: {n_chunks}")
