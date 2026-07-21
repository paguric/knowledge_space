# Fase 1A — Ingestione e indicizzazione vettoriale

Pipeline completa: documento sorgente → ingestion → chunking → embedding → Chroma. Include sync filesystem, configurazione per-base, strategy registry per ingestion/chunking/embedding, e la gestione incrementale dell'indice vettoriale su eventi (content change, move/rename, cambio config).

Al termine di questa sottofase `knowledge-base` sa:
- Caricare/scrivere lo stato del workspace (`state.json`)
- Sincronizzare le basi col filesystem (watcher watchdog)
- Leggere la configurazione TOML per-base con cascata di default
- Ingestire documenti in 6 formati con 3 librerie (docling, pymupdf4llm, markitdown)
- Chunkare il testo con 5 strategie (fixed_size, recursive, semantic, sentence, markdown)
- Embeddare i chunk con modelli locali o remoti (OpenAI, Cohere, Voyage)
- Indicizzare il tutto in Chroma (collection per base, ID deterministici)
- Rilevare cambiamenti ai file sorgente e re-indicizzare solo chunk cambiati (hash diff)
- Gestire move/rename senza ricalcolare embedding
- Bloccare cambi di config (modello/chunking/ingestion) su collection non vuota

> Per la collocazione di questa sottofase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md). Per la specifica dei trigger di reindex vettoriale: vedi [45-indexing-incrementale.md](45-indexing-incrementale.md) trigger 1–5. Per le specifiche di configurazione, ingestion, chunking, embedding: vedi [30-configuration.md](30-configuration.md), [50-ingestion.md](50-ingestion.md), [60-chunking.md](60-chunking.md), [70-embedding.md](70-embedding.md).

---

### Step 0: Modello di dominio e persistenza ibrida

Fondamenta su cui poggiano tutti gli altri step.

- [x] Definire modelli Pydantic in `knowledge_base/models.py`:
  - `ChunkRef`, `FileEntry`, `KnowledgeBase`, `Domain`, `Workspace`, `GlobalIndexData`, `WorkspaceConfigData`.
- [x] Creare `GlobalIndex` per caricare/salvare l'indice globale (path iniettabile, nessuna conoscenza di app/XDG).
- [x] Creare `WorkspaceConfig` per caricare/salvare la configurazione del workspace (path iniettabile).
- [x] Rimuovere le variabili globali dai nuovi moduli (legacy non ancora toccato).
- [x] Scrivere test di roundtrip JSON per `WorkspaceConfig` e `GlobalIndex` (16 test).

### Step 1: Workspace e sincronizzazione col filesystem

- [x] Creare `WorkspaceManager`:
  - `add(path)` / `remove(path)` / `list()`
  - `load(path)` → restituisce `Workspace`
  - `sync(workspace)` → allinea basi (cartelle) col filesystem
  - `set_last_workspace(path)` / `get_last_workspace()`
- [x] Integrare `watchdog` per sincronizzazione a runtime (`WorkspaceWatcher`, observer iniettabile).
- [x] Scrivere test per CRUD workspace e sincronizzazione FS (8 test).

### Step 2: Domini

- [x] Creare `DomainManager`:
  - `create(workspace, name, base_names)` / `delete(workspace, name)`
  - `auto_generate(workspace)` dalla struttura di cartelle (lvl1 + sottocartelle → dominio; foglie del sottoalbero → basi)
  - `activate(workspace, name)` / `deactivate(workspace, name)`
  - `add_base(workspace, domain, base)` / `remove_base(workspace, domain, base)`
- [x] Scrivere test per creazione, auto-generazione e flag `active` (10 test).

### Step 3: Configurazione delle basi (TOML)

Implementare la configurazione per-base come da [30-configuration.md](30-configuration.md): file TOML, cascata di default, strategy registry.

- [x] Aggiungere `RuntimePaths` (Pydantic) in `knowledge-space` con path XDG e convenzioni `.knowledge-space/` del workspace.
- [x] Definire `BaseConfig` (Pydantic) con sezioni `ingestion`, `chunking`, `embedding`.
- [x] Implementare `BaseConfigLoader` con cascata: default hardcoded → `<workspace>/.knowledge-space/defaults.toml` → `<base>/.knowledge-space/base.toml`. Warning all'avvio se `defaults.toml` manca (fallback a hardcoded). KS non riscrive mai i TOML.
- [x] Leggere TOML con `tomllib` (stdlib Python 3.11+).
- [x] Validare il TOML all'avvio: warning + fallback al default per valori non riconosciuti.
- [x] Definire il **registry delle strategie** (pattern strategy/plugin) per ingestion, chunking, embedding.
- [x] Blocco cambio config all'avvio: se `[embedding].model` / `[chunking].method` / `[ingestion].library` differisce da quanto registrato in `state.json` per la base **e** la collection Chroma non è vuota → errore esplicito che suggerisce `ks reindex <base> --<reason>` (vedi [45-indexing-incrementale.md](45-indexing-incrementale.md) trigger 3/4/5 per i dettagli del blocco e dello sblocco esplicito).
- [x] Scrivere test per: cascata di default, override, validazione, file mancanti, blocco cambio config (22 test in `test_base_config.py` + 6 test `test_runtime_paths.py`).

### Step 4: Strategie di ingestion

Implementare secondo la specifica [50-ingestion.md](50-ingestion.md).

- [x] Interfaccia `IngestionStrategy` e registry (`knowledge_base/strategies/ingestion.py`). Parametro globale `use_gpu` (default `false`).
- [x] Strategy `docling` (PDF, profilo ricercatore) — parametri: `use_gpu`, `do_ocr`, `do_table_structure`, `table_mode`, `image_export`.
- [x] Strategy `pymupdf4llm` (PDF, profilo consulente) — parametri: `page_chunks`, `write_images`, `extract_mode`.
- [x] Strategy `markitdown` (PPTX, MD, profilo studente) — parametri minimi (estensione via plugin).
- [x] Validazione formati: estensione vs `supported_extensions` della strategy; rifiuto esplicito.
- [x] Test per ciascuna strategy con file in `tests/data/synthetic/`.

### Step 5: Strategie di chunking

Implementare secondo la specifica [60-chunking.md](60-chunking.md).

- [ ] Interfaccia `ChunkingStrategy` e registry (`knowledge_base/strategies/chunking.py`).
- [ ] Strategy `fixed_size` (chunk_overlap=0 no-overlap, >0 sliding window — unica classe, due comportamenti).
- [ ] Strategy `recursive` (separatori gerarchici `["\n\n", "\n", " ", ""]`).
- [ ] Strategy `semantic` (richiede embedding, non default).
- [ ] Strategy `sentence` (granularity = "sentence" | "paragraph").
- [ ] Strategy `markdown` (MarkdownHeaderTextSplitter, code block intatto).
- [ ] Registry con metadati discoverable (`params_schema`, `requires_embedding`).
- [ ] Test per ciascuna strategy; test fixed_size overlap=0 vs >0.

### Step 6: Embedding configurabile per base

Implementare secondo la specifica [70-embedding.md](70-embedding.md).

- [ ] Interfaccia `EmbeddingStrategy`, `EmbeddingMetadata` e registry (`knowledge_base/strategies/embedding.py`).
- [ ] Popolare registry con tutti i modelli di embedding supportati (locali + remoti: OpenAI, Cohere, Voyage) — ciascuno con metadati: `languages`, `dim`, `max_context_tokens`, `license`, `requires_api`.
- [ ] Collection Chroma separata per base, creata con `dim` dal modello configurato.
- [ ] Validatore chunk vs `max_context_tokens`: errore esplicito se un chunk eccede il limite.
- [ ] Test: embedding con modelli diversi → vettori di dimensioni diverse; errore atteso su chunk troppo grande.

### Step 7: KnowledgeBaseManager e indicizzazione

Implementare la logica operativa sulle basi di conoscenza, orchestrando ingestion → chunking → embedding → Chroma. Include `file_id` (UUID stabile per rename), diff incrementale via `content_hash`, e gestione move/rename senza recompute.

- [ ] **Estendere modelli Pydantic** (prerequisito per grafo, ma implementato qui perché modifica la pipeline di indicizzazione):
  - `FileEntry`: aggiungere `file_id: str` (UUID4 generato alla prima indicizzazione, stabile per la vita del file).
  - `ChunkRef`: rimuovere `edited`/`edited_mtime`. `chunk_id = f"{base_name}::{file_id}::{i}"`.
  - `KnowledgeBase`: aggiungere `chunking_method: Optional[str]` e `ingestion_library: Optional[str]` (per blocco cambio config).
  - `WorkspaceConfigData` / `GraphConfigData`: sezione `graph`.
- [ ] Creare `KnowledgeBaseManager`:
  - `add(workspace, path)` / `remove(workspace, name)`
  - `add_file(kb, path)` → pipeline: ingestion → chunking → embedding → vector store
  - `remove_file(kb, path)` → rimozione da indice e vector store
  - `sync(kb)` → allinea file con filesystem (mtime check)
- [ ] Il manager legge `BaseConfig` (Step 3) per istanziare le strategy corrette.
- [ ] **Validazione lunghezza chunk vs `max_context_tokens`** dell'embedding: errore esplicito se un chunk eccede il limite del modello.
- [ ] Encapsulare Chroma/langchain nel manager (nessuna variabile globale).
- [ ] **ID deterministico per chunk**: `chunk_id = f"{base_name}::{file_id}::{i}"` (usato come chiave in Chroma e come `Neo4jNode.id`). Disaccoppia dal filename: rename del file sorgente non cambia `chunk_id` (vedi trigger 2 di [45-indexing-incrementale.md](45-indexing-incrementale.md)).
- [ ] **Salvataggio chunk su disco obbligatorio**: `<base>/.knowledge-space/chunks/<file_id>/<file_id>_chunk_<i>.md` (prodotto derivato, non editabile dall'utente). Il manager riscrive solo i chunk con `content_hash` cambiato.
- [ ] **Estensione metadata Chroma**: `chunk_id`, `base_name`, `file_name`, `file_id`, `chunk_index`, `content_hash`; `collection.upsert` (no `add_documents(uuid4())`). Niente `edited`/`edited_mtime`.
- [ ] **Diff incrementale su re-ingest** (trigger 1 di [45-indexing-incrementale.md](45-indexing-incrementale.md)): dopo re-chunk, confronta `content_hash` dei nuovi chunk con quelli vecchi. Solo chunk con hash diverso vengono re-embeddati e upsertati in Chroma. Chunk invariati saltati. Su inserimento in mezzo al documento, approccio **B** (shift accettato, re-embed da quel punto in poi).
- [ ] **Move/rename senza recompute** (trigger 2 di [45-indexing-incrementale.md](45-indexing-incrementale.md)): update `FileEntry.path`/`FileEntry.name` + metadata Chroma (file_name). `chunk_id` immutato (basato su `file_id`). Zero re-embed.
- [ ] **Migrazione retroattiva** dei `state.json` esistenti: `file_id` (generato), `chunk_id` (rigenerato), `content_hash` (calcolato), `embedding_model`, `chunking_method`, `ingestion_library`, sezione `graph`.
- [ ] Scrivere test per: ingestion, rimozione, sync mtime, diff incrementale, move/rename idempotente, errore `max_context_tokens`, idempotenza (add_file × 2).

### Step 8-ter: `AppContext` e bootstrap dell'applicazione

`knowledge-base` è una libreria pura senza alcuna conoscenza di XDG, APP_NAME o variabili globali. Il **wiring** avviene in `knowledge-space`, che costruisce un `AppContext` e lo passa esplicitamente a CLI, MCP server e REST API. Questo step introduce l'unico punto dell'app in cui le dipendenze vengono assemblate; tutti gli entrypoint (Step 12 CLI, Step 13 MCP, Step 14 REST) ricevono un `AppContext` già pronto (o un factory che lo costruisce da `RuntimePaths`).

- [ ] Definire `RuntimePaths` (Pydantic) in `knowledge_space`: path XDG (`data_home`, `state_home`, `config_home`) + convenzione `<workspace>/.knowledge-space/`. Costruito da `APP_NAME` + env (default XDG spec, overridable per test).
- [ ] Definire `AppContext` (Pydantic o dataclass) in `knowledge_space.context`:
  - `runtime_paths: RuntimePaths`
  - `global_index: GlobalIndex`
  - `workspace_manager: WorkspaceManager`
  - `domain_manager: DomainManager`
  - `base_manager_factory: Callable[[WorkspaceConfig, BaseConfig], KnowledgeBaseManager]`
  - `embedder_factory: Callable[[str], EmbeddingStrategy]` — lazy, modello caricato on-demand.
  - `llm_factory: Callable[[str], LLMStrategy]` (per query rewriting, reranking, compression, GraphRAG — stub fino a Fase 1B/1C).
  - `graph_store_factory: Callable[[GraphConfigData], GraphStore]` (opzionale — `None` se Neo4j non configurato; concreta in Fase 1C).
  - `base_config_loader: BaseConfigLoader` (Step 3), che legge `defaults.toml` del workspace + `<base>/.knowledge-space/base.toml`.
- [ ] Implementare `build_app_context(runtime_paths: RuntimePaths | None = None) -> AppContext` in `knowledge_space.bootstrap` (entrypoint unico; default usa `RuntimePaths.default()`).
- [ ] **Nessuna variabile globale**: l'AppContext è l'unico stato condiviso; CLI/MCP/REST lo ricevono come argomento o tramite `fastapi.Depends`.
- [ ] Scrivere test in `packages/knowledge-space/tests/`: costruzione `AppContext` con `RuntimePaths` temporanei (tmp_path), mocking delle factory, verifica che i manager ricevono path corretti (no XDG reale).

> **Anticipato rispetto a CLI**: questo step è in questa sottofase perché la CLI (Fase 3) ne ha bisogno, e perché tenerlo in una fase successiva nasconderebbe un rischio architetturale (iniezione di dipendenze) sotto la logica di presentazione.

> **Modalità esecuzione**: in Fase 1–3 la CLI opera in **modalità standalone** (ogni comando è un processo separato, crea un `AppContext` temporaneo, opera su `state.json`/Chroma, termina). Non ci sono watcher in background. Il backend process (watcher+REST+MCP) e la modalità CLI client saranno introdotti in Fase 4. Vedi [11-app-lifecycle.md](11-app-lifecycle.md).

## Comandi CLI (da implementare in Fase 3, progettati qui)

| Comando | Trigger | Cosa fa (parte vettoriale) |
|---|---|---|
| `ks reindex <base> --model-change` | 3 | Nuova collection Chroma con `dim` del nuovo modello, re-embed da disco. Aggiorna `embedding_model` in stato. La propagazione al grafo è differita a Fase 1C. |
| `ks reindex <base> --chunking-change` | 4 | Re-chunk + re-embed + riscrittura chunk su disco. Delete+insert in Chroma. Backup opzionale in `<file_id>__<ts>/`. La propagazione al grafo è differita a Fase 1C. |
| `ks reindex <base> --ingestion-change` | 5 | Re-ingest + re-chunk + re-embed + riscrittura chunk. Come trigger 4 ma parte da ingestion. La propagazione al grafo è differita a Fase 1C. |

Il blocco (errore all'avvio se config cambiata) è implementato in Step 3 + Step 7. I comandi `ks reindex` implementano solo la parte vettoriale in questa sottofase; la propagazione al grafo verrà aggiunta in Fase 1C.

## Scelte consolidate per questa sottofase

| Aspetto | Scelta |
|---|---|
| `file_id` | UUID4 stabile per la vita del file; `chunk_id = base::file_id::i` |
| Chunk su disco | Prodotto derivato, non editabile. Path: `<file_id>/<file_id>_chunk_<i>.md` |
| Chunk ID stabile | Disaccoppia dal nome file → rename non cambia `chunk_id` |
| Diff incrementale | `content_hash` su re-chunk, re-embed solo hash diversi. Approccio B su insert in mezzo (shift accettato) |
| Chroma metadata | `chunk_id`, `base_name`, `file_name`, `file_id`, `chunk_index`, `content_hash`. Niente `edited`/`edited_mtime` |
| Blocco cambio config | Errore se `model`/`method`/`library` diverso da registrato e collection non vuota |
| Move/rename | Metadata-only: `file_name` in Chroma + `FileEntry.path`/`name` in stato. Zero embedding |

## Dipendenze tra sottofasi

- **Fase 1B** (retrieval) dipende da: Step 7 (KnowledgeBaseManager con Chroma funzionante).
- **Fase 1C** (GraphRAG) dipende da: Step 7 (file_id, chunk_id, Chroma funzionante, chunk su disco, diff incrementale).

---

*Ultimo aggiornamento: 21 luglio 2026*
