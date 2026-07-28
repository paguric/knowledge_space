# Feature 002 — Logging per ogni operazione dell'applicazione

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a sotto-agente
**Priorità:** alta (migliora debuggabilità di tutta l'applicazione)

## Obiettivo

Ogni operazione significativa dell'applicazione — dalla gestione dei workspace/base/domini
all'indicizzazione dei file, alla ricerca, alla modifica della configurazione — deve generare
messaggi di log sul file `ks.log` in modo da poter ricostruire l'evoluzione del sistema e
debuggare anomalie.

## Contesto attuale

- Il modulo `knowledge_space.logging` (`src/knowledge_space/logging.py`) configura già un
  `RotatingFileHandler` su `<log_dir>/ks.log`, ma lo fa solo sul logger radice
  `knowledge_space`. (Fonte: `src/knowledge_space/logging.py`)
- I manager in `packages/knowledge-base/src/knowledge_base/` usano già `logger = logging.getLogger(__name__)`
  e loggano alcuni eventi (es. `workspace_manager.py`, `knowledge_base_manager.py`), ma in modo
  sporadico. (Fonte: `packages/knowledge-base/src/knowledge_base/workspace_manager.py`;
  `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py`)
- La CLI in `src/knowledge_space/cli/common.py` chiama `logging.basicConfig()` in `get_context()`,
  ma non usa `setup_logging()` né scrive sul file di log dell'app. (Fonte:
  `src/knowledge_space/cli/common.py`)
- La suite di test esistente (`tests/test_logging.py`) copre `setup_logging()`, ma non il logging
  delle operazioni CLI/manager. (Fonte: `tests/test_logging.py`)

## Requisiti

1. **Tutti i log dell'applicazione devono finire su `ks.log`:**
   - Configurare in `setup_logging()` anche il logger `knowledge_base` (o il logger root),
     in modo che i log emessi da `knowledge_base.*` siano catturati dagli stessi handler di
     `knowledge_space.*`.
   - `get_context()` in `src/knowledge_space/cli/common.py` deve chiamare `setup_logging()`
     usando `RuntimePaths.log_dir`, non `logging.basicConfig()`.
   - Il comportamento `--verbose` e `KS_LOG_LEVEL` deve restare invariato.

2. **Aggiungere log in tutte le operazioni CLI e manager:**
   - Livello consigliato:
     - `INFO` per inizio/fine operazioni, esiti positivi, cambiamenti di stato.
     - `DEBUG` per dettagli interni (parametri, query, mtime, hash).
     - `WARNING` per fallback o situazioni anomale non fatali.
     - `ERROR` per errori gestiti restituiti all'utente.
   - Operazioni da coprire (elenco minimo):
     - **Workspace:** `add`, `remove`, `list`, `info`, `set_last_workspace`.
     - **Base:** `add`, `remove`, `list`, `info`, `sync` (anche in `base.py` e `file.py`).
     - **File:** `add`, `remove`, `sync`, `reindex`.
     - **Dominio:** `new`, `remove`, `add_base`, `remove_base`, `auto_generate`, activate/deactivate.
     - **Ricerca:** `search` (query, base, numero risultati, errori embedder/Chroma).
     - **Configurazione:** `show`, `init`, `set`, `unset`, `edit` (inclusi trigger di reindex).
     - **Chunk:** `list`, `show`.
     - **Tree / status / models:** almeno inizio operazione ed eventuali errori.
   - I log devono essere in italiano, concetti, senza includere contenuto di file o chiavi API.

3. **Mantenere l'idempotenza di `setup_logging()`:**
   - Chiamare `setup_logging()` una sola volta per processo CLI. Verificare che chiamate multiple
     non duplichino handler (già supportato, ma testare).

## File da toccare

- `src/knowledge_space/logging.py` — estendere la configurazione a `knowledge_base` (o root).
- `src/knowledge_space/cli/common.py` — sostituire `logging.basicConfig()` con `setup_logging()`.
- `src/knowledge_space/cli/workspace.py` — aggiungere log.
- `src/knowledge_space/cli/base.py` — aggiungere log.
- `src/knowledge_space/cli/file.py` — aggiungere log.
- `src/knowledge_space/cli/domain.py` — aggiungere log.
- `src/knowledge_space/cli/search.py` — aggiungere log.
- `src/knowledge_space/cli/config.py` — aggiungere log.
- `src/knowledge_space/cli/chunk.py` — aggiungere log.
- `src/knowledge_space/cli/tree.py` — aggiungere log.
- `src/knowledge_space/cli/status.py` — aggiungere log.
- `src/knowledge_space/cli/models_cmd.py` — aggiungere log.
- `src/knowledge_space/cli/reindex.py` — aggiungere log.
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — completare log esistenti.
- `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` — completare log.
- `packages/knowledge-base/src/knowledge_base/domain_manager.py` — aggiungere log.
- `packages/knowledge-base/src/knowledge_base/search_service.py` — aggiungere log.
- `tests/test_logging.py` — aggiungere test su logging operazioni.

## Deliverables

1. `setup_logging()` cattura log sia di `knowledge_space` che di `knowledge_base`.
2. `get_context()` avvia il logging su file tramite `setup_logging()`.
3. Ogni comando CLI e ogni metodo manager significativo logga almeno inizio ed esito.
4. Test che verificano:
   - un comando CLI scrive sul file di log;
   - un'operazione di manager scrive sul file di log;
   - `setup_logging()` è idempotente anche dopo la modifica.

## Verifica

- `uv run pytest tests/test_logging.py -q` → verde.
- `uv run pytest tests/test_cli.py -q` → verde (nessuna regressione).
- `uv run pytest packages/knowledge-base/tests/ -q` → verde (nessuna regressione).
- `uv run pytest -q` → i 13 test noti possono ancora fallire, ma non devono essercene di nuovi.

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Non includere contenuti di file, API key o secret nei log.
- Al termine: riportare brevemente branch, file cambiati, comando+risultato test, dubbi.
