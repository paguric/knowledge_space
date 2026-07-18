# Roadmap, scelte e rischi

## Fasi di implementazione

Il lavoro è diviso in **4 fasi**:

1. **Fase 1 — Logica di business completa**: tutta la logica di backend funzionante e testata (modelli, managers, configurazione, pipeline di ingestion/chunking/embedding/indicizzazione e retrieval). Al termine di questa fase `knowledge-base` è una libreria completa e testabile in isolamento.
2. **Fase 2 — Testing e validazione**: dataset sintetici e profili di configurazione predefiniti (ricercatore/legale/studente) per validare end-to-end la pipeline completa e confrontare le configurazioni.
3. **Fase 3 — MCP + CLI**: server MCP per interrogare i workspace e interfaccia a riga di comando. Entrambi si appoggiano ai manager già consolidati nella Fase 1.
4. **Fase 4 — REST + Frontend**: layer FastAPI sopra i manager e frontend React collegato alle API.

---

## Fase 1 — Logica di business completa

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

Implementare la configurazione per-base come da [configuration.md](configuration.md): file TOML, cascata di default, strategy registry.

- [ ] Aggiungere `RuntimePaths` (Pydantic) in `knowledge-space` con path XDG e convenzioni `.knowledge-space/` del workspace.
- [ ] Definire `BaseConfig` (Pydantic) con sezioni `ingestion`, `chunking`, `embedding`.
- [ ] Implementare `BaseConfigLoader` con cascata: default hardcoded → `defaults.toml` del workspace → `bases/<base_name>.toml`.
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

Implementare diverse strategie di chunking come plugin.

- [ ] Definire l'interfaccia `ChunkingStrategy` (Protocol/ABC): `split(text: str) -> list[Chunk]`.
- [ ] Implementare strategy `fixed_size` (già esistente con `CharacterTextSplitter`).
- [ ] Implementare strategy `recursive` (langchain `RecursiveCharacterTextSplitter`).
- [ ] Implementare strategy `sentence` (split per frasi, es. `langchain_text_splitters`).
- [ ] Implementare strategy `markdown` (split rispettando la struttura Markdown, es. `MarkdownHeaderTextSplitter`).
- [ ] Registrare le strategy nel registry.
- [ ] Scrivere test per ciascuna strategy con testi di esempio.

> **Da definire**: parametri specifici di ciascuna strategy (chunk_size, overlap, separatori, ecc.) e come verranno passati dal `BaseConfig`.

### Step 6: Embedding configurabile per base

- [ ] Definire l'interfaccia `EmbeddingStrategy` (Protocol/ABC): `embed(texts: list[str]) -> list[list[float]]`.
- [ ] Implementare strategy `sentence-transformers` (già esistente, incapsulare) che accetta il nome del modello dal config.
- [ ] Implementare strategy `huggingface` (langchain `HuggingFaceEmbeddings`).
- [ ] Registrare le strategy nel registry.
- [ ] Garantire che ogni base usi il proprio modello di embedding (collection Chroma separata).
- [ ] Scrivere test di consistenza: embedding della stessa query con modelli diversi produce vettori di dimensioni diverse.

> **Da definire**: supporto per modelli locali vs API (es. `OpenAIEmbeddings`), caching degli embedding, device (CPU/GPU).

### Step 7: KnowledgeBaseManager e indicizzazione

Implementare la logica operativa sulle basi di conoscenza, orchestrando ingestion → chunking → embedding.

- [ ] Creare `KnowledgeBaseManager`:
  - `add(workspace, path)` / `remove(workspace, name)`
  - `add_file(kb, path)` → pipeline: ingestion → chunking → embedding → vector store
  - `remove_file(kb, path)` → rimozione da indice e vector store
  - `sync(kb)` → allinea file con filesystem (mtime check)
- [ ] Il manager legge `BaseConfig` (Step 3) per istanziare le strategy corrette.
- [ ] Encapsulare Chroma/langchain nel manager (nessuna variabile globale).
- [ ] Salvataggio dei chunk su disco (opzionale/da rivalutare).
- [ ] Scrivere test per ingestion, rimozione, sync mtime, ricerca base.

### Step 8: Pipeline di retrieval (pre / retrieval / post)

Implementare la pipeline di ricerca completa, configurabile via TOML per base.

- [ ] **Pre-retrieval (query rewriting)**:
  - Definire l'interfaccia `QueryRewriter` (Protocol/ABC): `rewrite(query: str) -> list[str]` (una query può generare sub-query).
  - Implementare strategy: `identity` (no-op), `hyde` (Hypothetical Document Embeddings), `multi_query` (espansione con LLM).
  - Registrare nel registry.
- [ ] **Retrieval**:
  - Implementare retrieval **dense** (similarity search sul vector store).
  - Implementare retrieval **sparse** (BM25 / keyword search).
  - Implementare **ensemble** (fusione di dense + sparse, es. Reciprocal Rank Fusion).
  - Rispettare i flag `active` (workspace, dominio, base, file, chunk) durante la ricerca.
  - `search(query, workspace?, domain?, kb?)` → restituisce chunk rilevanti con score.
- [ ] **Post-retrieval (compression)**:
  - Definire l'interfaccia `Compressor` (Protocol/ABC): `compress(documents: list, query: str) -> list`.
  - Implementare strategy: `identity` (no-op), `llm_chain_extract` (langchain `LLMChainExtractor`).
  - Registrare nel registry.
- [ ] Estendere `BaseConfig` con sezioni `[pre_retrieval]`, `[retrieval]`, `[post_retrieval]`.
- [ ] Scrivere test per ciascuna fase della pipeline (con mock per le strategy LLM-based).

> **Da definire**: integrazione con LLM per query rewriting e compression (locale vs API), algoritmi di fusione, numero di top-k configurabile, supporto metadati di filtraggio.

### Step 8-bis: Pipeline GraphRAG + edit-aware re-embedding

Costruire il grafo della conoscenza su Neo4j **riprendendo** la pipeline `neo4j-graphrag` a partire dal lexical graph, senza rifare ingestion/chunking/embedding (già calcolati da KS). Supportare l'aggiunta incrementale di documenti e l'edit dei chunk da parte dell'utente. Piano completo in [graph.md](graph.md).

- [ ] **F0 — Prerequisiti sull'ingest esistente**:
  - Spostare i chunk da `chunks_dir` globale a `<base>/.chunks/<file_stem>/<file_stem>_chunk_<i>.md`.
  - ID deterministico chunk `base::file::i` in Chroma e come `Neo4jNode.id`.
  - Estensione metadata Chroma (`chunk_index`, `base_name`, `file_name`, `edited`, `content_hash`, ...) + `collection.upsert` (no `add_documents(uuid4())`).
  - Watcher sorgente ignora i path che iniziano con `.` (`.chunks/`, `.knowledge-space/`).
  - Estensione modelli Pydantic (`ChunkRef`, `KnowledgeBase`, `WorkspaceConfigData`, `GraphConfigData`) — vedi [data-model.md](data-model.md).
  - Test di idempotenza: riesecuzione di `add_file` non duplica record Chroma né chunk su disco.
- [ ] **F1 — Pacchetto e dipendenze**: `neo4j-graphrag` + `neo4j` + extra `[nlp]` in `knowledge-base`; modulo `knowledge_base/graph/`; `graph.json` workspace + `[graph]` TOML per-base (vedi [configuration.md](configuration.md)).
- [ ] **F2 — `KSChunkLoader`**: componente custom che legge chunk da disco ed embedding da Chroma, espone `upsert_chunk` per edit-aware re-embedding.
- [ ] **F3 — Pipeline GraphRAG**: assemblaggio `KSChunkLoader -> schema (caricato da `schema.json` se esiste) -> LLMEntityRelationExtractor(create_lexical_graph=True) -> Neo4jWriter(MERGE)`.
- [ ] **F4 — Entity resolution incrementale**: `SpaCySemanticMatchResolver` default con `filter_query="WHERE NOT entity:Resolved"`, fallback a `exact` se extra `[nlp]` mancante.
- [ ] **F5 — ChunkWatcher (eager cascade)**: watcher su `.chunks/**/*.md` con debounce + hash check; su edit -> upsert Chroma + re-estrazione LLM mirata sul chunk; handling delete/rename.
- [ ] **F6 — Blocco cambio modello embedding**: errore se `[embedding].model` differisce da `embedding_model` registrato e collection non vuota.
- [ ] **F7 — Test di integrazione**: vedi [graph.md §13](graph.md).
- [ ] **F7-bis — Retrieval factory**: `RetrieverFactory.build(base_config, graph_config, driver, embedder, llm)` per istanziare uno qualsiasi dei retriever supportati (vector, vector_cypher, hybrid, hybrid_cypher, text2cypher, tools) in base a `[graph].retriever` (vedi [graph.md §14](graph.md)). Creazione indici Neo4j (vector + full-text) idempotente.
- [ ] **F8 — Documentazione**: `docs/graph.md` + aggiornamenti `data-model.md`/`configuration.md`/`architecture.md`/questo file.

**Scelte consolidate**:

| Aspetto | Scelta |
|---|---|
| Grafo Neo4j | Uno per workspace |
| Resume da | Lexical graph (delegato all'estrattore) + estrazione + risoluzione |
| Schema | Caricato da `schema.json` se esiste; estratto/costruito solo la prima volta |
| Resolver | Semantico (spaCy) come default, fallback exact, configurabile in `[graph].resolver` |
| Edit chunk | Auto re-embedding via watcher + eager cascade su grafo |
| Snapshot originale | Sì, in `.knowledge-space/snapshots/` per audit |
| Cambio modello emb. | Bloccato se collection non vuota |
| Retrieval | Configurabile `[graph].retriever` per-base (default `hybrid_cypher`); l'app istanzia solo il metodo scelto dall'utente |

---

## Fase 2 — Testing e validazione

Validare end-to-end la pipeline di business completa (Fase 1) tramite dataset sintetici e profili di configurazione predefiniti, prima di esporre il sistema tramite CLI/MCP/REST.

### Step 9: Dataset sintetici

- [ ] Definire corpus di esempio in `tests/data/synthetic/` organizzati per dominio tematico:
  - **Accademico**: paper/abstract, appunti, slide markdown.
  - **Legale**: contratti, sentenze, normative (testo strutturato con sezioni).
  - **Tecnico**: README, documentazione API, issue (markdown con codice).
- [ ] Generare documenti in formati realistici (PDF, Markdown, TXT) per coprire le strategy di ingestion.
- [ ] Definire un set di **query golden** per ogni dominio,con **risposta attesa** (chunk id / snippet / keywords) per valutare recall e precision.
- [ ] Documentare la struttura del dataset e come rigenerarlo (eventuale script).

### Step 10: Profili di configurazione predefiniti

Definire configurazioni TOML default per scenari d'uso rappresentativi. I profili sono **punti di partenza** copiabili dall'utente, non logica hardcoded.

- [ ] **`researcher`**:
  - ingestion: `docling` (gestione PDF ricca).
  - chunking: `recursive` con `chunk_size` medio-grande (1200), overlap 200.
  - embedding: modello potente (`all-mpnet-base-v2`).
  - pre-retrieval: `multi_query` (espansione LLM) o `hyde`.
  - retrieval: `ensemble` (dense + sparse).
  - post-retrieval: `llm_chain_extract` (compressione contestualizzata).
- [ ] **`legal`**:
  - ingestion: `docling` (PDF strutturati).
  - chunking: `markdown` (preserva gerarchia sezioni/articles).
  - embedding: `all-mpnet-base-v2` o modello specializzato se disponibile.
  - pre-retrieval: `identity` (query già precisa dal legale).
  - retrieval: `dense` con top-k alto + filtro metadati per articolo.
  - post-retrieval: `identity` (serve il testo originale, no compressione).
- [ ] **`student`**:
  - ingestion: `pypdf` o `docling` (bilanciato).
  - chunking: `fixed_size` 800/150 (leggero, veloce).
  - embedding: `all-MiniLM-L6-v2` (modello leggero, low RAM).
  - pre-retrieval: `identity`.
  - retrieval: `dense` top-k medio.
  - post-retrieval: `identity`.
- [ ] Salvare i profili in `configs/profiles/<name>.toml` (cartella del repo, non del workspace).
- [ ] Documentare come applicare un profilo a un workspace (`defaults.toml` del workspace = copia del profilo).

### Step 11: Test end-to-end e benchmark

- [ ] Test end-to-end (in `packages/knowledge-base/tests/e2e/`):
  - Per ciascun profilo (researcher/legal/studente), eseguire la pipeline completa (ingest → chunk → embed → retrieve) sul dataset sintetico corrispondente.
  - Verificare che i chunk rilevanti per le query golden vengano recuperati (recall ≥ soglia).
  - Verificare che i flag `active` vengano rispettati (disattivare un dominio → nessun risultato da quelle basi).
- [ ] Benchmark comparativo:
  - Confrontare i 3 profili su metriche qualitative (recall@k, MRR, latenza ingestion, latenza query).
  - Produrre un report markdown con tabelle (es. `docs/benchmark.md`).
- [ ] **Strategy LLM-based**: usare stub/mock per query rewriting e compression nei test CI; opzionale un test manuale con LLM reale (skip di default).

> **Da definire**: modello LLM da usare nei test con LLM reale (locale come `llama-cpp` o API come OpenAI/Anthropic),soglie di recall target, peso delle metriche nel benchmark.

---

## Fase 3 — MCP + CLI

Esporre i manager consolidati nella Fase 1 tramite MCP e CLI.

### Step 12: CLI con Typer

- [ ] Aggiungere `typer` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/cli.py`.
- [ ] Implementare comandi per workspace, domini, basi, file, ricerca.
- [ ] La CLI **legge** ma non scrive i file TOML (vedi [configuration.md](configuration.md)).
- [ ] Scrivere test di integrazione per i comandi CLI.

### Step 13: Server MCP

- [ ] Aggiungere `mcp` alle dipendenze di `mcp-server`.
- [ ] Rimuovere la dipendenza `mcp-server` da `knowledge-space`; aggiungere `knowledge-base` come dipendenza di `mcp-server`.
- [ ] Implementare `mcp_server/server.py` con trasporto stdio.
- [ ] Implementare i tool MCP (`list_workspaces`, `add_workspace`, `search`, `list_domains`, `activate_domain`, etc.).
- [ ] Scrivere test per MCP.

---

## Fase 4 — REST + Frontend

### Step 14: Backend REST

Thin layer FastAPI sopra i manager già testati.

- [ ] Aggiungere `fastapi` e `uvicorn` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/api/app.py` con `create_app`.
- [ ] Implementare router `health`, `workspaces`, `domains`, `bases`, `files`, `search`, `config`.
- [ ] Aggiungere CORS.
- [ ] Scrivere test per l'API.

### Step 15: Frontend React / GUI

- [ ] Collegare il frontend alle API REST.
- [ ] Permettere modifica dei file TOML dall'interfaccia (quando prevista da configuration.md).
- [ ] Visualizzare struttura ad albero (workspace → domini → basi → file → chunk).

### Step 16: Polish e documentazione

- [ ] Rimuovere codice legacy e variabili globali residue (`base.py`, `workspace.py`, `domain.py` vecchi).
- [ ] Rimuovere entrypoint CLI da `knowledge-base`.
- [ ] Aggiornare i `README.md` di tutti i pacchetti.
- [ ] Aggiornare `AGENTS.md` con le convenzioni del progetto.
- [ ] Aggiungere test end-to-end.
- [ ] Valutare la versione minima di Python: `>=3.14` è molto restrittiva. Considerare `>=3.11` o `>=3.12`.

---

## Considerazioni e rischi

### Concurrency

- L'indice globale (`GlobalIndex`) e i `config.json` non sono concurrent-safe. Se il server REST gira con più worker, l'accesso deve essere sincronizzato.
- **Chroma** PersistentClient è generalmente sicuro per un singolo processo; più processi contemporanei possono creare conflitti.
- **watchdog** usa thread. Per i test, permettere di iniettare un observer fittizio.

### Sicurezza

- Non esporre `hf_key` o altri secrets via API.
- Validare i path passati dagli utenti per evitare path traversal.
- Se il backend è esposto in rete, aggiungere autenticazione.

### Compatibilità Python

- `requires-python = ">=3.14"` è molto avanzato. Valutare `>=3.11` o `>=3.12`.

### Esecuzione simultanea REST e MCP

- La CLI può esporre due comandi separati: `serve` e `mcp`.
- In futuro, MCP in modalità SSE sullo stesso server FastAPI.

### Strategie LLM-dipendenti

- Query rewriting (HyDE, multi-query) e compression richiedono un LLM. Per la Fase 1 usare mock/stub nei test; l'integrazione reale con un LLM (locale o API) sarà decisione di configurazione.
- `EmbeddingStrategy` per base può richiedere modelli diversi caricati in memoria contemporaneamente: valutare uso di RAM e lazy loading.

## Riepilogo delle scelte consigliate

| Aspetto | Scelta consigliata |
|---------|-------------------|
| Monorepo | Mantenere workspace uv con 3 pacchetti |
| Persistenza | Ibrida: indice globale + file `config.json` per workspace |
| Configurazione basi | TOML per base + `defaults.toml` (cascata) |
| Modelli di dominio | Pydantic (`Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef`) |
| Logica operativa | Classi manager/service separate dai modelli di dominio |
| Strategy pattern | Registry per ingestion, chunking, embedding, pre/post-retrieval |
| Profili di config | `researcher` / `legal` / `student` in `configs/profiles/` |
| Testing e2e | Dataset sintetici + query golden in `tests/data/synthetic/` |
| Backend REST | FastAPI + Pydantic + uvicorn |
| Server MCP | SDK ufficiale `mcp`, trasporto stdio (poi SSE) |
| CLI | Typer |
| Configurazione app | `RuntimePaths` + `UserSettings` + `AppConfig`, passaggio esplicito |
| Persistenza | Repository pattern a medio termine |
| Iniezione dipendenze | `AppContext` a livello di applicazione |
| Versione Python | Valutare `>=3.11` o `>=3.12` al posto di `>=3.14` |

---

*Ultimo aggiornamento: 18 luglio 2026*