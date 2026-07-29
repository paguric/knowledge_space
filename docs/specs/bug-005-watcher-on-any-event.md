# Bug 005 — Watcher non triggera `sync()`: `on_any_event` errato + nessun debounce

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a sotto-agente
**Priorità:** alta (bloccante per il flusso watch)

## Riproduzione

```bash
ks workspace add /path/to/ws
ks serve &
# mv Paper\ Accademici/ /path/to/ws/
# la base non viene creata, nessun sync
```

## Diagnosi

Tre problemi indipendenti nel `WorkspaceWatcher` in
`packages/knowledge-base/src/knowledge_base/workspace_manager.py`.

### Problema 1 — `on_any_event` non è un metodo di callback watchdog

**Codice attuale:**

```python
class _Handler(FileSystemEventHandler):
    def on_any_event(self_inner, event):
        manager_ref._manager.sync(manager_ref._workspace)
```

L'Observer di watchdog chiama direttamente `on_created`, `on_moved`, `on_deleted`, ecc.
`on_any_event` è un metodo interno che watchdog chiama *dopo* i metodi specifici
(come hook), ma **non viene triggerato dall'Observer come entry point**.
Di conseguenza `sync()` non viene mai invocato.

**Fix:** sostituire `on_any_event` con i metodi corretti:
- `on_created(event)` — chiama `sync()` quando viene creata una cartella.
- `on_deleted(event)` — chiama `sync()` quando viene rimossa una cartella.
- `on_moved(event)` — chiama `sync()` quando una cartella viene spostata.

### Problema 2 — Nessun debounce: `mv` genera centinaia di eventi

Un `mv cartella/ workspace/` genera un evento `on_created` + `on_modified` per
**ogni file dentro** la cartella, più l'evento `on_created` per la cartella stessa.
Il handler chiamerebbe `sync()` centinaia di volte di fila.

**Fix:** aggiungere un debounce di 500 ms (thread-safe, con `threading.Timer`).

Esempio di pattern:

```python
import threading

class WorkspaceWatcher:
    def __init__(self, ...):
        self._timer: threading.Timer | None = None
        self._debounce_seconds = 0.5

    def _schedule_sync(self):
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self._debounce_seconds, self._do_sync)
        self._timer.start()

    def _do_sync(self):
        self._manager.sync(self._workspace)
        self._timer = None
```

Ogni evento FS resetta il timer; `sync()` viene eseguito solo quando gli eventi
si sono calmati per 500 ms.

### Problema 3 (comportamento, non bug) — `sync()` non indicizza i file

Anche con i fix precedenti, `WorkspaceManager.sync()` scopre le cartelle-figlie
e le registra come basi, ma **non indicizza i file al loro interno**.
Questo è probabilmente il comportamento voluto (struttura ≠ contenuto).

**Azione:** verificare se il watcher deve anche chiamare `ingest()` sui file nuovi.
Se sì, aggiungere un metodo `WorkspaceManager.sync_and_ingest(ws)` che chiama
`sync()` + per ogni base nuova chiama `KnowledgeBaseManager.ingest()`.

Per ora **lascia il comportamento attuale** e aggiungi un commento che chiarisca
che il watcher si limita a sincronizzare la struttura (basi), non il contenuto.

## File da toccare

- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` —
  - Sostituire `on_any_event` con `on_created`, `on_deleted`, `on_moved`.
  - Aggiungere debounce con `threading.Timer`.
  - Aggiungere commento su sync vs ingest.
  - Log: INFO quando un evento triggera il debounce, INFO quando sync viene eseguito.

## Test

- `tests/test_workspace_watcher.py`:
  - Aggiornare `test_dispatch_calls_sync`: chiamare `on_created` invece di `on_any_event`.
  - Aggiungere `test_on_deleted_triggers_sync`.
  - Aggiungere `test_on_moved_triggers_sync`.
  - Aggiungere `test_debounce_does_not_sync_multiple_times`:
    - Dispatch 3 eventi rapidi, verifica che `sync()` sia chiamato UNA sola volta.

## Verifica

- `uv run pytest tests/test_workspace_watcher.py -q` → verde.
- `uv run pytest -q` → nessun nuovo fallimento.
- Manuale (con workspace reale):
  ```bash
  ks workspace add /tmp/ws
  ks serve &
  sleep 2
  mkdir /tmp/ws/new_base
  sleep 2
  # verifica che new_base compaia in ks status
  kill %1
  ```

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Al termine: riportare branch, file cambiati, risultato test, eventuali dubbi.
