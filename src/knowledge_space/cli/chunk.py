"""Comandi chunk.

``ks chunk list --file <base> <filename>`` — elenca chunk
``ks chunk show <chunk_id>`` — mostra testo
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    normalize_base_name,
    output_json,
)

app = typer.Typer(help="Gestione chunk.")


@app.command("list")
def list_chunks(
    base_name: str = typer.Option(..., "--base", "-b", help="Nome della base."),
    file_name: str = typer.Option(..., "--file", "-f", help="Nome del file."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Elenca i chunk di un file."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    base_name = normalize_base_name(base_name)

    if base_name not in ws.bases:
        typer.echo(f"Base non trovata: {base_name}", err=True)
        raise typer.Exit(1)

    kb = ws.bases[base_name]
    if file_name not in kb.files:
        typer.echo(f"File non trovato: {file_name}", err=True)
        raise typer.Exit(1)

    entry = kb.files[file_name]
    file_id = entry.file_id

    if json_output:
        output_json([
            {
                "chunk_id": f"{base_name}::{file_id}::{c.index}",
                "index": c.index,
                "active": c.active,
                "content_hash": c.content_hash,
            }
            for c in entry.chunks
        ])
    else:
        if not entry.chunks:
            typer.echo(f"Nessun chunk per {file_name}.")
            return
        typer.echo(f"Chunk di {file_name} ({len(entry.chunks)} totali):")
        for c in entry.chunks:
            status = "✓" if c.active else "✗"
            chunk_id = f"{base_name}::{file_id}::{c.index}"
            hash_short = c.content_hash[:8] + "..." if c.content_hash else "-"
            typer.echo(f"  [{status}] {chunk_id} (hash={hash_short})")


@app.command()
def show(
    chunk_id: str = typer.Argument(help="ID del chunk (formato: base::file_id::index)."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Mostra il testo di un chunk."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)

    # Parsa chunk_id: base::file_id::index
    parts = chunk_id.split("::")
    if len(parts) != 3:
        typer.echo(
            "Errore: formato chunk_id non valido. Usa: base::file_id::index",
            err=True,
        )
        raise typer.Exit(1)

    base_name, file_id, index_str = parts
    try:
        index = int(index_str)
    except ValueError:
        typer.echo("Errore: indice chunk non valido.", err=True)
        raise typer.Exit(1)

    if base_name not in ws.bases:
        typer.echo(f"Base non trovata: {base_name}", err=True)
        raise typer.Exit(1)

    # Leggi chunk da disco
    chunk_path = (
        ws.path / base_name / ctx.runtime_paths.dot_folder_name
        / "chunks" / file_id / f"{file_id}_chunk_{index}.md"
    )

    if not chunk_path.exists():
        typer.echo(f"Chunk non trovato: {chunk_path}", err=True)
        raise typer.Exit(1)

    text = chunk_path.read_text(encoding="utf-8")
    typer.echo(text)
