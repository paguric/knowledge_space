"""Logica operativa sui workspace.

Il :class:`WorkspaceManager` incapsula le operazioni di CRUD sui workspace
e la sincronizzazione del modello col filesystem, usando i loader di
:mod:`knowledge_base.persistence`. Non conosce né il nome dell'app né i
path XDG: riceve ``GlobalIndex`` e una funzione ``config_path_for`` che
mappa un path di workspace nel path del suo ``config.json``.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, List, Optional

from knowledge_base.models import KnowledgeBase, Workspace
from knowledge_base.persistence import GlobalIndex, WorkspaceConfig

logger = logging.getLogger(__name__)

# Funzione che, dato il path di un workspace, restituisce il path del suo
# file di configurazione (config.json). L'applicazione decide la convenzione.
ConfigPathFor = Callable[[Path], Path]


class WorkspaceManager:
    """Operazioni CRUD sui workspace e sincronizzazione col filesystem."""

    def __init__(
        self,
        global_index: GlobalIndex,
        config_path_for: ConfigPathFor,
    ) -> None:
        self._index = global_index
        self._config_path_for = config_path_for

    # ..................................................................... #
    # CRUD
    # ..................................................................... #

    def _config(self, workspace_path: Path) -> WorkspaceConfig:
        return WorkspaceConfig(
            config_path=self._config_path_for(Path(workspace_path)),
            workspace_path=Path(workspace_path),
        )

    def add(self, path: Path) -> bool:
        """Registra un workspace e ne crea il ``config.json`` di default.
        Restituisce ``True`` se era nuovo."""
        ws = Path(path)
        logger.info("Registrazione workspace: %s", ws)
        added = self._index.add_workspace(ws)
        if added:
            self._config(ws).init_default()
            logger.info("Workspace registrato: %s", ws)
        else:
            logger.info("Workspace già registrato: %s", ws)
        return added

    def remove(self, path: Path) -> bool:
        """Deregistra un workspace. Restituisce ``True`` se era presente.
        Non cancella i file su disco."""
        ws = Path(path)
        logger.info("Rimozione workspace: %s", ws)
        removed = self._index.remove_workspace(ws)
        if removed:
            logger.info("Workspace rimosso: %s", ws)
        else:
            logger.warning("Workspace non trovato: %s", ws)
        return removed

    def list(self) -> List[Path]:
        """Restituisce i path dei workspace registrati."""
        workspaces = self._index.list_workspaces()
        logger.debug("Workspace registrati: %d", len(workspaces))
        return workspaces

    def set_last_workspace(self, path: Path) -> None:
        """Imposta l'ultimo workspace usato."""
        logger.debug("Ultimo workspace impostato: %s", path)
        self._index.set_last_workspace(Path(path))

    def get_last_workspace(self) -> Optional[Path]:
        return self._index.get_last_workspace()

    def load(self, path: Path) -> Workspace:
        """Carica il modello :class:`Workspace` dal suo ``config.json``."""
        ws_path = Path(path)
        logger.debug("Caricamento workspace: %s", ws_path)
        return self._config(ws_path).to_workspace()

    # ..................................................................... #
    # Sincronizzazione col filesystem
    # ..................................................................... #

    def sync(self, workspace: Workspace) -> Workspace:
        """Allinea ``workspace`` col filesystem: scopre le cartelle-figlie
        come nuove basi (vuote) e rimuove dalle basi del modello quelle la
        cui cartella non esiste più su disco.

        Restituisce il modello aggiornato (lo stesso oggetto, mutato in place)
        e ne persiste lo stato sul ``config.json``.

        La sincronizzazione a livello di file (mtime, chunks) è demandata
        allo Step 3 (``KnowledgeBaseManager``).
        """
        ws_path = workspace.path
        logger.info("Sincronizzazione workspace: %s", ws_path)

        # 1. Scopre cartelle-figlie come nuove basi.
        if ws_path.is_dir():
            seen: set[str] = set()
            for entry in ws_path.iterdir():
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                base_name = entry.name
                seen.add(base_name)
                if base_name not in workspace.bases:
                    workspace.bases[base_name] = KnowledgeBase(path=entry)

            # 2. Rimuove basi la cui cartella non esiste piÃ¹.
            for name in list(workspace.bases):
                if name not in seen and not workspace.bases[name].path.exists():
                    del workspace.bases[name]

        # 3. Persiste.
        self._save(workspace)
        return workspace

    def _save(self, workspace: Workspace) -> None:
        from knowledge_base.models import WorkspaceConfigData

        self._config(workspace.path).save(
            WorkspaceConfigData(
                version=1,
                domains=workspace.domains,
                bases=workspace.bases,
            )
        )

    # ..................................................................... #
    # Watchdog
    # ..................................................................... #

    def start_watching(
        self,
        workspace: Workspace,
        observer_factory: Optional[Callable[[], object]] = None,
        debounce_seconds: float = 0.5,
    ) -> "WorkspaceWatcher":
        """Avvia un watcher che richiama :meth:`sync` al verificarsi di
        eventi sul filesystem del workspace. Restituisce un oggetto
        costruibile con ``stop()``.

        ``observer_factory`` permette di iniettare un observer fittizio nei
        test; di default usa il :class:`watchdog.observers.Observer` reale.
        ``debounce_seconds`` controlla l'intervallo di debounce (default 500ms).
        """
        return WorkspaceWatcher(self, workspace, observer_factory, debounce_seconds)


class WorkspaceWatcher:
    """Wrapper attorno a un observer watchdog che sincronizza il workspace
    quando cambia il filesystem. Testabile iniettando un observer fittizio.

    Nota: ``sync()`` scopre e registra le cartelle-figlie come basi, ma
    **non indicizza** i file al loro interno (comportamento voluto).
    L'indicizzazione dei file è demandata a ``KnowledgeBaseManager.ingest()``.
    """

    def __init__(
        self,
        manager: WorkspaceManager,
        workspace: Workspace,
        observer_factory: Optional[Callable[[], object]] = None,
        debounce_seconds: float = 0.5,
    ) -> None:
        from watchdog.events import FileSystemEventHandler

        self._manager = manager
        self._workspace = workspace
        self._timer: threading.Timer | None = None
        self._debounce_seconds = debounce_seconds

        if observer_factory is None:
            from watchdog.observers import Observer

            observer_factory = Observer

        self._observer = observer_factory()

        watcher_ref = self

        class _Handler(FileSystemEventHandler):
            """Handler che intercetta creazioni, cancellazioni e spostamenti.

            Ogni evento resetta il timer di debounce; ``sync()`` viene
            eseguito solo dopo che gli eventi si sono calmati per
            ``debounce_seconds``.
            """

            def on_created(self_inner, event):  # type: ignore[override]
                logger.info("Evento FS on_created: %s", getattr(event, "src_path", "?"))
                watcher_ref._schedule_sync()

            def on_deleted(self_inner, event):  # type: ignore[override]
                logger.info("Evento FS on_deleted: %s", getattr(event, "src_path", "?"))
                watcher_ref._schedule_sync()

            def on_moved(self_inner, event):  # type: ignore[override]
                logger.info("Evento FS on_moved: %s -> %s",
                            getattr(event, "src_path", "?"),
                            getattr(event, "dest_path", "?"))
                watcher_ref._schedule_sync()

        self._handler = _Handler()

    def _schedule_sync(self) -> None:
        """Pianifica una sincronizzazione con debounce.

        Ogni chiamata resetta il timer: ``sync()`` viene eseguito solo
        dopo che gli eventi FS si sono calmati per ``_debounce_seconds``.
        """
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self._debounce_seconds, self._do_sync)
        self._timer.start()

    def _do_sync(self) -> None:
        """Esegue la sincronizzazione e azzera il timer."""
        logger.info("Debounce scaduto, esecuzione sync() su %s", self._workspace.path)
        self._manager.sync(self._workspace)
        self._timer = None

    def start(self) -> None:
        self._observer.schedule(self._handler, str(self._workspace.path), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()