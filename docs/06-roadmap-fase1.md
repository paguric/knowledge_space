# Fase 1 — Logica di business completa

Tutta la logica di backend funzionante e testata: modelli, managers, configurazione, pipeline di ingestion/chunking/embedding/indicizzazione e retrieval. Al termine di questa fase `knowledge-base` è una libreria completa e testabile in isolamento.

> Per la collocazione di questa fase nel piano generale: vedi [05-roadmap-overview.md](05-roadmap-overview.md).

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

Implementare la configurazione per-base come da [03-configuration.md](03-configuration.md): file TOML, cascata di default, strategy registry.

- [ ] Aggiungere `RuntimePaths` (Pydantic) in `knowledge-space` con path XDG e convenzioni `.knowledge-space/` del workspace.
- [ ] Definire `BaseConfig` (Pydantic) con sezioni `ingestion`, `chunking`, `embedding`.
- [ ] Implementare `BaseConfigLoader` con cascata: default hardcoded → `<workspace>/.knowledge-space/defaults.toml` → `<base>/.knowledge-space/base.toml`. Warning all'avvio se `defaults.toml` manca (fallback a hardcoded). KS non riscrive mai i TOML.
- [ ] Leggere TOML con `tomllib` (stdlib Python 3.11+).
- [ ] Validare il TOML all'avvio: warning + fallback al default per valori non riconosciuti.
- [ ] Definire il **registry delle strategie** (pattern strategy/plugin) per ingestion, chunking, embedding.
- [ ] Scrivere test per: cascata di default, override, validazione, file mancanti.

### Step 4: Strategie di ingestion

Implementare diverse strategie di ingestion come plugin registrabili nel config TOML.

- [ ] Definire l'interfaccia `IngestionStrategy` (Protocol/ABC): `convert(source_path: Path) -> str`.
- [ ] Implementare strategy `docling` (già esistente, incapsulare).
- [ ] Implementare strategy `pypdf` (dipendenza leggera).
- [ ] Registrare le strategy nel registry.
- [ ] Scrivere test con file di esempio per ciascuna strategy (formati: PDF, Markdown, testo).

> **Da definire**: quali altre librerie di ingestion supportare (es. `unstructured`, `markitdown`, `textract`). Per la Fase 1 bastano `docling` + `pypdf`.

### Step 5: Strategie di chunking

Implementare diverse strategie di chunking come plugin nel registry delle strategie.

- [ ] Definire l'interfaccia `ChunkingStrategy` (Protocol/ABC): `split(text: str) -> list[Chunk]`.
- [ ] **Strategie base** (priorità 1):
  - [ ] `fixed_size` — `CharacterTextSplitter` con `chunk_size` e `chunk_overlap`; `chunk_overlap = 0` = no-overlap, `chunk_overlap > 0` = sliding window. **Una sola strategy, due comportamenti** via parametro (no duplicazione `sliding_window`).
  - [ ] `recursive` — `RecursiveCharacterTextSplitter` (separatori gerarchici `["\n\n", "\n", " ", ""]`).
  - [ ] `semantic` — `SemanticChunker` (richiede embedding; confronta embedding di frasi adiacenti per trovare boundary semantici). ⚠️ Runtime cost: embeddi ogni frase; non default in `defaults.toml`.
  - [ ] `sentence` — split per frasi (boundary `.`/`?`/`!`); `params.granularity = "sentence" | "paragraph"` (default `sentence`). Un'unica strategy con parametro, non due separate.
  - [ ] `markdown` — `MarkdownHeaderTextSplitter` (rispetta header `#`/`##`/`###`, code block intatto).
- [ ] **Strategie avanzate** (priorità 2 — **in pausa**, implementate dopo la validazione Fase 2):
  - [ ] ~~`parent_child` (Small-to-Big)~~ — **non è una strategy di chunking**; è un pattern di retrieval che arricchisce un chunker base. Esposta in `[retrieval].expansion = "none" | "parent_child"` con `parent_granularity = "section" | "paragraph"`. Vedi Step 8.
  - [ ] ~~`late_chunking`~~ — **non è una strategy di chunking**; è una modalità di embedding che richiede modello long-context (≥8192 tok). Esposta in `[embedding].mode = "standard" | "late_chunking"`, con fallback automatico a `standard` se il documento supera `max_context_tokens` del modello. Vedi Step 6.
- [ ] Parametri specifici di ciascuna strategy (`chunk_size`, `chunk_overlap`, `separators`, `granularity`, …) letti da `BaseConfig.chunking.params` (mappa libera tipizzata per strategy).
- [ ] **Contestualizzazione col modello embedding**: il chunker riceve `max_context_tokens` dal `BaseConfig.embedding` e, quando possibile, regola `chunk_size` di conseguenza; il manager (Step 7) valida ogni chunk prima dell'embedding.
- [ ] Registrare tutte le strategy base nel registry con metadati discoverable (`name`, `params_schema`, `requires_embedding`).
- [ ] Scrivere test per ciascuna strategy con testi di esempio; test specifici per `fixed_size` con `chunk_overlap = 0` vs `> 0` (no-overlap vs sliding window).

> **Da definire**: implementazione di riferimento per `semantic` (langchain `SemanticChunker` vs custom); tokenizer per `sentence` boundary in italiano (NLTK `punkt` multilingua vs regex).

### Step 6: Embedding configurabile per base

- [ ] Definire l'interfaccia `EmbeddingStrategy` (Protocol/ABC): `embed(texts: list[str]) -> list[list[float]]`.
- [ ] Implementare strategy `sentence-transformers` (già esistente, incapsulare) che accetta il nome del modello dal config.
- [ ] Implementare strategy `huggingface` (langchain `HuggingFaceEmbeddings`).
- [ ] **Supportare molteplici modelli di embedding** via registry; ogni strategia deve esporre metadati discoverable:
  - `model_name` (es. `BAAI/bge-m3`, `intfloat/multilingual-e5-small`, `Alibaba-NLP/gte-large-en-v1.5`).
  - `languages` (lista, es. `["en"]`, `["en", "it"]`, `["multilingual"]`).
  - `dim` (dimensione vettore).
  - `max_context_tokens` (lunghezza massima contesto, es. 512 per `all-mpnet-base-v2`, 8192 per `gte-large-en-v1.5` e `bge-m3`).
  - `license` (Apache 2.0, MIT, CC-BY-NC-4.0, …).
  - `requires_api` (bool; `False` per locali, `True` per OpenAI/Cohere).
- [ ] **Esposizione frontend (Fase 4)**: l'API REST e il frontend devono elencare i modelli registrati con i loro metadati, in particolare **quali lingue supportano** (italiano / inglese / multi) e la dimensione del contesto, così che l'utente possa scegliere consapevolmente il modello compatibile col proprio corpus.
- [ ] Garantire che ogni base usi il proprio modello di embedding (collection Chroma separata).
- [ ] Scrivere test di consistenza: embedding della stessa query con modelli diversi produce vettori di dimensioni diverse.

> **Da definire**: supporto per modelli locali vs API (es. `OpenAIEmbeddings`), caching degli embedding, device (CPU/GPU).

> **NOTA IMPORTANTE — dimensione del contesto** (da tenere in considerazione durante l'implementazione di Step 5 e 6): ogni modello di embedding ha un `max_context_tokens` (es. `all-mpnet-base-v2` = 384/512, `gte-large-en-v1.5` = 8192, `bge-m3` = 8192). Se un chunk troppo grande non può essere convertito dal modello, il manager deve **lanciare un errore esplicito** (non troncare silenziosamente). Si raccomanda di:
> - Aggiungere un validatore nel `KnowledgeBaseManager` (Step 7) che stima la lunghezza in token del chunk (es. via `tiktoken` per modelli EN, o tokenizer del modello stesso) PRIMA di invocare l'embedding.
> - L'errore deve includere: nome base, file, indice chunk, lunghezza token stimata, `max_context_tokens` del modello.
> - Opzionalmente, loggare un warning quando un chunk supera l'80% del `max_context_tokens` (soglia configurabile in `BaseConfig`).
> - Il chunking (Step 5) dovrebbe in heat prendere `max_context_tokens` dal `BaseConfig.embedding` per regolare `chunk_size` di conseguenza quando possibile, riducendo le probabilità di eccedere.

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

Implementare la pipeline di ricerca completa, configurabile via TOML per base. La pipeline ha **tre step sequenziali**: pre-retrieval → retrieval → post-retrieval. Ogni step accetta `method = "identity"` come **no-op esplicito** (i dati passano through, senza istanziare LLM/reranker): pipeline sempre omogenea, intento dell'utente dichiarato nel TOML. Utile per es. profilo `legal` dove le leggi non devono essere riassunte.

> **Small-to-Big (Parent-Child)**: pattern di **espansione** che si stacking sopra un chunker base (vedi Step 5). Esposto in `[retrieval].expansion = "none" | "parent_child"` con `parent_granularity = "section" | "paragraph"`. Quando `expansion = "parent_child"`, il retrieval matcha sul child ma restituisce il parent collegato; il chunker base resta libero. **Priorità 2 — in pausa**.

- [ ] **Pre-retrieval (query rewriting)** — sezione `[pre_retrieval]`:
  - Definire l'interfaccia `QueryRewriter` (Protocol/ABC): `rewrite(query: str) -> list[str]` (una query può generare sub-query).
  - Implementare strategy: `identity` (no-op, 1:1), `hyde` (Hypothetical Document Embeddings), `multi_query` (espansione con LLM in N sub-query).
  - Parametri strategy-specific in `params = {...}` (es. `multi_query` accetta `n_queries=3`, `llm=...`).
  - Registrare nel registry.
- [ ] **Retrieval** — sezione `[retrieval]`:
  - `method = "dense" | "sparse" | "hybrid"` — scelta esplicita utente.
  - Retrieval **dense**: similarity search sul vector store.
  - Retrieval **sparse**:
    - Se il modello embedding della base espone `embed_sparse` (es. `BAAI/bge-m3`), usarlo nativamente.
    - **Altrimenti fallback automatico a BM25 esterno** (`rank_bm25` sul testo grezzo dei chunk), con warning di log all'avvio.
  - Retrieval **hybrid**: ensemble di dense + sparse + fusione; `fusion = "rrf" | "weighted_sum"` (default `rrf`, robusto senza tuning pesi).
  - Rispettare i flag `active` (workspace, dominio, base, file, chunk) durante la ricerca.
  - `search(query, workspace?, domain?, kb?)` → restituisce chunk rilevanti con score.
- [ ] **Post-retrieval (rerank + compress)** — sezione `[post_retrieval]`:
  - `top_k = 10` — numero di risultati finali (applicato **ultimi**, dopo ogni altra elaborazione).
  - `reranker = "identity" | "cross_encoder" | "llm"` — riordino dei top-N; `reranker_model` opzionale (es. `BAAI/bge-reranker-v2-m3`).
  - `compressor = "identity" | "llm_chain_extract" | ...` — compression/sintesi dei contenuti passati al LLM.
  - Ordine fisso: **retrieve → rerank → compress** (l'LLM generatore vede solo ciò che esce dal compressor).
  - Definire due interfacce separate (`Reranker`, `Compressor`) perché rispondono a domande diverse ("quali sono i più rilevanti?" vs "quali contenuti passare al LLM?").
  - Implementare strategy: `identity` per entrambe (no-op), `cross_encoder` con model esterno, `llm_chain_extract` (langchain `LLMChainExtractor`).
  - Registrare nel registry.
- [ ] Estendere `BaseConfig` con sezioni `[pre_retrieval]`, `[retrieval]`, `[post_retrieval]`.
- [ ] Aggiungere dipendenza soft `rank_bm25` (BM25 fallback, puro Python).
- [ ] Validazione all'avvio: se `[retrieval].method` richiede sparse ma il modello embedding non lo supporta nativamente, montare BM25 fallback e loggare un warning (info ai fini di audit).
- [ ] Scrivere test per ciascuna fase della pipeline (con mock per le strategy LLM-based); test specifici per `identity` (no-op pass-through) e per hybrid con modello solo-dense (verifica del fallback BM25).

> **Da definire**: integrazione con LLM per query rewriting, reranking e compression (locale vs API), pesi della `weighted_sum`, supporto metadati di filtraggio al retrieval.

### Step 8-bis: Pipeline GraphRAG + edit-aware re-embedding

Costruire il grafo della conoscenza su Neo4j **riprendendo** la pipeline `neo4j-graphrag` a partire dal lexical graph, senza rifare ingestion/chunking/embedding (già calcolati da KS). Supportare l'aggiunta incrementale di documenti e l'edit dei chunk da parte dell'utente. Piano completo in [04-graph.md](04-graph.md).

- [ ] **F0 — Prerequisiti sull'ingest esistente**:
  - Spostare i chunk da `chunks_dir` globale a `<base>/.knowledge-space/chunks/<file_stem>/<file_stem>_chunk_<i>.md`.
  - ID deterministico chunk `base::file::i` in Chroma e come `Neo4jNode.id`.
  - Estensione metadata Chroma (`chunk_index`, `base_name`, `file_name`, `edited`, `content_hash`, ...) + `collection.upsert` (no `add_documents(uuid4())`).
  - Watcher sorgente ignora i path che iniziano con `.` (`.knowledge-space/` dentro la base).
  - Estensione modelli Pydantic (`ChunkRef`, `KnowledgeBase`, `WorkspaceConfigData`, `GraphConfigData`) — vedi [02-data-model.md](02-data-model.md).
  - Test di idempotenza: riesecuzione di `add_file` non duplica record Chroma né chunk su disco.
- [ ] **F1 — Pacchetto e dipendenze**: `neo4j-graphrag` + `neo4j` + extra `[nlp]` in `knowledge-base`; modulo `knowledge_base/graph/`; `graph.json` workspace + `[graph]` TOML per-base (vedi [03-configuration.md](03-configuration.md)).
- [ ] **F2 — `KSChunkLoader`**: componente custom che legge chunk da disco ed embedding da Chroma, espone `upsert_chunk` per edit-aware re-embedding.
- [ ] **F3 — Pipeline GraphRAG**: assemblaggio `KSChunkLoader -> schema (caricato da `schema.json` se esiste) -> LLMEntityRelationExtractor(create_lexical_graph=True) -> Neo4jWriter(MERGE)`.
- [ ] **F4 — Entity resolution incrementale**: `SpaCySemanticMatchResolver` default con `filter_query="WHERE NOT entity:Resolved"`, fallback a `exact` se extra `[nlp]` mancante.
- [ ] **F5 — ChunkWatcher (eager cascade)**: watcher su `<base>/.knowledge-space/chunks/**/*.md` con debounce + hash check; su edit -> upsert Chroma + re-estrazione LLM mirata sul chunk; handling delete/rename.
- [ ] **F6 — Blocco cambio modello embedding**: errore se `[embedding].model` differisce da `embedding_model` registrato e collection non vuota.
- [ ] **F7 — Test di integrazione**: vedi [04-graph.md §13](04-graph.md).
- [ ] **F7-bis — Retrieval factory**: `RetrieverFactory.build(base_config, graph_config, driver, embedder, llm)` per istanziare uno qualsiasi dei retriever supportati (vector, vector_cypher, hybrid, hybrid_cypher, text2cypher, tools) in base a `[graph].retriever` (vedi [04-graph.md §14](04-graph.md)). Creazione indici Neo4j (vector + full-text) idempotente.
- [ ] **F8 — Documentazione**: `docs/04-graph.md` + aggiornamenti `02-data-model.md`/`03-configuration.md`/`01-architecture.md`/questo file.

**Scelte consolidate**:

| Aspetto | Scelta |
|---|---|
| Grafo Neo4j | Uno per workspace |
| Resume da | Lexical graph (delegato all'estrattore) + estrazione + risoluzione |
| Schema | Caricato da `schema.json` se esiste; estratto/costruito solo la prima volta |
| Resolver | Semantico (spaCy) come default, fallback exact, configurabile in `[graph].resolver` |
| Edit chunk | Auto re-embedding via watcher + eager cascade su grafo |
| Snapshot originale | Rimandato a sviluppi futuri (vedi [04-graph.md §15](04-graph.md)) |
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