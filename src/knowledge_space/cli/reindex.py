"""Comando reindex.

``ks reindex <base>`` — reindicizza base
``ks reindex --all`` — tutte le basi
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    normalize_base_name,
)


def reindex_command(
    base_name: Optional[str] = typer.Argument(None, help="Nome della base da reindicizzare."),
    all_bases: bool = typer.Option(False, "--all", "-a", help="Reindicizza tutte le basi."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Reindicizza una o tutte le basi."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)

    if not all_bases and not base_name:
        typer.echo("Specifica una base o usa --all.", err=True)
        raise typer.Exit(1)

    bases_to_reindex = []
    if all_bases:
        bases_to_reindex = list(ws.bases.keys())
    elif base_name:
        base_name = normalize_base_name(base_name)
        if base_name not in ws.bases:
            typer.echo(f"Base non trovata: {base_name}", err=True)
            raise typer.Exit(1)
        bases_to_reindex.append(base_name)

    for bname in bases_to_reindex:
        kb = ws.bases[bname]
        typer.echo(f"Reindicizzazione base: {bname}")

        if not kb.files:
            typer.echo(f"  Nessun file nella base {bname}, skip.")
            continue

        file_names = list(kb.files.keys())
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
                result = manager.add_file(bname, file_path)
                typer.echo(f"  ✓ {fname} ({len(result.chunks)} chunk)")
            except Exception as exc:
                typer.echo(f"  ✗ {fname}: {exc}", err=True)
                errors += 1

        if errors:
            typer.echo(f"  Completato con {errors} errori.")
        else:
            typer.echo(f"  Completato con successo.")
