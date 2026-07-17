# Roadmap, scelte e rischi

## Fasi di implementazione

Il lavoro è diviso in **3 fasi**:

1. **Fase 1 — Logica di business completa**: tutta la logica di backend funzionante e testata (modelli, managers, configurazione, pipeline di ingestion/chunking/embedding/indicizzazione e retrieval). Al termine di questa fase `knowledge-base` è una libreria completa e testabile in isolamento.
2. **Fase 2 — MCP + CLI**: server MCP per interrogare i workspace e interfaccia a riga di comando. Entrambi si appoggiano ai manager già consolidati nella Fase 1.
3. **Fase 3 — REST + Frontend**: layer FastAPI sopra i manager e frontend React collegato alle API.

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

---

## Fase 2 — MCP + CLI

Esporre i manager consolidati nella Fase 1 tramite MCP e CLI.

### Step 9: CLI con Typer

- [ ] Aggiungere `typer` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/cli.py`.
- [ ] Implementare comandi per workspace, domini, basi, file, ricerca.
- [ ] La CLI **legge** ma non scrive i file TOML (vedi [configuration.md](configuration.md)).
- [ ] Scrivere test di integrazione per i comandi CLI.

### Step 10: Server MCP

- [ ] Aggiungere `mcp` alle dipendenze di `mcp-server`.
- [ ] Rimuovere la dipendenza `mcp-server` da `knowledge-space`; aggiungere `knowledge-base` come dipendenza di `mcp-server`.
- [ ] Implementare `mcp_server/server.py` con trasporto stdio.
- [ ] Implementare i tool MCP (`list_workspaces`, `add_workspace`, `search`, `list_domains`, `activate_domain`, etc.).
- [ ] Scrivere test per MCP.

---

## Fase 3 — REST + Frontend

### Step 11: Backend REST

Thin layer FastAPI sopra i manager già testati.

- [ ] Aggiungere `fastapi` e `uvicorn` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/api/app.py` con `create_app`.
- [ ] Implementare router `health`, `workspaces`, `domains`, `bases`, `files`, `search`, `config`.
- [ ] Aggiungere CORS.
- [ ] Scrivere test per l'API.

### Step 12: Frontend React / GUI

- [ ] Collegare il frontend alle API REST.
- [ ] Permettere modifica dei file TOML dall'interfaccia (quando prevista da configuration.md).
- [ ] Visualizzare struttura ad albero (workspace → domini → basi → file → chunk).

### Step 13: Polish e documentazione

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
| Backend REST | FastAPI + Pydantic + uvicorn |
| Server MCP | SDK ufficiale `mcp`, trasporto stdio (poi SSE) |
| CLI | Typer |
| Configurazione app | `RuntimePaths` + `UserSettings` + `AppConfig`, passaggio esplicito |
| Persistenza | Repository pattern a medio termine |
| Iniezione dipendenze | `AppContext` a livello di applicazione |
| Versione Python | Valutare `>=3.11` o `>=3.12` al posto di `>=3.14` |

---

*Ultimo aggiornamento: 17 luglio 2026*