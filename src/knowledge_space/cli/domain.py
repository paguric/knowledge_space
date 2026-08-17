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
    save_workspace_state,
)

app = typer.Typer(help="Gestione domini.")


# --------------------------------------------------------------------------- #
# Autocomplete
# --------------------------------------------------------------------------- #


def _domain_name_autocomplete(
    ctx: typer.Context,
    args: list[str],
    incomplete: str,
) -> list[tuple[str, str]]:
    """Autocomplete per nomi dominio: suggerisce i domini esistenti."""
    try:
        from knowledge_space.bootstrap import build_app_context
        app_ctx = build_app_context()
        ws = get_workspace(app_ctx, None)
        names = [d.name for d in ws.domains if d.name.startswith(incomplete)]
        return [(n, "") for n in names]
    except Exception:
        return []


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
    ws = get_workspace(ctx, workspace, sync=True)
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
    name: str = typer.Argument(
        help="Nome del dominio.",
        autocompletion=_domain_name_autocomplete,
    ),
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


def _resolve_base_name_for_domain(raw_name: str, ws: Any) -> str:
    """Risolve il nome base per i comandi dominio (bug-024).

    Le basi annidate sono registrate con chiave = path relativo completo
    (es. ``Papers/Base1``); ``resolve_base_name`` la riduce a ``Path.name``
    (``Base1``) e fallisce. Se la risoluzione normale non trova la chiave,
    ritenta con il nome raw esatto.
    """
    resolved = resolve_base_name(raw_name, workspace=ws)
    if resolved in ws.bases:
        return resolved
    if raw_name in ws.bases:
        return raw_name
    return resolved


@app.command("add-base")
def add_base(
    domain_name: str = typer.Argument(
        help="Nome del dominio.",
        autocompletion=_domain_name_autocomplete,
    ),
    base_name: str = typer.Argument(help="Nome della base."),
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-r",
        help="Includi ricorsivamente tutte le sotto-basi annidate.",
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Aggiunge una base a un dominio; con -r anche le sotto-basi."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    domain_name = normalize_base_name(domain_name)
    base_name = _resolve_base_name_for_domain(base_name, ws)

    # Ricorsivo: la base + tutte le chiavi annidate "base/..."
    # (le sotto-basi sono registrate col path relativo completo).
    if recursive:
        targets = [base_name] + sorted(
            b for b in ws.bases if b.startswith(base_name + "/")
        )
    else:
        targets = [base_name]

    added_count = 0
    already = 0
    for target in targets:
        logger.info("Aggiunta base %s al dominio %s", target, domain_name)
        added = ctx.domain_manager.add_base(ws, domain_name, target)
        if added:
            logger.info("Base %s aggiunta al dominio %s", target, domain_name)
            added_count += 1
        else:
            already += 1

    if added_count == 0:
        logger.warning("Errore aggiunta base %s al dominio %s", base_name, domain_name)
        typer.echo(
            f"Errore: dominio '{domain_name}' non trovato, base inesistente, "
            f"o già presente.",
            err=True,
        )
        raise typer.Exit(1)

    if recursive and len(targets) > 1:
        typer.echo(
            f"{added_count} basi aggiunte al dominio '{domain_name}'"
            + (f" ({already} già presenti)" if already else "")
        )
    else:
        typer.echo(f"Base '{base_name}' aggiunta al dominio '{domain_name}'")


@app.command("remove-base")
def remove_base(
    domain_name: str = typer.Argument(
        help="Nome del dominio.",
        autocompletion=_domain_name_autocomplete,
    ),
    base_name: str = typer.Argument(help="Nome della base."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Rimuove una base da un dominio."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    domain_name = normalize_base_name(domain_name)
    base_name = _resolve_base_name_for_domain(base_name, ws)
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


# --------------------------------------------------------------------------- #
# activate / deactivate
# --------------------------------------------------------------------------- #


def _set_domain_active(
    name: str,
    active: bool,
    workspace: Optional[str],
    verbose: bool,
) -> None:
    """Imposta lo stato attivo di un dominio e salva lo stato."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    domain = next((d for d in ws.domains if d.name == name), None)
    if domain is None:
        typer.echo(f"Dominio non trovato: {name}", err=True)
        typer.echo(f"Domini disponibili: {', '.join(d.name for d in ws.domains) or '(nessuno)'}", err=True)
        raise typer.Exit(1)
    domain.active = active
    save_workspace_state(ctx, ws)
    azione = "attivato" if active else "disattivato"
    logger.info("Dominio %s: %s", name, azione)
    typer.echo(f"Dominio {azione}: {name}")


@app.command()
def activate(
    name: str = typer.Argument(help="Nome del dominio."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Attiva un dominio (le basi incluse tornano nella ricerca)."""
    _set_domain_active(name, True, workspace, verbose)


@app.command()
def deactivate(
    name: str = typer.Argument(help="Nome del dominio."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Disattiva un dominio (le basi incluse escluse dalla ricerca)."""
    _set_domain_active(name, False, workspace, verbose)
