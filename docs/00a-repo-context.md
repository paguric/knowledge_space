# Knowledge Space — Repository Context (per sotto-agenti)

> Generato dall'agente master come contesto condiviso. **Ogni affermazione cita il file
> da cui è tratta**, così ogni sotto-agente può lavorare in autonomia. Mantenere questo
> file come fonte di orientamento; la pianificazione aggiornata vive in `docs/roadmap.md`.

## 1. Cos'è il progetto
- Pipeline di ingestione, indicizzazione e retrieval su documenti, con **strategy pattern**
  per ingestion / chunking / embedding / retrieval / LLM. (Fonte: `README.md`; `docs/roadmap.md` §1)
- Monorepo **uv** con 3 pacchetti: `knowledge-base` (libreria pura), `mcp-server` (futuro),
  `knowledge-space` (app layer: CLI/bootstrap). (Fonte: `pyproject.toml` → `[tool.uv.workspace].members`;
  `docs/roadmap.md` §1)
- `requires-python = ">=3.14"`. La roadmap (§9) nota che è molto restrittivo e da valutare
  (`>=3.12`). (Fonte: `pyproject.toml`; `docs/roadmap.md` §9)

## 2. Layout pacchetti e responsabilità
| Pacchetto | Responsabilità | Dipende da |
|-----------|----------------|------------|
| `knowledge-base` | Modelli, persistenza, manager, strategy registry, pipeline retrieval/grafo | Nessun riferimento a XDG/CLI/API |
| `knowledge-space` | `RuntimePaths`, `AppContext`, CLI, REST (futuro), bootstrap | `knowledge-base` |
| `mcp-server` | Server MCP (stdio/SSE) | `knowledge-base` |

(Fonte: `docs/roadmap.md` §1 — "Separazione delle responsabilità")

Struttura su disco:
```
packages/knowledge-base/src/knowledge_base/   # models, persistence, *manager, base_config, strategies/
packages/knowledge-base/tests/
packages/mcp-server/                          # (placeholder, Step 14)
src/knowledge_space/                          # constants, runtime_paths, context, bootstrap, cli/*
tests/                                        # test_cli, test_context, test_logging, test_runtime_paths, conftest
docs/                                         # documentazione e roadmap
tests/data/synthetic/legal/                   # dataset + golden queries
```
(Fonte: `docs/roadmap.md` §1 — "Monorepo con 3 pacchetti"; `README.md` "Architettura")

## 3. Entry point / CLI
- Entrambi gli script `ks` e `knowledge-space` puntano a `knowledge_space.cli:app`.
  (Fonte: `pyproject.toml` → `[project.scripts]`)
- Moduli CLI in `src/knowledge_space/cli/`: `workspace`, `domain`, `base`, `file`, `chunk`,
  `tree`, `search`, `reindex`, `config`, `status`, `models_cmd`, `common`. (Fonte: `README.md`
  "Comandi principali"; `docs/85-cli.md`; `docs/roadmap.md` §6 Step 13)
- Modalità **standalone**: ogni comando crea un `AppContext` temporaneo, opera su
  `state.json`/Chroma, termina. (Fonte: `docs/roadmap.md` §6 Step 13)

## 4. Modello di dominio
- Modelli Pydantic in `packages/knowledge-base/src/knowledge_base/models.py`: `ChunkRef`,
  `FileEntry`, `KnowledgeBase`, `Domain`, `Workspace`, `GlobalIndexData`, `WorkspaceConfigData`.
  (Fonte: `docs/roadmap.md` §2 Step 0; `docs/20-data-model.md`)
- Persistenza in `persistence.py`: `GlobalIndex`, `WorkspaceConfig` (path iniettabile, nessuna
  variabile globale). (Fonte: `docs/roadmap.md` §2 Step 0)

## 5. Manager (logica operativa)
- `WorkspaceManager` (`workspace_manager.py`): `add/remove/list/load/sync`,
  `WorkspaceWatcher` con observer iniettabile. (Fonte: `docs/roadmap.md` §2 Step 1)
- `DomainManager` (`domain_manager.py`): `create/delete/auto_generate/activate/add_base/remove_base`.
  (Fonte: `docs/roadmap.md` §2 Step 2)
- `KnowledgeBaseManager` (`knowledge_base_manager.py`): `add/remove/add_file/remove_file/sync`;
  `file_id` UUID4 stabile; `chunk_id = base::file_id::i`; diff incrementale via `content_hash`;
  chunk su disco in `<base>/.knowledge-space/chunks/<file_id>/`. (Fonte: `docs/roadmap.md` §2 Step 7)

## 6. Cascata di configurazione
- `BaseConfig` (Pydantic) in `base_config.py` con sezioni `ingestion`, `chunking`, `embedding`,
  `pre_retrieval`, `retrieval`, `post_retrieval`, `graph`. (Fonte: `docs/roadmap.md` §2 Step 3, §3, §4)
- Cascata: hardcoded → `<workspace>/.knowledge-space/defaults.toml` → `<base>/.knowledge-space/base.toml`.
  (Fonte: `docs/30-configuration.md`; `README.md` "Configurazione")
- **Trigger di reindex** (blocco cambio config): `embedding.model`, `chunking.method`,
  `ingestion.library`. (Fonte: `docs/roadmap.md` §2 Step 3)

## 7. Strategy registries
- **ingestion**: `docling`, `pymupdf4llm`, `markitdown`, `identity`. (Fonte: `docs/roadmap.md` §2 Step 4)
- **chunking**: `fixed_size`, `recursive`, `semantic` (richiede embedding), `sentence`, `markdown`.
  (Fonte: `docs/roadmap.md` §2 Step 5)
- **embedding**: 12 modelli (7 locali + 5 remoti OpenAI/Cohere/Voyage). I remoti usano
  **lazy-import**; `openai`/`cohere`/`voyageai` sono extra opzionale `remote` (NON core).
  (Fonte: `docs/roadmap.md` §2 Step 6; `packages/knowledge-base/pyproject.toml`)
- **retrieval**: `dense`/`sparse`/`hybrid` in `strategies/retrieval.py`; `sparse` usa `rank_bm25`
  (lazy import, `ImportError` se assente — attualmente `rank_bm25` NON è dichiarato come dipendenza).
  (Fonte: `docs/roadmap.md` §3; `packages/knowledge-base/src/knowledge_base/strategies/retrieval.py:192`)
- **post/pre-retrieval**: in `strategies/post_retrieval.py`, `strategies/pre_retrieval.py`.
  (Fonte: `docs/roadmap.md` §3)
- **LLM**: `LLMStrategy` (Protocol) con `generate()`/`stream()`, `llm_factory` in `strategies/llm.py`;
  mock `mock/echo`, `mock/fixed`, alias `fast`/`quality`/`local`. (Fonte: `docs/roadmap.md` §6-bis; `docs/75-llm.md`)

## 8. AppContext & bootstrap (unico punto di DI)
- `AppContext` dataclass in `knowledge_space/context.py`; `build_app_context()` in
  `knowledge_space/bootstrap.py`. Campi: `runtime_paths`, `global_index`, `workspace_manager`,
  `domain_manager`, `base_manager_factory`, `embedder_factory`, `llm_factory`,
  `graph_store_factory`, `base_config_loader`. (Fonte: `docs/roadmap.md` §2 Step 8-ter)
- `RuntimePaths` in `knowledge_space/runtime_paths.py` (non spostato in context.py).
  (Fonte: `docs/roadmap.md` §2 Step 8-ter; `knowledge_space/runtime_paths.py`)
- Vincolo: **nessuna variabile globale**, tutto passato esplicitamente.
  (Fonte: `docs/roadmap.md` §1 — "Pattern architetturali")

## 9. Convenzioni di test
- `pytest`; marker `api` (richiede `COHERE_API_KEY`, `VOYAGE_API_KEY`) e `neo4j` definiti in
  `pyproject.toml` → `[tool.pytest.ini_options].markers`. (Fonte: `pyproject.toml`)
- Test di `knowledge-base` in `packages/knowledge-base/tests/`; test app in `tests/`
  (`test_cli.py`, `test_context.py`, `test_logging.py`, `test_runtime_paths.py`). (Fonte: `tests/`)
- `tests/conftest.py` con fixtures; dataset sintetico legale in `tests/data/synthetic/legal/`
  con `golden_queries.json` e `validate.py`. (Fonte: `docs/roadmap.md` §5 Step 9)
- Comandi: `uv run pytest` (tutti), `uv run pytest tests/test_cli.py -v`,
  `uv run pytest packages/knowledge-base/tests/ -v`. (Fonte: `README.md` "Sviluppo")

## 10. Stato corrente / issue note (alla data di questa sessione)
- **13 test falliscono nel default env** (dipendenze opzionali non installate):
  - 8 test embedding remoti (`TestOpenAIEmbedding`/`TestCohereEmbedding`/`TestVoyageEmbedding`)
    → `ModuleNotFoundError: No module named 'openai'`: `_get_client()` fa lazy-import del client
    (linea ~208 di `strategies/embedding.py`); i pacchetti remoti sono extra `remote` non installato;
    i test unitari si aspettano `MissingAPIKeyError` e ricevono `ModuleNotFoundError`.
    (Fonte: `packages/knowledge-base/tests/test_embedding.py:230`; `strategies/embedding.py:208`)
  - 5 test retrieval `sparse`/`hybrid` → `ModuleNotFoundError: No module named 'rank_bm25'`
    (lazy import in `retrieval.py:192`; `rank_bm25` non dichiarato come dipendenza).
    (Fonte: `packages/knowledge-base/tests/test_retrieval.py`; `strategies/retrieval.py:192`)
- **Modifiche non committate** presenti nella working tree (WIP di terzi, NON del master):
  `src/knowledge_space/cli/config.py` (autocomplete chiavi + tabella help, comandi `set/unset/edit`,
  rilevamento trigger di reindex) e `tests/test_cli.py` (+67 righe).
  (Fonte: `git status`; `src/knowledge_space/cli/config.py`; `tests/test_cli.py`)
- I file `docs/00a-repo-context.md` e `docs/specs/*` sono scritti dal master: **non modificarli
  né committarli**.

## 11. Workflow git (convenzioni repo)
- Messaggi stile repo con prefisso: `fix:`, `feat:`, `docs:`, `chore:`
  (es. `git log`: "fix: risoluzione path base relativo e argomento scope in config show",
  "feat: config set/unset/edit + resolve_base_name per path relativi"). (Fonte: `git log`)
- Lavorare sul branch **`dev`**; non commettere mai direttamente su `main`; non pushare senza
  autorizzazione.

## 12. Mappa documentazione
- `docs/00-index.md` (indice), `docs/roadmap.md` (fonte di verità pianificazione),
  `docs/10-architecture.md`, `11-app-lifecycle.md`, `20-data-model.md`, `30-configuration.md`,
  `40-graph.md`, `45-indexing-incrementale.md`, `50-ingestion.md`, `60-chunking.md`,
  `70-embedding.md`, `75-llm.md`, `80-retrieval.md`, `85-cli.md`. (Fonte: `docs/00-index.md`)
- `AGENTS.md` — convenzioni, workflow git/test e istruzioni per sotto-agenti.
  (Fonte: `AGENTS.md`)
- `docs/specs/bug-*.md` e `docs/specs/feat-*.md` — piani di implementazione/fix generati dal master.
  (Fonte: `docs/specs/`)

## 13. Processo di delega (master agent)
- I sotto-agenti operano in tab Herdr separati: **features** e **bugs**.
- Ogni sotto-agente usa `pi` con modello `opencode-go/mimo-v2.5-pro` e thinking `high`.
- Prima di lavorare il sotto-agente deve leggere `AGENTS.md`, questo file (`docs/00a-repo-context.md`)
  e lo spec assegnato in `docs/specs/`.
- Il sotto-agente NON deve modificare né committare file sotto `docs/` o `AGENTS.md`.
- Al termine riporta: branch, file cambiati, comando e risultato dei test, dubbi.

---
*Curato dall'agente master. Aggiornare questo file quando cambiano responsabilità o struttura.*
