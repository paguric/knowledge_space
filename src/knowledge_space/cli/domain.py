"""Comandi domain.

``ks domain new <name>`` — crea dominio
``ks domain list`` — elenca domini
``ks domain remove <name>`` — rimuove
``ks domain add-base <name> <base>`` — assegna base
``ks domain remove-base <name> <base>`` — rimuove base
``ks domain auto-generate`` — genera da struttura cartelle
"""

from __future__ import annotations

import logging
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
)

app = typer.Typer(help="Gestione domini.")


@app.command()
def new(
    name: str = typer.Argument(help="Nome del dominio."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Crea un nuovo dominio nel workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Creazione dominio: %s", name)

    try:
        domain = ctx.domain_manager.create(ws, name)
        logger.info("Dominio creato: %s", domain.name)
        typer.echo(f"Dominio creato: {domain.name}")
    except ValueError as exc:
        logger.error("Errore creazione dominio: %s", exc)
        typer.echo(f"Errore: {exc}", err=True)
        raise typer.Exit(1)


@app.command("list")
def list_domains(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Elenca i domini del workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Elenco domini")

    if json_output:
        output_json([
            {"name": d.name, "active": d.active, "bases": d.base_names}
            for d in ws.domains
        ])
    else:
        if not ws.domains:
            typer.echo("Nessun dominio nel workspace.")
            return
        headers = ["Nome", "Attivo", "Basi"]
        rows = [
            [d.name, "✓" if d.active else "✗", ", ".join(d.base_names) or "-"]
            for d in ws.domains
        ]
        output_table(headers, rows)


@app.command()
def remove(
    name: str = typer.Argument(help="Nome del dominio."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Rimuove un dominio."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Rimozione dominio: %s", name)

    removed = ctx.domain_manager.delete(ws, name)
    if removed:
        logger.info("Dominio rimosso: %s", name)
        typer.echo(f"Dominio rimosso: {name}")
    else:
        logger.warning("Dominio non trovato: %s", name)
        typer.echo(f"Dominio non trovato: {name}", err=True)
        raise typer.Exit(1)


@app.command("add-base")
def add_base(
    domain_name: str = typer.Argument(help="Nome del dominio."),
    base_name: str = typer.Argument(help="Nome della base."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Aggiunge una base a un dominio."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    base_name = resolve_base_name(base_name, workspace=ws)
    logger.info("Aggiunta base %s al dominio %s", base_name, domain_name)

    added = ctx.domain_manager.add_base(ws, domain_name, base_name)
    if added:
        logger.info("Base %s aggiunta al dominio %s", base_name, domain_name)
        typer.echo(f"Base '{base_name}' aggiunta al dominio '{domain_name}'")
    else:
        logger.warning("Errore aggiunta base %s al dominio %s", base_name, domain_name)
        typer.echo(
            f"Errore: dominio '{domain_name}' non trovato, base inesistente, o già presente.",
            err=True,
        )
        raise typer.Exit(1)


@app.command("remove-base")
def remove_base(
    domain_name: str = typer.Argument(help="Nome del dominio."),
    base_name: str = typer.Argument(help="Nome della base."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Rimuove una base da un dominio."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    base_name = resolve_base_name(base_name, workspace=ws)
    logger.info("Rimozione base %s dal dominio %s", base_name, domain_name)

    removed = ctx.domain_manager.remove_base(ws, domain_name, base_name)
    if removed:
        logger.info("Base %s rimossa dal dominio %s", base_name, domain_name)
        typer.echo(f"Base '{base_name}' rimossa dal dominio '{domain_name}'")
    else:
        logger.warning("Errore rimozione base %s dal dominio %s", base_name, domain_name)
        typer.echo(
            f"Errore: dominio '{domain_name}' non trovato o base non presente.",
            err=True,
        )
        raise typer.Exit(1)


@app.command("auto-generate")
def auto_generate(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Genera domini dalla struttura delle cartelle del workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Auto-generazione domini da struttura cartelle")

    ws = ctx.domain_manager.auto_generate(ws)
    logger.info("Domini generati: %d", len(ws.domains))
    typer.echo(f"Domini generati: {len(ws.domains)}")
    for d in ws.domains:
        typer.echo(f"  {d.name}: {', '.join(d.base_names) or '(vuoto)'}")
