# Feature 003 — `ks serve`: daemon con watcher e server MCP

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a sotto-agente
**Priorità:** alta (sblocca watch automatico + MCP; risolve bug-004)

## Obiettivo

`ks serve` è un comando long-running che:
1. Avvia un **watcher filesystem** su ogni workspace registrato.
2. Espone un **server MCP** per operazioni remote.
3. Resta in foreground (o diventa daemon) finché non riceve SIGINT/SIGTERM.

## Architettura

### Watcher filesystem

- Nuovo modulo: `packages/knowledge-base/src/knowledge_base/workspace_watcher.py`.
- Usa `watchdog` (`watchdog.observers.Observer` + `watchdog.events.FileSystemEventHandler`).
- Su ogni evento FS (`created`, `modified`, `deleted`, `moved`) chiama `WorkspaceManager.sync(ws)`.
- **Non** indicizza automaticamente i file — `sync()` aggiunge/rimuove basi dalla struttura workspace.
  L'indicizzazione dei file dentro le basi resta a carico di comandi espliciti (`ks file add`,
  `ks base sync`, o ingestion on-demand).
- Ogni workspace registrato ha il proprio `Observer` (thread separato).
- Il file `~/.local/state/KnowledgeSpace/workspaces.json` è la fonte di verità per la lista.

### Server MCP

- Nuovo modulo: `packages/mcp-server/src/mcp_server/` (se non esiste, crealo sotto `src/knowledge_space/mcp/`).
- Trasporto **stdio** (default) e **SSE** (opzionale, `--sse` flag).
- Implementa i tool/commandi MCP per le operazioni principali:
  - `workspace_list` — elenca workspace
  - `workspace_add` — aggiunge workspace
  - `base_add` — aggiunge base
  - `base_list` — elenca basi
  - `file_ingest` — ingestisce file
  - `search` — ricerca
  - `sync` — forza sync su workspace (già presente come metodo manager, esporlo)
- Usa il protocollo MCP 2024-11-05 (o la versione più recente stabile).
- Il server MCP **non** reimplementa la logica — wrappa `WorkspaceManager`, `KnowledgeBaseManager`, ecc.

### Comando `ks serve`

- File: `src/knowledge_space/cli/serve.py`.
- Opzioni:
  - `--host HOST` (default `127.0.0.1`) — per SSE.
  - `--port PORT` (default `8080`) — per SSE.
  - `--sse` — usa trasporto SSE invece di stdio.
  - `--verbose` — DEBUG logging.
- Comportamento:
  1. Carica `RuntimePaths` e l'indice globale.
  2. Per ogni workspace in `index.list()`, avvia un `WorkspaceWatcher`.
  3. Avvia il server MCP sul trasporto selezionato.
  4. Su SIGINT/SIGTERM: ferma tutti i watcher, chiude server, exit 0.
- Registrazione in `src/knowledge_space/cli/__init__.py`:
  ```python
  from knowledge_space.cli.serve import serve_command
  app.command(name="serve", help="Avvia watcher + server MCP.")(serve_command)
  ```

### Dipendenze da aggiungere

In `pyproject.toml`:
```toml
[project.optional-dependencies]
watcher = ["watchdog>=4.0.0"]
mcp = ["mcp>=0.9.0"]
dev = ["watchdog", "mcp"]
```
Oppure metti `watchdog` direttamente in `dependencies` se il watcher è core (non opzionale).
Per MCP: decidi se è core o opzionale (se è core, mettilo in `dependencies`).

### File da creare/modificare

**Nuovi file:**
- `packages/knowledge-base/src/knowledge_base/workspace_watcher.py`
- `src/knowledge_space/cli/serve.py`
- `packages/mcp-server/src/mcp_server/` (se necessario) **oppure** integrazione MCP in `knowledge_space/mcp/`
- `packages/mcp-server/pyproject.toml` (se nuovo pacchetto)
- `tests/test_workspace_watcher.py`
- `tests/test_mcp_server.py` (o integrazione in `test_cli.py`)

**File da modificare:**
- `src/knowledge_space/cli/__init__.py` — registra `serve_command`
- `pyproject.toml` — aggiungi `watchdog` (e opzionalmente `mcp`)
- `docs/roadmap.md` — integra watcher in Step 14

## Logging (Feature 002)

- `workspace_watcher.py`: log INFO su avvio/fermo watcher, WARNING su errore.
- `serve.py`: log INFO su avvio server, shutdown, ERROR su eccezioni.
- Tutto passa da `setup_logging()` già presente.

## Test

- `test_workspace_watcher.py`: test con `FakeObserver` (già usato in `test_workspace_manager.py`) per
  verificare che `sync()` venga chiamato su eventi.
- `test_cli.py` (classe `TestServe`): verifica che `ks serve --help` funzioni e che il comando
  si avvii/fermi correttamente (con timeout).
- `test_mcp_server.py`: verifica handshake MCP e risposte ai tool.

## Verifica

- `uv run pytest tests/test_workspace_watcher.py -q` → verde.
- `uv run pytest tests/test_cli.py -q` → verde (include TestServe).
- `uv run pytest -q` → nessun nuovo fallimento.
- Manuale:
  ```bash
  ks workspace add /tmp/ws
  ks serve &
  sleep 2
  mkdir /tmp/ws/new_base
  sleep 2
  # la base new_base deve comparire
  kill %1
  ```

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Non modificare `README.md` (lo fa il master).
- Al termine: riportare branch, file creati/modificati, risultato test, eventuali dubbi.
