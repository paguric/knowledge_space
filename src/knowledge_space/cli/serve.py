"""Comando ``ks serve``: daemon con watcher filesystem e server MCP.

Avvia un watcher su ogni workspace registrato e un server MCP
per operazioni remote. Resta in foreground finché non riceve
SIGINT/SIGTERM.

Include un ``WorkspacesWatcher`` che monitora ``workspaces.json``
e aggiunge/rimuove dinamicamente i watcher dei workspace quando
l'utente registra o deregistra workspace con ``ks workspace add/remove``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

import typer
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from knowledge_base.workspace_manager import WorkspaceManager, WorkspaceWatcher
from knowledge_space.bootstrap import build_app_context
from knowledge_space.cli.common import get_context
from knowledge_space.runtime_paths import RuntimePaths

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Watcher dinamico su workspaces.json
# --------------------------------------------------------------------------- #


class _WorkspacesFileHandler(FileSystemEventHandler):
    """Handler watchdog che segnala quando ``workspaces.json`` viene modificato o creato."""

    def __init__(self, target_path: Path, change_event: threading.Event) -> None:
        super().__init__()
        self._target = str(target_path)
        self._change_event = change_event

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.src_path == self._target:
            logger.debug("workspaces.json modificato")
            self._change_event.set()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.src_path == self._target:
            logger.debug("workspaces.json creato")
            self._change_event.set()


class WorkspacesWatcher:
    """Monitora ``workspaces.json`` e aggiunge/rimuove workspace watcher dinamicamente.

    Quando il file ``workspaces.json`` cambia (es. ``ks workspace add/remove``),
    ricarica la lista dei workspace dal manager e:
    - avvia un watcher per ogni workspace **nuovo**;
    - ferma il watcher per ogni workspace **rimosso**.

    Args:
        workspaces_json_path: path del file ``workspaces.json``.
        workspace_manager: manager CRUD workspace.
        start_watcher_fn: funzione che, dato il ``Workspace``, avvia e restituisce
            un ``WorkspaceWatcher`` già registrato.
        watchers_ref: lista condivisa (protetta da ``lock``) dei watcher attivi.
        lock: ``threading.Lock`` per proteggere ``watchers_ref``.
        change_event: ``threading.Event`` segnalato dal file handler.
    """

    def __init__(
        self,
        workspaces_json_path: Path,
        workspace_manager: WorkspaceManager,
        start_watcher_fn: Callable[[Path], WorkspaceWatcher],
        watchers_ref: List[WorkspaceWatcher],
        lock: threading.Lock,
        change_event: threading.Event,
    ) -> None:
        self._json_path = workspaces_json_path
        self._workspace_manager = workspace_manager
        self._start_watcher_fn = start_watcher_fn
        self._watchers_ref = watchers_ref
        self._lock = lock
        self._change_event = change_event
        self._stop_event = threading.Event()
        self._observer: Optional[Observer] = None
        self._poll_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Avvia il watchdog su ``workspaces.json`` e il polling loop."""
        # Observer watchdog sul file workspaces.json.
        self._observer = Observer()
        handler = _WorkspacesFileHandler(self._json_path, self._change_event)
        # Osserva la directory padre (workspaces.json potrebbe non esistere ancora).
        watch_dir = self._json_path.parent
        watch_dir.mkdir(parents=True, exist_ok=True)
        self._observer.schedule(handler, str(watch_dir), recursive=False)
        self._observer.start()
        logger.info("WorkspacesWatcher avviato su %s", self._json_path)

        # Thread di polling che reagisce al change_event.
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="workspaces-watcher",
            daemon=True,
        )
        self._poll_thread.start()

    def _poll_loop(self) -> None:
        """Loop che attende il change_event e sincronizza i watcher."""
        while not self._stop_event.is_set():
            # Attendi fino a 1 secondo, oppure finché l'evento non è segnalato.
            self._stop_event.wait(timeout=1.0)
            if self._stop_event.is_set():
                break
            if self._change_event.is_set():
                self._change_event.clear()
                # Debounce: aspetta che la scrittura sia completata.
                time.sleep(0.2)
                self._sync_workspaces()

    def _sync_workspaces(self) -> None:
        """Ricarica la lista workspace e aggiunge/rimuove watcher."""
        try:
            current_paths = set(self._workspace_manager.list())
        except Exception as exc:
            logger.warning("Errore lettura workspace: %s", exc)
            return

        with self._lock:
            active_paths = {w._workspace.path for w in self._watchers_ref}

        # --- Rimuovi watcher per workspace rimossi ---
        with self._lock:
            for w in list(self._watchers_ref):
                if w._workspace.path not in current_paths:
                    try:
                        w.stop()
                    except Exception as exc:
                        logger.warning("Errore stop watcher %s: %s", w._workspace.path, exc)
                    self._watchers_ref.remove(w)
                    logger.info("Watcher rimosso: %s", w._workspace.path)

        # --- Aggiungi watcher per workspace nuovi ---
        for path in current_paths - active_paths:
            if not path.is_dir():
                logger.warning("Workspace non trovato su disco, skip: %s", path)
                continue
            try:
                w = self._start_watcher_fn(path)
                with self._lock:
                    self._watchers_ref.append(w)
                logger.info("Watcher aggiunto: %s", path)
            except Exception as exc:
                logger.error("Errore avvio watcher %s: %s", path, exc)

    def stop(self) -> None:
        """Ferma il watchdog e il polling loop."""
        self._stop_event.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        logger.info("WorkspacesWatcher fermato")


def serve_command(
    host: str = typer.Option("127.0.0.1", help="Indirizzo di bind del server MCP."),
    port: int = typer.Option(8456, help="Porta di ascolto del server MCP."),
    sse: bool = typer.Option(False, "--sse", help="Usa trasporto HTTP (streamable) invece di stdio."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Avvia watcher filesystem + server MCP.

    Ogni workspace registrato viene monitorato per cambiamenti
    nel filesystem (creazione/rimozione cartelle → sync basi).
    Un watcher dinamico su ``workspaces.json`` rileva workspace
    aggiunti o rimossi dopo l'avvio e aggiorna i watcher di
    conseguenza.
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

    # Lock + event per comunicazione tra thread.
    watchers_lock = threading.Lock()
    ws_change_event = threading.Event()

    # Lista condivisa dei watcher attivi (protetta da watchers_lock).
    watchers: list[WorkspaceWatcher] = []

    def _start_and_register(ws_path: Path) -> WorkspaceWatcher:
        """Avvia un watcher per un workspace e lo restituisce."""
        ws = ctx.workspace_manager.load(ws_path)
        w = ctx.workspace_manager.start_watching(ws)
        w.start()
        logger.info("Watcher avviato per: %s", ws_path)
        typer.echo(f"  ✓ Watcher: {ws_path}")
        return w

    # Avvia watcher iniziali per ogni workspace registrato.
    for ws_path in workspaces_paths:
        if not ws_path.is_dir():
            logger.warning("Workspace non trovato su disco, skip: %s", ws_path)
            continue
        w = _start_and_register(ws_path)
        watchers.append(w)

    if not watchers:
        typer.echo("Nessun watcher attivo (workspace non validi).")
        raise typer.Exit(1)

    # Avvia il watcher dinamico su workspaces.json.
    workspaces_json = rp.workspaces_index
    workspaces_watcher = WorkspacesWatcher(
        workspaces_json_path=workspaces_json,
        workspace_manager=ctx.workspace_manager,
        start_watcher_fn=_start_and_register,
        watchers_ref=watchers,
        lock=watchers_lock,
        change_event=ws_change_event,
    )
    workspaces_watcher.start()
    logger.info("WorkspacesWatcher dinamico avviato su %s", workspaces_json)

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
        # Ferma il watcher dinamico.
        workspaces_watcher.stop()
        # Ferma tutti i watcher dei workspace.
        with watchers_lock:
            for w in list(watchers):
                try:
                    w.stop()
                except Exception as exc:
                    logger.warning("Errore stop watcher: %s", exc)
        logger.info("Tutti i watcher fermati")
        typer.echo("Server fermato.")
