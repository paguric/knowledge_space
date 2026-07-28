# Bug 003 — `ks tree` e `ks status` non mostrano tutti i workspace esistenti

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a sotto-agente
**Priorità:** media (comportamento fuorviante per utenti con più workspace)

## Sintomo

`ks tree` e `ks status` mostrano sempre un **singolo workspace** (quello attivo o quello
trovato tramite `--workspace` / `last_workspace` / cwd-context), anche quando nel registro
esistono più workspace.

Per un utente con più workspace registrati, ci si aspetta che i comandi mostrino la lista
di tutti i workspace, con la possibilità di dettagliare quello attivo o di filtrare con
`--workspace`.

## Causa radice

- `tree.py` e `status.py` chiamano `get_workspace(ctx, workspace)` che risolve sempre un
  singolo workspace. (Fonte: `src/knowledge_space/cli/tree.py`; `src/knowledge_space/cli/status.py`;
  `src/knowledge_space/cli/common.py`)
- Non c'è iterazione su `ctx.workspace_manager.list()`.
- `status.py` ha già un fallback "Nessun workspace trovato" ma non gestisce il caso multi-workspace.
  (Fonte: `src/knowledge_space/cli/status.py`)

## Fix atteso

### `ks status`

- Se non viene passato `--workspace`:
  - Recupera la lista di tutti i workspace registrati con `ctx.workspace_manager.list()`.
  - Se la lista è vuota, mostra il messaggio attuale.
  - Se la lista contiene uno o più workspace:
    - Mostra una panoramica di ciascun workspace (path, numero di basi/file/chunk, attivo/inattivo).
    - Evidenzia il workspace attivo (quello restituito da `resolve_workspace_path` o `last_workspace`).
    - Mantieni `--workspace` per dettagliare un singolo workspace.
    - Mantieni `--json` con una lista di workspace.

### `ks tree`

- Se non viene passato `--workspace`:
  - Recupera la lista di tutti i workspace registrati.
  - Se c'è un solo workspace, comportamento attuale.
  - Se ce ne sono più di uno, mostra per ciascuno un albero (con header del path workspace).
  - Mantieni `--workspace` per mostrare solo un workspace.
  - Mantieni `--json` con una lista.

### API condivisa

- Aggiungere in `src/knowledge_space/cli/common.py` una funzione helper, ad esempio
  `list_workspaces_or_active(ctx, workspace)`, che:
  - se `workspace` è passato, restituisce la lista con quel solo workspace;
  - altrimenti restituisce `ctx.workspace_manager.list()`.
  Oppure gestire la logica direttamente nei comandi.

### Output

- Formato testo: chiaro, indentato, con il path workspace come radice di ogni sezione.
- Formato JSON: lista di oggetti workspace (stessa struttura attuale, incapsulati in
  `{ "workspaces": [...] }`).

## File da toccare

- `src/knowledge_space/cli/common.py` — helper per risolvere lista workspace (opzionale ma consigliato).
- `src/knowledge_space/cli/status.py` — mostra tutti i workspace.
- `src/knowledge_space/cli/tree.py` — mostra tutti i workspace.
- `tests/test_cli.py` — aggiungere test per:
  - `ks status` con più workspace registrati;
  - `ks tree` con più workspace registrati;
  - `--workspace` filtra correttamente;
  - output JSON valido.

## Verifica

- `uv run pytest tests/test_cli.py -q` → verde.
- `uv run pytest -q` → nessun nuovo fallimento.
- Manualmente: registrare due workspace e verificare che `ks status` e `ks tree` mostrino entrambi.

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Al termine: riportare brevemente branch, file cambiati, comando+risultato test, dubbi.
