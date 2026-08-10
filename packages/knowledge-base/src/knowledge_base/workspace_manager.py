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
from typing import Any, Callable, List, Optional, Set

from knowledge_base.models import KnowledgeBase, Workspace
from knowledge_base.persistence import GlobalIndex, WorkspaceConfig

logger = logging.getLogger(__name__)

# Funzione che, dato il path di un workspace, restituisce il path del suo
# file di configurazione (config.json). L'applicazione decide la convenzione.
ConfigPathFor = Callable[[Path], Path]

# Factory che, dato un Workspace, restituisce un KnowledgeBaseManager
# (o un oggetto equivalente con metodo add_file).
BaseManagerFactory = Callable[[Workspace], Any]


def _discover_bases_recursive(ws_path: Path) -> dict[str, KnowledgeBase]:
    """Scopre ricorsivamente tutte le sottocartelle come basi.

    Ogni cartella (non nascosta, non ``.knowledge-space``) diventa una base.
    Il nome della base è il path relativo rispetto al workspace, con ``/``
    come separatore (es. ``Papers``, ``Papers/2024``).

    Returns:
        Dizionario nome_base → KnowledgeBase(path=cartella_assoluta).
    """
    bases: dict[str, KnowledgeBase] = {}
    for entry in ws_path.rglob("*"):
        if not entry.is_dir():
            continue
        # Salta cartelle nascoste e qualsiasi cartella dentro .knowledge-space
        if entry.name.startswith(".") or ".knowledge-space" in entry.parts:
            continue
        rel = entry.relative_to(ws_path)
        base_name = str(rel)
        bases[base_name] = KnowledgeBase(path=entry)
    return bases


class WorkspaceManager:
    """Operazioni CRUD sui workspace e sincronizzazione col filesystem."""

    def __init__(
        self,
        global_index: GlobalIndex,
        config_path_for: ConfigPathFor,
        base_manager_factory: Optional[BaseManagerFactory] = None,
    ) -> None:
        self._index = global_index
        self._config_path_for = config_path_for
        self._base_manager_factory = base_manager_factory

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
        """Allinea ``workspace`` col filesystem: scopre ricorsivamente
        tutte le sottocartelle come basi e rimuove dal modello quelle la
        cui cartella non esiste più su disco.

        Il nome di ogni base è il path relativo dalla radice del workspace
        (es. ``Papers``, ``Papers/2024``). Le cartelle nascoste e
        ``.knowledge-space`` sono ignorate.

        Restituisce il modello aggiornato (lo stesso oggetto, mutato in place)
        e ne persiste lo stato sul ``config.json``.

        La sincronizzazione a livello di file (mtime, chunks) è demandata
        a :meth:`sync_and_ingest`.
        """
        ws_path = workspace.path
        logger.info("Sincronizzazione workspace: %s", ws_path)

        # 1. Scopre ricorsivamente tutte le cartelle come basi.
        if ws_path.is_dir():
            discovered = _discover_bases_recursive(ws_path)
            seen: set[str] = set(discovered)

            for base_name, kb in discovered.items():
                if base_name not in workspace.bases:
                    workspace.bases[base_name] = kb
                    logger.info("Nuova base scoperta: %s", base_name)

            # 2. Rimuove basi la cui cartella non esiste più.
            for name in list(workspace.bases):
                if name not in seen and not workspace.bases[name].path.exists():
                    del workspace.bases[name]
                    logger.info("Base rimossa (cartella assente): %s", name)

        # 3. Persiste.
        self._save(workspace)
        return workspace

    def sync_and_ingest(self, workspace: Workspace) -> Workspace:
        """Sincronizza il workspace e indicizza i file nuovi o modificati.

        1. Chiama :meth:`sync` per scoprire le basi.
        2. Per ogni base **nuova** (non presente prima della sync), tenta
           l'indicizzazione dei file tramite il ``base_manager_factory``
           iniettato nel costruttore.
        3. Per ogni base **esistente**, verifica se ci sono file nuovi
           (non presenti nel modello) o modificati (mtime diverso) e li
           indicaizza.
        4. Se nessun ``base_manager_factory`` è configurato, salta l'ingest
           con un WARNING.

        Returns:
            Workspace aggiornato.
        """
        # Salva i nomi delle basi PRIMA della sync per rilevare le nuove.
        basi_prima: set[str] = set(workspace.bases)

        self.sync(workspace)

        basi_dopo: set[str] = set(workspace.bases)
        basi_nuove = basi_dopo - basi_prima
        basi_esistenti = basi_dopo & basi_prima

        if not basi_dopo:
            logger.info("Nessuna base nel workspace")
            return workspace

        if self._base_manager_factory is None:
            logger.warning(
                "Base manager factory non configurata: impossibile indicizzare "
                "i file nelle basi: %s",
                basi_dopo,
            )
            return workspace

        # Crea un KnowledgeBaseManager per il workspace e indicizza i file.
        try:
            base_manager = self._base_manager_factory(workspace)
        except Exception as exc:
            logger.error("Errore nella creazione del base manager: %s", exc)
            return workspace

        # 1. Indicizza file nelle basi NUOVE.
        for base_name in basi_nuove:
            self._ingest_files_in_base(base_manager, workspace, base_name)

        # 2. Indicizza file NUOVI/MODIFICATI nelle basi ESISTENTI.
        for base_name in basi_esistenti:
            self._ingest_new_files_in_existing_base(
                base_manager, workspace, base_name
            )

        # 3. Persisti i file indicizzati.
        self._save(workspace)
        return workspace

    def _ingest_files_in_base(
        self,
        base_manager: Any,
        workspace: Workspace,
        base_name: str,
    ) -> None:
        """Indicizza tutti i file in una base appena scoperta."""
        kb = workspace.bases[base_name]
        base_path = kb.path
        if not base_path.is_dir():
            return

        files = [
            f
            for f in base_path.iterdir()
            if f.is_file() and not f.name.startswith(".")
        ]
        if not files:
            logger.info("Base %s: nessun file da indicizzare", base_name)
            return

        logger.info("Base %s: indicizzazione di %d file", base_name, len(files))
        for file_path in files:
            try:
                base_manager.add_file(base_name, file_path)
                logger.info("File indicizzato: %s/%s", base_name, file_path.name)
            except Exception as exc:
                logger.warning(
                    "Errore nell'indicizzazione di %s/%s: %s",
                    base_name,
                    file_path.name,
                    exc,
                )

    def _ingest_new_files_in_existing_base(
        self,
        base_manager: Any,
        workspace: Workspace,
        base_name: str,
    ) -> None:
        """Indicizza file nuovi o modificati in una base già esistente.

        Confronta i file su disco con quelli nel modello (``kb.files``).
        Un file è considerato nuovo se non è nel modello; è considerato
        modificato se l'``mtime`` su disco differisce da quello registrato.
        """
        kb = workspace.bases[base_name]
        base_path = kb.path
        if not base_path.is_dir():
            return

        files_to_ingest: list[Path] = []
        for file_path in base_path.iterdir():
            if not file_path.is_file() or file_path.name.startswith("."):
                continue

            existing = kb.files.get(file_path.name)
            if existing is None:
                # File nuovo
                files_to_ingest.append(file_path)
            else:
                # File esistente: check mtime
                try:
                    current_mtime = file_path.stat().st_mtime
                except OSError:
                    continue
                if existing.mtime != current_mtime:
                    files_to_ingest.append(file_path)

        if not files_to_ingest:
            return

        logger.info(
            "Base %s: indicizzazione di %d file nuovi/modificati",
            base_name,
            len(files_to_ingest),
        )
        for file_path in files_to_ingest:
            try:
                base_manager.add_file(base_name, file_path)
                logger.info("File indicizzato: %s/%s", base_name, file_path.name)
            except Exception as exc:
                logger.warning(
                    "Errore nell'indicizzazione di %s/%s: %s",
                    base_name,
                    file_path.name,
                    exc,
                )

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
        """Avvia un watcher che richiama :meth:`sync_and_ingest` al
        verificarsi di eventi sul filesystem del workspace.

        ``observer_factory`` permette di iniettare un observer fittizio nei
        test; di default usa il :class:`watchdog.observers.Observer` reale.
        ``debounce_seconds`` controlla l'intervallo di debounce (default 500ms).
        """
        return WorkspaceWatcher(self, workspace, observer_factory, debounce_seconds)


class WorkspaceWatcher:
    """Wrapper attorno a un observer watchdog che sincronizza il workspace
    quando cambia il filesystem. Testabile iniettando un observer fittizio.

    Quando il ``base_manager_factory`` è configurato, il watcher esegue
    ``sync_and_ingest()`` (scopre basi + indicizza file nelle basi nuove).
    Altrimenti esegue solo ``sync()`` (scopre basi, non indicizza).
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
        # Protezione da sovrapposizione (bug 016): una sync alla volta.
        self._sync_in_progress = False
        self._sync_pending = False

        if observer_factory is None:
            from watchdog.observers import Observer

            observer_factory = Observer

        self._observer = observer_factory()

        watcher_ref = self

        class _Handler(FileSystemEventHandler):
            """Handler che intercetta creazioni, cancellazioni e spostamenti.

            Ogni evento resetta il timer di debounce; la sincronizzazione
            viene eseguita solo dopo che gli eventi si sono calmati per
            ``debounce_seconds``.
            """

            def on_created(self_inner, event):  # type: ignore[override]
                src = getattr(event, "src_path", "")
                if ".knowledge-space" in src:
                    return
                logger.info("Evento FS on_created: %s", src)
                watcher_ref._schedule_sync()

            def on_deleted(self_inner, event):  # type: ignore[override]
                src = getattr(event, "src_path", "")
                if ".knowledge-space" in src:
                    return
                logger.info("Evento FS on_deleted: %s", src)
                watcher_ref._schedule_sync()

            def on_moved(self_inner, event):  # type: ignore[override]
                src = getattr(event, "src_path", "")
                dest = getattr(event, "dest_path", "")
                if ".knowledge-space" in src or ".knowledge-space" in dest:
                    return
                logger.info(
                    "Evento FS on_moved: %s -> %s",
                    src, dest,
                )
                watcher_ref._schedule_sync()

        self._handler = _Handler()

    def _schedule_sync(self) -> None:
        """Pianifica una sincronizzazione con debounce.

        Ogni chiamata resetta il timer: la sincronizzazione viene eseguita
        solo dopo che gli eventi FS si sono calmati per ``_debounce_seconds``.
        """
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self._debounce_seconds, self._do_sync)
        self._timer.start()

    def _do_sync(self) -> None:
        """Esegue la sincronizzazione (con ingest se possibile) e azzera il timer.

        Protezione da sovrapposizione (bug 016): se una sync è già in corso,
        la chiamata viene marcata come pendente e rieseguita al termine di
        quella corrente — mai in parallelo, al massimo una in coda.
        """
        if self._sync_in_progress:
            logger.info(
                "Sincronizzazione già in corso su %s, accodata al termine",
                self._workspace.path,
            )
            self._sync_pending = True
            self._timer = None
            return

        self._sync_in_progress = True
        try:
            if self._manager._base_manager_factory is not None:
                logger.info(
                    "Debounce scaduto, esecuzione sync_and_ingest() su %s",
                    self._workspace.path,
                )
                self._manager.sync_and_ingest(self._workspace)
            else:
                logger.info(
                    "Debounce scaduto, esecuzione sync() su %s",
                    self._workspace.path,
                )
                self._manager.sync(self._workspace)
        finally:
            self._sync_in_progress = False
            self._timer = None
            if self._sync_pending:
                # File arrivati durante la sync: riesegue una volta sola.
                self._sync_pending = False
                self._schedule_sync()

    def start(self) -> None:
        self._observer.schedule(self._handler, str(self._workspace.path), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
