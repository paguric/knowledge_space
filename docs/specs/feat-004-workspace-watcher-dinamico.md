# Feature 004 — Watcher dinamico: workspace aggiunti dopo l'avvio vengono monitorati

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da delegare a feature-lead
**Priorità:** media

## Contesto

Attualmente `ks serve` registra i watcher solo all'avvio:

```python
for ws_path in workspaces_paths:
    watcher = ctx.workspace_manager.start_watching(ws)
    watcher.start()
    watchers.append(watcher)
```

Se dopo l'avvio l'utente aggiunge un workspace con `ks workspace add`, quel workspace non viene monitorato.

## Soluzione: watchdog su `workspaces.json`

Un `WorkspacesWatcher` monitora il file `workspaces.json` (o `state.json` a livello di runtime). Quando il file cambia:
1. Ricarica la lista workspace dal manager
2. Confronta con i watcher attivi
3. Aggiunge watcher per workspace nuovi
4. Rimuove watcher per workspace rimossi

## Implementazione

### Nuovo oggetto `WorkspacesWatcher` in `serve.py`

```python
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

class _WorkspacesFileHandler(FileSystemEventHandler):
    """Handler che notifica change_event quando workspaces.json cambia."""

    def __init__(self, path: Path, change_event: threading.Event):
        self._path = path
        self._change_event = change_event

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.src_path == str(self._path):
            self._change_event.set()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.src_path == str(self._path):
            self._change_event.set()


class WorkspacesWatcher:
    """Monitora workspaces.json e aggiunge/rimuove workspace watcher dinamicamente."""

    def __init__(
        self,
        workspaces_json_path: Path,
        workspace_manager: WorkspaceManager,
        start_watcher_fn: Callable[[Path], WorkspaceWatcher],
        watchers_ref: list[WorkspaceWatcher],
        lock: threading.Lock,
        change_event: threading.Event,
    ):
        ...

    def start(self) -> None: ...

    def _sync_workspaces(self) -> None:
        """Ricarica lista workspace, aggiunge/rimuove watcher."""
        current_paths = self._workspace_manager.list()
        active_paths = {w._workspace.path for w in self._watchers_ref}

        # Rimuovi watcher per workspace rimossi
        with self._lock:
            for w in list(self._watchers_ref):
                if w._workspace.path not in current_paths:
                    w.stop()
                    self._watchers_ref.remove(w)
                    logger.info("Watcher rimosso: %s", w._workspace.path)

        # Aggiungi watcher per workspace nuovi
        for path in current_paths:
            if path not in active_paths and path.is_dir():
                ws = self._workspace_manager.load(path)
                w = self._start_watcher_fn(ws)
                w.start()
                with self._lock:
                    self._watchers_ref.append(w)
                logger.info("Watcher aggiunto: %s", path)

    def _poll_loop(self) -> None:
        """Loop che verifica change_event periodicamente."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=1.0)
            if self._change_event.is_set():
                self._change_event.clear()
                self._sync_workspaces()

    def stop(self) -> None:
        self._stop_event.set()
        self._observer.stop()
```

### Modifiche a `serve_command`

```python
    # Lock + event per comunicazione tra thread
    watchers_lock = threading.Lock()
    ws_change_event = threading.Event()
    stop_event_ws = threading.Event()

    # Lista condivisa dei watcher attivi
    watchers: list[WorkspaceWatcher] = []

    def _start_and_register(ws: Workspace) -> WorkspaceWatcher:
        w = ctx.workspace_manager.start_watching(ws)
        w.start()
        return w

    # Avvia il watcher su workspaces.json
    workspaces_watcher = WorkspacesWatcher(
        workspaces_json_path=rp.workspaces_json,  # o da ctx
        workspace_manager=ctx.workspace_manager,
        start_watcher_fn=_start_and_register,
        watchers_ref=watchers,
        lock=watchers_lock,
        change_event=ws_change_event,
        stop_event=stop_event_ws,
    )
    workspaces_watcher.start()
```

Nel `finally`, oltre ai watcher dei workspace, fermare anche `workspaces_watcher.stop()`.

### File da toccare

- `src/knowledge_space/cli/serve.py` — aggiungere `WorkspacesWatcher`, `_WorkspacesFileHandler`, modificare `serve_command`

### Gestione edge case

- Se `workspaces.json` non esiste ancora, il watcher deve comunque partire e aspettare che venga creato (non lanciare errore).
- Il watchdog non garantisce che il file sia stato completamente scritto prima del callback. Usare `time.sleep(0.2)` prima di ricaricare, oppure polling con debounce.
- Lock: le modifiche alla lista `watchers` devono essere protette da `watchers_lock`.

### Test

- Test manuale:
  ```bash
  systemctl --user restart ks-serve
  sleep 2
  ks workspace add /tmp/ws_dopo
  sleep 3
  # Verificare che il watcher sia attivo:
  journalctl --user -u ks-serve | grep "Watcher aggiunto"
  ls /tmp/ws_dopo
  mkdir /tmp/ws_dopo/TestBase
  sleep 2
  # Verificare che la base sia stata registrata
  ```

## Istruzioni per feature-lead

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usare l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Testare manualmente come descritto sopra prima di riportare.
- Al termine: riportare branch, file cambiati, eventuali dubbi.
