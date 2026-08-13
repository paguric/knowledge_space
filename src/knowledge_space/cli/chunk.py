"""Comandi chunk.

``ks chunk list --file <base> <filename>`` — elenca chunk
``ks chunk show <chunk_id>`` — mostra testo
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
    resolve_base_name,
    save_workspace_state,
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
    ws = get_workspace(ctx, workspace, sync=True)
    base_name = resolve_base_name(base_name, workspace=ws)
    logger.info("Elenco chunk per file %s nella base %s", file_name, base_name)

    if base_name not in ws.bases:
        logger.warning("Base non trovata: %s", base_name)
        typer.echo(f"Base non trovata: {base_name}", err=True)
        raise typer.Exit(1)

    kb = ws.bases[base_name]
    if file_name not in kb.files:
        logger.warning("File non trovato: %s", file_name)
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
    ws = get_workspace(ctx, workspace, sync=True)
    logger.info("Visualizzazione chunk: %s", chunk_id)

    # Parsa chunk_id: base::file_id::index
    parts = chunk_id.split("::")
    if len(parts) != 3:
        logger.error("Formato chunk_id non valido: %s", chunk_id)
        typer.echo(
            "Errore: formato chunk_id non valido. Usa: base::file_id::index",
            err=True,
        )
        raise typer.Exit(1)

    base_name, file_id, index_str = parts
    try:
        index = int(index_str)
    except ValueError:
        logger.error("Indice chunk non valido: %s", index_str)
        typer.echo("Errore: indice chunk non valido.", err=True)
        raise typer.Exit(1)

    if base_name not in ws.bases:
        logger.warning("Base non trovata: %s", base_name)
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


# --------------------------------------------------------------------------- #
# activate / deactivate
# --------------------------------------------------------------------------- #


def _parse_chunk_id(chunk_id: str):
    """Scompone ``<base>::<file_id>::<index>`` in (base_name, file_id, index)."""
    parts = chunk_id.split("::")
    if len(parts) != 3:
        return None
    base_name, file_id, index = parts
    try:
        return base_name, file_id, int(index)
    except ValueError:
        return None


def _set_chunk_active(
    chunk_id: str,
    active: bool,
    workspace: Optional[str],
    verbose: bool,
) -> None:
    """Imposta lo stato attivo di un chunk e salva lo stato."""
    parsed = _parse_chunk_id(chunk_id)
    if parsed is None:
        typer.echo(f"Chunk id non valido: {chunk_id} (atteso base::file_id::index)", err=True)
        raise typer.Exit(1)
    base_name, file_id, index = parsed

    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    base_name = resolve_base_name(base_name, workspace=ws)
    if base_name not in ws.bases:
        typer.echo(f"Base non trovata: {base_name}", err=True)
        raise typer.Exit(1)
    kb = ws.bases[base_name]
    entry = next((f for f in kb.files.values() if f.file_id == file_id), None)
    if entry is None:
        typer.echo(f"File con file_id {file_id} non trovato nella base {base_name}", err=True)
        raise typer.Exit(1)
    chunk = next((c for c in entry.chunks if c.index == index), None)
    if chunk is None:
        typer.echo(f"Chunk {index} non trovato nel file {entry.name}", err=True)
        raise typer.Exit(1)

    chunk.active = active
    save_workspace_state(ctx, ws)
    azione = "attivato" if active else "disattivato"
    logger.info("Chunk %s: %s", chunk_id, azione)
    typer.echo(f"Chunk {azione}: {chunk_id}")


@app.command()
def activate(
    chunk_id: str = typer.Argument(help="Chunk id (base::file_id::index)."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Attiva un chunk (incluso nella ricerca)."""
    _set_chunk_active(chunk_id, True, workspace, verbose)


@app.command()
def deactivate(
    chunk_id: str = typer.Argument(help="Chunk id (base::file_id::index)."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Disattiva un chunk (escluso dalla ricerca)."""
    _set_chunk_active(chunk_id, False, workspace, verbose)
