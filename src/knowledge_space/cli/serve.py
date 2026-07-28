"""Comando ``ks serve``: daemon con watcher filesystem e server MCP.

Avvia un watcher su ogni workspace registrato e un server MCP
per operazioni remote. Resta in foreground finché non riceve
SIGINT/SIGTERM.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

import typer

from knowledge_base.workspace_manager import WorkspaceManager
from knowledge_space.bootstrap import build_app_context
from knowledge_space.cli.common import get_context
from knowledge_space.runtime_paths import RuntimePaths

logger = logging.getLogger(__name__)


def serve_command(
    host: str = typer.Option("127.0.0.1", help="Indirizzo di bind per SSE."),
    port: int = typer.Option(8080, help="Porta di ascolto per SSE."),
    sse: bool = typer.Option(False, "--sse", help="Usa trasporto SSE invece di stdio."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Avvia watcher filesystem + server MCP.

    Ogni workspace registrato viene monitorato per cambiamenti
    nel filesystem (creazione/rimozione cartelle → sync basi).
    Il server MCP espone le operazioni principali per client remoti.
    """
    ctx = get_context(verbose=verbose)
    rp = ctx.runtime_paths

    # Carica i workspace registrati.
    workspaces_paths = ctx.workspace_manager.list()
    if not workspaces_paths:
        typer.echo("Nessun workspace registrato. Usa 'ks workspace add <path>' prima.")
        raise typer.Exit(1)

    typer.echo(f"Workspace monitorati: {len(workspaces_paths)}")

    # Avvia watcher per ogni workspace.
    watchers = []
    for ws_path in workspaces_paths:
        if not ws_path.is_dir():
            logger.warning("Workspace non trovato su disco, skip: %s", ws_path)
            continue
        ws = ctx.workspace_manager.load(ws_path)
        watcher = ctx.workspace_manager.start_watching(ws)
        watcher.start()
        watchers.append(watcher)
        logger.info("Watcher avviato per: %s", ws_path)
        typer.echo(f"  ✓ Watcher: {ws_path}")

    if not watchers:
        typer.echo("Nessun watcher attivo (workspace non validi).")
        raise typer.Exit(1)

    # Avvia il server MCP.
    from mcp_server.server import run_sse, run_stdio

    def _config_path_for(ws_path: Path) -> Path:
        return rp.workspace_state_file(ws_path)

    typer.echo(f"Server MCP in avvio ({'SSE' if sse else 'stdio'})...")

    try:
        if sse:
            asyncio.run(
                run_sse(
                    ctx.workspace_manager,
                    _config_path_for,
                    state_home=rp.state_home,
                    host=host,
                    port=port,
                )
            )
        else:
            asyncio.run(
                run_stdio(
                    ctx.workspace_manager,
                    _config_path_for,
                    state_home=rp.state_home,
                )
            )
    except KeyboardInterrupt:
        logger.info("Interruzione da tastiera")
    except Exception as exc:
        logger.error("Errore server MCP: %s", exc)
        typer.echo(f"Errore: {exc}", err=True)
    finally:
        # Ferma tutti i watcher.
        for w in watchers:
            try:
                w.stop()
                logger.info("Watcher fermato")
            except Exception as exc:
                logger.warning("Errore stop watcher: %s", exc)
        typer.echo("Server fermato.")
