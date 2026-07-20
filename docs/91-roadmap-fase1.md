# Fase 1 — Logica di business completa

Tutta la logica di backend funzionante e testata: modelli, managers, configurazione, pipeline di ingestion/chunking/embedding/indicizzazione e retrieval. Al termine di questa fase `knowledge-base` è una libreria completa e testabile in isolamento.

> Per la collocazione di questa fase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md).

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

- [ ] Aggiungere `RuntimePaths` (Pydantic) in `knowledge-space` con path XDG e convenzioni `.knowledge-space/` del workspace.
- [ ] Definire `BaseConfig` (Pydantic) con sezioni `ingestion`, `chunking`, `embedding`.
- [ ] Implementare `BaseConfigLoader` con cascata: default hardcoded → `<workspace>/.knowledge-space/defaults.toml` → `<base>/.knowledge-space/base.toml`. Warning all'avvio se `defaults.toml` manca (fallback a hardcoded). KS non riscrive mai i TOML.
- [ ] Leggere TOML con `tomllib` (stdlib Python 3.11+).
- [ ] Validare il TOML all'avvio: warning + fallback al default per valori non riconosciuti.
- [ ] Definire il **registry delle strategie** (pattern strategy/plugin) per ingestion, chunking, embedding.
- [ ] Scrivere test per: cascata di default, override, validazione, file mancanti.

### Step 4: Strategie di ingestion

Implementare secondo la specifica [50-ingestion.md](50-ingestion.md).

- [ ] Interfaccia `IngestionStrategy` e registry (`knowledge_base/strategies/ingestion.py`).
- [ ] Strategy `docling` (PDF, paper/legale) — parametri: `do_ocr`, `do_table_structure`, `table_mode`, `image_export`.
- [ ] Strategy `pymupdf4llm` (PDF, textbook) — parametri: `page_chunks`, `write_images`, `extract_mode`.
- [ ] Strategy `markitdown` (PPTX/slide) — parametri minimi (estensione via plugin).
- [ ] Strategy `pypdf` (fallback leggero, PDF semplice).
- [ ] Validazione formati: estensione vs `supported_extensions` della strategy; rifiuto esplicito.
- [ ] Test per ciascuna strategy con file in `tests/data/synthetic/`.

### Step 5: Strategie di chunking

Implementare secondo la specifica [60-chunking.md](60-chunking.md).

- [ ] Interfaccia `ChunkingStrategy` e registry (`knowledge_base/strategies/chunking.py`).
- [ ] Strategy `fixed_size` (chunk_overlap=0 no-overlap, >0 sliding window — unica classe, due comportamenti).
- [ ] Strategy `recursive` (separatori gerarchici `["\n\n", "\n", " ", ""]`).
- [ ] Strategy `semantic` (richiede embedding, non default).
- [ ] Strategy `sentence` (granularity = "sentence" | "paragraph").
- [ ] Strategy `markdown` (MarkdownHeaderTextSplitter, code block intatto).
- [ ] Contestualizzazione: riceve `max_context_tokens` per regolare chunk_size.
- [ ] Registry con metadati discoverable (`params_schema`, `requires_embedding`).
- [ ] Test per ciascuna strategy; test fixed_size overlap=0 vs >0.

### Step 6: Embedding configurabile per base

Implementare secondo la specifica [70-embedding.md](70-embedding.md).

- [ ] Interfaccia `EmbeddingStrategy`, `EmbeddingMetadata` e registry (`knowledge_base/strategies/embedding.py`).
- [ ] Popolare registry con i 7 modelli di embedding (da `all-mpnet-base-v2` a `multilingual-e5-large`) — ciascuno con metadati: `languages`, `dim`, `max_context_tokens`, `license`.
- [ ] Collection Chroma separata per base, creata con `dim` dal modello configurato.
- [ ] Validatore chunk vs `max_context_tokens`: errore esplicito se un chunk eccede il limite.
- [ ] Test: embedding con modelli diversi → vettori di dimensioni diverse; errore atteso su chunk troppo grande.

### Step 7: KnowledgeBaseManager e indicizzazione

Implementare la logica operativa sulle basi di conoscenza, orchestrando ingestion → chunking → embedding.

- [ ] Creare `KnowledgeBaseManager`:
  - `add(workspace, path)` / `remove(workspace, name)`
  - `add_file(kb, path)` → pipeline: ingestion → chunking → embedding → vector store
  - `remove_file(kb, path)` → rimozione da indice e vector store
  - `sync(kb)` → allinea file con filesystem (mtime check)
- [ ] Il manager legge `BaseConfig` (Step 3) per istanziare le strategy corrette.
- [ ] **Validazione lunghezza chunk vs `max_context_tokens`** dell'embedding (vedi nota Step 6): errore esplicito se un chunk eccede il limite del modello.
- [ ] Encapsulare Chroma/langchain nel manager (nessuna variabile globale).
- [ ] **Salvataggio chunk su disco obbligatorio** in `<base>/.knowledge-space/chunks/<file_stem>/<file_stem>_chunk_<i>.md` (formato Markdown, editabile dall'utente). Prerequisito per Step 8-bis. I chunk su disco sono la sorgente di verità:
  - Il manager scrive i chunk al termine della pipeline di chunking; se il file `.knowledge-space/chunks/<file_stem>/` esiste già (re-ingest), sovrascrive solo i chunk aggiornati (mtime check) e lascia intatti quelli editati (flag `edited=true` su `ChunkRef`).
  - I chunk su disco hanno la precedenza sull'eventuale testo ricalcolato: se l'utente edita un `.md`, il watcher di Step 8-bis re-embedda solo quelli modificati (content hash check, vedi `ChunkRef.content_hash`).
- [ ] **ID deterministico** per chunk: `chunk_id = f"{base_name}::{file_stem}::{i}"` (usato come chiave in Chroma e come `Neo4jNode.id`).
- [ ] **Estensione metadata Chroma**: `chunk_id`, `base_name`, `file_name`, `chunk_index`, `edited`, `content_hash`; `collection.upsert` (no `add_documents(uuid4())`) — prerequisito Step 8-bis F0.
- [ ] **Migrazione retroattiva** dei `config.json` esistenti (campi opzionali Pydantic con default copre la lettura, ma il manager deve popolare i nuovi campi alla prima sync): `chunk_id`, `content_hash`, `embedding_model`, e sezione `graph` se assente. Idempotenza: riesecuzione di `add_file` non duplicare record Chroma né chunk su disco.
- [ ] Scrivere test per ingestion, rimozione, sync mtime, ricerca base, **test che verifichi il lancio dell'errore quando un chunk eccede `max_context_tokens`**, e **test di idempotenza** (add_file × 2 = stessi chunk_id e stessi record Chroma).

### Step 8: Pipeline di retrieval (pre / retrieval / post)

Implementare secondo la specifica [80-retrieval.md](80-retrieval.md). La pipeline ha tre step sequenziali: pre-retrieval → retrieval → post-retrieval. Ogni step accetta `method = "identity"` come no-op esplicito.

- [ ] Interfacce `QueryRewriter`, `RetrievalStrategy`, `Reranker`, `Compressor` (Protocol) e registry (`knowledge_base/strategies/retrieval/`).
- [ ] Pre-retrieval: `identity` (no-op), `hyde`, `multi_query`.
- [ ] Retrieval: `dense` (vector store), `sparse` (BM25 fallback automatico via `rank_bm25`), `hybrid` (fusion `rrf`, `weighted_sum`).
- [ ] Post-retrieval: `reranker` (identity, cross_encoder), `compressor` (identity, llm_chain_extract).
- [ ] Rispetto flag `active` durante la ricerca.
- [ ] Test per ciascuna fase (mock per strategy LLM-based); test identity pass-through; test hybrid con fallback BM25.

> **Da definire**: integrazione con LLM per query rewriting, reranking e compression (locale vs API), pesi della `weighted_sum`, supporto metadati di filtraggio al retrieval.

### Step 8-bis: Pipeline GraphRAG + edit-aware re-embedding

Costruire il grafo della conoscenza su Neo4j **riprendendo** la pipeline `neo4j-graphrag` a partire dal lexical graph, senza rifare ingestion/chunking/embedding (già calcolati da KS). Supportare l'aggiunta incrementale di documenti e l'edit dei chunk da parte dell'utente. Piano completo in [40-graph.md](40-graph.md).

- [ ] **F0 — Prerequisiti sull'ingest esistente**:
  - Spostare i chunk da `chunks_dir` globale a `<base>/.knowledge-space/chunks/<file_stem>/<file_stem>_chunk_<i>.md`.
  - ID deterministico chunk `base::file::i` in Chroma e come `Neo4jNode.id`.
  - Estensione metadata Chroma (`chunk_index`, `base_name`, `file_name`, `edited`, `content_hash`, ...) + `collection.upsert` (no `add_documents(uuid4())`).
  - Watcher sorgente ignora i path che iniziano con `.` (`.knowledge-space/` dentro la base).
  - Estensione modelli Pydantic (`ChunkRef`, `KnowledgeBase`, `WorkspaceConfigData`, `GraphConfigData`) — vedi [20-data-model.md](20-data-model.md).
  - Test di idempotenza: riesecuzione di `add_file` non duplica record Chroma né chunk su disco.
- [ ] **F1 — Pacchetto e dipendenze**: `neo4j-graphrag` + `neo4j` + extra `[nlp]` in `knowledge-base`; modulo `knowledge_base/graph/`; `graph.json` workspace + `[graph]` TOML per-base (vedi [30-configuration.md](30-configuration.md)).
- [ ] **F2 — `KSChunkLoader`**: componente custom che legge chunk da disco ed embedding da Chroma, espone `upsert_chunk` per edit-aware re-embedding.
- [ ] **F3 — Pipeline GraphRAG**: assemblaggio `KSChunkLoader -> schema (caricato da `schema.json` se esiste) -> LLMEntityRelationExtractor(create_lexical_graph=True) -> Neo4jWriter(MERGE)`.
- [ ] **F4 — Entity resolution incrementale**: `SpaCySemanticMatchResolver` default con `filter_query="WHERE NOT entity:Resolved"`, fallback a `exact` se extra `[nlp]` mancante.
- [ ] **F5 — ChunkWatcher (eager cascade)**: watcher su `<base>/.knowledge-space/chunks/**/*.md` con debounce + hash check; su edit -> upsert Chroma + re-estrazione LLM mirata sul chunk; handling delete/rename.
- [ ] **F6 — Blocco cambio modello embedding**: errore se `[embedding].model` differisce da `embedding_model` registrato e collection non vuota.
- [ ] **F7 — Test di integrazione**: vedi [40-graph.md §13](40-graph.md).
- [ ] **F7-bis — Retrieval factory**: `RetrieverFactory.build(base_config, graph_config, driver, embedder, llm)` per istanziare uno qualsiasi dei retriever supportati (vector, vector_cypher, hybrid, hybrid_cypher, text2cypher, tools) in base a `[graph].retriever` (vedi [40-graph.md §14](40-graph.md)). Creazione indici Neo4j (vector + full-text) idempotente.
- [ ] **F8 — Documentazione**: `docs/40-graph.md` + aggiornamenti `20-data-model.md`/`30-configuration.md`/`10-architecture.md`/questo file.

**Scelte consolidate**:

| Aspetto | Scelta |
|---|---|
| Grafo Neo4j | Uno per workspace |
| Resume da | Lexical graph (delegato all'estrattore) + estrazione + risoluzione |
| Schema | Caricato da `schema.json` se esiste; estratto/costruito solo la prima volta |
| Resolver | Semantico (spaCy) come default, fallback exact, configurabile in `[graph].resolver` |
| Edit chunk | Auto re-embedding via watcher + eager cascade su grafo |
| Snapshot originale | Rimandato a sviluppi futuri (vedi [40-graph.md §15](40-graph.md)) |
| Cambio modello emb. | Bloccato se collection non vuota |
| Retrieval | Configurabile `[graph].retriever` per-base (default `hybrid_cypher`); l'app istanzia solo il metodo scelto dall'utente |

### Step 8-ter: `AppContext` e bootstrap dell'applicazione

`knowledge-base` è una libreria pura senza alcuna conoscenza di XDG, APP_NAME o variabili globali. Il **wiring** avviene in `knowledge-space`, che costruisce un `AppContext` e lo passa esplicitamente a CLI, MCP server e REST API. Questo step introduce l'unico punto dell'app in cui le dipendenze vengono assemblate; tutti gli entrypoint (Step 12 CLI, Step 13 MCP, Step 14 REST) ricevono un `AppContext` già pronto (o un factory che lo costruisce da `RuntimePaths`).

- [ ] Definire `RuntimePaths` (Pydantic) in `knowledge_space`: path XDG (`data_home`, `state_home`, `config_home`) + convenzione `<workspace>/.knowledge-space/`. Costruito da `APP_NAME` + env (default XDG spec, overridable per test).
- [ ] Definire `AppContext` (Pydantic o dataclass) in `knowledge_space.context`:
  - `runtime_paths: RuntimePaths`
  - `global_index: GlobalIndex` (con path=`runtime_paths.state_home/...`)
  - `workspace_manager: WorkspaceManager`
  - `domain_manager: DomainManager`
  - `base_manager_factory: Callable[[WorkspaceConfig, BaseConfig], KnowledgeBaseManager]` — factory per base (riusa i manager già testati della Fase 1).
  - `embedder_factory: Callable[[str], EmbeddingStrategy]` — lazy, modello caricato on-demand.
  - `llm_factory: Callable[[str], LLMStrategy]` (per query rewriting, reranking, compression, GraphRAG).
  - `graph_store_factory: Callable[[GraphConfigData], GraphStore]` (Step 8-bis; opzionale — `None` se Neo4j non configurato).
  - `base_config_loader: BaseConfigLoader` (Step 3), che legge `defaults.toml` del workspace + `<base>/.knowledge-space/base.toml`.
- [ ] Implementare `build_app_context(runtime_paths: RuntimePaths | None = None) -> AppContext` in `knowledge_space.bootstrap` (entrypoint unico; default usa `RuntimePaths.default()`).
- [ ] **Nessuna variabile globale**: l'AppContext è l'unico stato condiviso; CLI/MCP/REST lo ricevono come argomento o tramite `fastapi.Depends`.
- [ ] Validazione all'avvio: avvertire se `[graph]` configurato ma Neo4j non raggiungibile (downgrade a vectore solo con warning).
- [ ] Scrivere test in `packages/knowledge-space/tests/`: costruzione `AppContext` con `RuntimePaths` temporanei (tmp_path), mocking delle factory, verifica che i manager ricevono path corretti (no XDG reale).

> **Anticipato rispetto a CLI**: questo step è nella **Fase 1** perché il CLI (Step 12) ne ha bisogno, e perché tenerlo nella Fase 3 nasconderebbe un rischio architetturale (iniezione di dipendenze) sotto la logica di presentazione. L'implementazione è in `knowledge-space` (app, non libreria), ma i test di wiring sono puri e isolati con `tmp_path`.

---

*Ultimo aggiornamento: 21 luglio 2026*