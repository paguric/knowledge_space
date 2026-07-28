# Bug 004 — `mv cartella/ workspace/` non crea automaticamente la base

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a sotto-agente
**Priorità:** media (flusso utente comune: aggiungere contenuti spostando cartelle)

## Sintomo

Quando un utente sposta una cartella dentro un workspace già registrato con:

```bash
mv cartella/ workspace/
```

la base corrispondente non viene creata automaticamente. Non esiste un comando CLI
`ks workspace sync` per forzare la riscoperta, e il watcher filesystem è disponibile
solo in un processo long-running (non nella CLI standalone).

## Causa radice

- `WorkspaceManager.sync()` (`packages/knowledge-base/src/knowledge_base/workspace_manager.py`)
  già scopre le cartelle-figlie del workspace e le registra come basi. (Fonte:
  `packages/knowledge-base/src/knowledge_base/workspace_manager.py`)
- Il comando `ks workspace add` chiama `sync()` solo in fase di registrazione iniziale.
  (Fonte: `src/knowledge_space/cli/workspace.py`)
- Non esiste un comando `ks workspace sync` esposto all'utente per riscoprire le basi
  dopo modifiche al filesystem.
- Il watcher `WorkspaceWatcher` è pensato per un processo long-running e non è attivo
  nella CLI standalone.

## Fix atteso

1. **Aggiungere il comando CLI `ks workspace sync`** in `src/knowledge_space/cli/workspace.py`:
   - Carica il workspace (risolto come negli altri comandi: `--workspace`, `last_workspace`,
     cwd-context).
   - Chiama `ctx.workspace_manager.sync(ws)`.
   - Mostra le basi scoperte (nuove), quelle rimosse (cartelle scomparse) e quelle già presenti.
   - Supporta `--json`.
   - Se non esiste workspace, errore con messaggio standard.

2. **Verificare che `sync()` rilevi correttamente cartelle spostate/mosse**:
   - `WorkspaceManager.sync()` itera `ws_path.iterdir()` e quindi rileva qualsiasi cartella
     presente al momento della chiamata. Non è necessario modificare il watcher per il caso CLI.
   - Aggiungere un test che simuli `mv cartella/ workspace/` creando una cartella e poi
     chiamando `sync()`: la base deve comparire.

3. **Logging** (coerente con Feature 002):
   - Aggiungere log INFO per l'operazione di sync e le basi scoperte/rimosse.

## File da toccare

- `src/knowledge_space/cli/workspace.py` — aggiungere comando `sync`.
- `tests/test_cli.py` — aggiungere test per `ks workspace sync`.
- `packages/knowledge-base/tests/test_workspace_manager.py` — aggiungere test per
  `sync()` dopo spostamento/creazione cartella.
- `docs/specs/bug-004-mv-trigger-base.md` — questo file (non modificare da sotto-agente).

## Deliverables

- Comando `ks workspace sync` funzionante e testato.
- `mv cartella/ workspace/` seguito da `ks workspace sync` crea la base.
- Nessuna regressione sui test esistenti.

## Verifica

- `uv run pytest tests/test_cli.py -q` → verde.
- `uv run pytest packages/knowledge-base/tests/test_workspace_manager.py -q` → verde.
- `uv run pytest -q` → nessun nuovo fallimento.
- Manuale:
  ```bash
  ks workspace add /tmp/ws
  mkdir /tmp/new_base
  mv /tmp/new_base /tmp/ws/
  ks workspace sync
  ks base list
  # deve mostrare new_base
  ```

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Al termine: riportare brevemente branch, file cambiati, comando+risultato test, dubbi.
