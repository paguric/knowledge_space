# Roadmap — Knowledge Space

> **Ultimo aggiornamento:** 25 luglio 2026

---

## §0 — Dashboard

Tabella compatta di tutto il progetto. Leggi questa sezione per capire **dove siamo** e **cosa manca** in 2 minuti.

### Stato degli step

| # | Step | Fase | Stato | Dipendenze | Prossimo passo |
|---|------|------|-------|------------|----------------|
| 0 | Modello di dominio e persistenza | 1A | ✅ Fatto | — | — |
| 1 | Workspace e sync FS | 1A | ✅ Fatto | Step 0 | — |
| 2 | Domini | 1A | ✅ Fatto | Step 1 | — |
| 3 | Configurazione TOML | 1A | ✅ Fatto | Step 0 | — |
| 4 | Strategie di ingestion | 1A | ✅ Fatto | Step 3 | — |
| 5 | Strategie di chunking | 1A | ✅ Fatto | Step 3 | — |
| 6 | Embedding configurabile | 1A | ✅ Fatto | Step 3 | — |
| 6-bis | Astrazione LLM | 1A | 🟡 Parziale | Step 6 | Fallback identity + wiring in AppContext |
| 7 | KnowledgeBaseManager | 1A | ✅ Fatto | Step 4, 5, 6 | — |
| **8-ter** | **AppContext e bootstrap** | **1A** | **✅ Fatto** | **Step 7, 6-bis** | **—** |
| 8 | Pipeline retrieval | 1B | ✅ Fatto | Step 8-ter | — |
| 8-bis | Pipeline GraphRAG | 1C | ✅ Fatto | Step 8-ter | — |
| 9 | Dataset sintetico legale | 2 | ❌ Non iniziato | Step 8 | — |
| 10 | Profili di configurazione | 2 | ❌ Non iniziato | Step 3 | — |
| 11 | Test end-to-end | 2 | ❌ Non iniziato | Step 8, 9 | — |
| 12 | Logging su file | 2 | ❌ Non iniziato | Step 8-ter | — |
| 13 | CLI con Typer | 3 | ❌ Non iniziato | Step 8-ter, 12 | — |
| 14 | Server MCP | 3 | ❌ Non iniziato | Step 8-ter | — |
| 15 | Backend REST | 4 | ❌ Non iniziato | Step 13 | — |
| 16 | Frontend React | 4 | ❌ Non iniziato | Step 15 | — |
| 17 | Polish e documentazione | 4 | ❌ Non iniziato | Step 16 | — |
| 18 | Imballaggio (Docker + .exe) | 4 | ❌ Non iniziato | Step 15, 16 | — |

### Mappe di dipendenze

```
Fase 1A (ingestione vettoriale):
  Step 0 ──┬── Step 1
           ├── Step 2
           ├── Step 3 ──┬── Step 4
           │            ├── Step 5
           │            └── Step 6
           │
           └── Step 7 (orchestra 4+5+6)
                     │
Step 6-bis ──────────┤
                     ▼
              Step 8-ter (AppContext)  ← COLLO DI BOTTIGLIA
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
    Fase 1B      Fase 1C      Fase 2
    (retrieval)  (GraphRAG)   (test)
         │           │           │
         └───────────┼───────────┘
                     ▼
                 Fase 3 (CLI + MCP)
                     │
                     ▼
                 Fase 4 (REST + Frontend)
```

### Priorità imminente

1. **Step 9** — Dataset sintetico legale (in corso su agente parallelo)
2. **Step 6-bis residuali** — fallback identity, wiring (arrivano con implementazioni reali)
3. **Step 10** — Profili di configurazione
4. **Step 11** — Test end-to-end

---

## §1 — Architettura generale

### Monorepo con 3 pacchetti

```
knowledge_space/
├── packages/
│   ├── knowledge-base/     # libreria pura (no XDG, no CLI, no API)
│   │   ├── src/knowledge_base/
│   │   │   ├── models.py
│   │   │   ├── persistence.py
│   │   │   ├── workspace_manager.py
│   │   │   ├── domain_manager.py
│   │   │   ├── knowledge_base_manager.py
│   │   │   ├── base_config.py
│   │   │   └── strategies/
│   │   │       ├── ingestion.py
│   │   │       ├── chunking.py
│   │   │       ├── embedding.py
│   │   │       └── llm.py
│   │   └── tests/
│   ├── mcp-server/         # server MCP (dipende da knowledge-base)
│   └── knowledge-space/    # app layer (CLI, REST, bootstrap)
│       ├── src/knowledge_space/
│       │   ├── constants.py
│       │   └── runtime_paths.py
│       └── tests/
├── docs/                   # documentazione
└── pyproject.toml          # workspace uv
```

### Separazione delle responsabilità

| Pacchetto | Responsabilità | Dipende da |
|-----------|---------------|------------|
| `knowledge-base` | Modelli, persistenza, manager, strategy registry, pipeline retrieval/grafo | Nessun riferimento a XDG, CLI, API |
| `knowledge-space` | `RuntimePaths`, `AppContext`, CLI, REST API, bootstrap | `knowledge-base` |
| `mcp-server` | Server MCP (stdio/SSE) | `knowledge-base` |

### Pattern architetturali

- **Strategy/plugin pattern** per ingestion, chunking, embedding, retrieval, LLM
- **Registry** discoverable per ogni strategy (nome + parametri + metadati)
- **AppContext** come unico punto di dependency injection
- **Nessuna variabile globale** — tutto passato esplicitamente

---

## §2 — Fase 1A: Ingestione e indicizzazione vettoriale

**Obiettivo:** Pipeline completa: documento → ingestion → chunking → embedding → Chroma. Include sync filesystem, configurazione per-base, strategy registry, gestione incrementale dell'indice.

**Stato:** ✅ Completa (Step 0-8-ter fatti, Step 6-bis parziale)

---

### Step 0 — Modello di dominio e persistenza ✅

Modelli Pydantic + caricamento/salvaggio indice globale e configurazione workspace.

**Implementato:**
- `models.py`: `ChunkRef`, `FileEntry`, `KnowledgeBase`, `Domain`, `Workspace`, `GlobalIndexData`, `WorkspaceConfigData`
- `persistence.py`: `GlobalIndex`, `WorkspaceConfig` (path iniettabile, nessuna variabile globale)
- 16 test di roundtrip JSON

---

### Step 1 — Workspace e sync FS ✅

CRUD workspace + sincronizzazione col filesystem via watchdog.

**Implementato:**
- `WorkspaceManager`: `add`, `remove`, `list`, `load`, `sync`, `set_last_workspace`, `get_last_workspace`
- `WorkspaceWatcher` con observer iniettabile
- 8 test

---

### Step 2 — Domini ✅

Gestione domini (raggruppamento logico di basi).

**Implementato:**
- `DomainManager`: `create`, `delete`, `auto_generate`, `activate`, `deactivate`, `add_base`, `remove_base`
- 10 test

---

### Step 3 — Configurazione TOML ✅

Configurazione per-base con cascata di default e strategy registry.

**Implementato:**
- `BaseConfig` (Pydantic) con sezioni `ingestion`, `chunking`, `embedding`
- `BaseConfigLoader` con cascata: default hardcoded → `defaults.toml` → `base.toml`
- Validazione TOML (warning + fallback per valori non riconosciuti)
- Registry delle strategie per ingestion, chunking, embedding
- Blocco cambio config (model/method/library diverso + collection non vuota → errore)
- 28 test

**Cascata di configurazione:**
```
default hardcoded
  ↓ override
<workspace>/.knowledge-space/defaults.toml
  ↓ override
<base>/.knowledge-space/base.toml
```

**Trigger di reindex** (blocco cambio config):

| Trigger | Chiave config | Impatto |
|---------|--------------|---------|
| `model-change` | `embedding.model` | Re-embed, nuova collection |
| `chunking-change` | `chunking.method` | Re-chunk + re-embed |
| `ingestion-change` | `ingestion.library` | Re-ingest + tutto downstream |

---

### Step 4 — Strategie di ingestion ✅

Conversione file sorgente → Markdown.

**Implementato:**
- Interfaccia `IngestionStrategy` e registry
- Strategy `docling` (PDF, layout complesso, OCR opzionale)
- Strategy `pymupdf4llm` (PDF veloce, multi-colonna)
- Strategy `markitdown` (PPTX, MD, DOCX, HTML)
- Strategy `identity` (MD/TXT, copia diretta)
- Validazione estensioni (formato non supportato → errore)
- 30 test

---

### Step 5 — Strategie di chunking ✅

Suddivisione testo in chunk.

**Implementato:**
- Interfaccia `ChunkingStrategy` e registry con `params_schema` discoverable
- 5 strategy: `fixed_size`, `recursive`, `semantic`, `sentence`, `markdown`
- `fixed_size` con due comportamenti: no-overlap (`chunk_overlap=0`) e sliding window (`>0`)
- `semantic` richiede embedding (`requires_embedding=True`)
- 46 test

---

### Step 6 — Embedding configurabile ✅

Modello di embedding per-base con registry e metadati discoverable.

**Implementato:**
- Interfaccia `EmbeddingStrategy`, `EmbeddingMetadata` e registry
- 12 modelli (7 locali + 5 remoti: OpenAI, Cohere, Voyage)
- `LocalEmbedding` + provider remoti con import lazy
- `estimate_tokens` + `validate_chunk_context` con `ChunkTooLongError`
- 46 test unitari + 6 test integrazione opzionali

**Modelli supportati:**

| Modello | Lingue | Dim | Max ctx | API |
|---------|--------|-----|---------|-----|
| `all-mpnet-base-v2` | EN | 768 | 384 | No |
| `all-MiniLM-L6-v2` | EN | 384 | 384 | No |
| `gte-large-en-v1.5` | EN | 1024 | 8192 | No |
| `bge-large-en-v1.5` | EN | 1024 | 512 | No |
| `bge-m3` | 🌍 multilingua | 1024 | 8192 | No |
| `multilingual-e5-small` | 🌍 multilingua | 384 | 512 | No |
| `multilingual-e5-large` | 🌍 multilingua | 1024 | 512 | No |
| `text-embedding-3-small` | 🌍 multilingua | 1536 | 8191 | Sì |
| `text-embedding-3-large` | 🌍 multilingua | 3072 | 8191 | Sì |
| `embed-multilingual-v3.0` | 🌍 multilingua | 1024 | 512 | Sì |
| `voyage-3` | 🌍 multilingua | 1024 | 32000 | Sì |
| `voyage-3-lite` | 🌍 multilingua | 1024 | 32000 | Sì |

---

### Step 6-bis — Astrazione LLM 🟡

Interfaccia comune per tutti i modelli linguistici.

**Fatto:**
- `LLMMetadata` (Pydantic) e `LLMStrategy` (Protocol) con `generate()` e `stream()`
- Registry con modelli mock (`mock/echo`, `mock/fixed`) e abbreviazioni (`fast`, `quality`, `local`)
- Provider remoti e locali registrati (solo metadati, nessuna implementazione HTTP)
- `llm_factory` con caching in `knowledge_base/strategies/llm.py`
- 5 test (mock, factory, errore chiave API mancante)

**Mancano (arrivano con Step 8-ter e Fase 1B/1C):**
- Fallback `identity` con warning per stage con `requires_llm=True` ma senza modello
- Wiring della factory in `AppContext`
- Campo `model` nel `params_schema` del registry retrieval
- Implementazioni reali OpenAI/Ollama/Anthropic (Fase 1B/1C)

**Nessuna sezione `[llm]` globale:** ogni componente sceglie il proprio modello nel TOML (es. `stages[{method="multi_query", model="..."}]`, `reranker_model`, `hyde_model`, `extraction_model`).

**Chiavi API:** mai nei TOML. Env var o `UserSettings` (`~/.config/KnowledgeSpace/config.json`).

---

### Step 7 — KnowledgeBaseManager ✅

Logica operativa sulle basi: orchestrazione ingestion → chunking → embedding → Chroma.

**Implementato:**
- `KnowledgeBaseManager`: `add`, `remove`, `add_file`, `remove_file`, `sync`
- `file_id` (UUID4 stabile per rename), `chunk_id = base::file_id::i`
- Diff incrementale via `content_hash` (re-embed solo chunk cambiati)
- Move/rename senza recompute (metadata-only)
- Chunk su disco: `<base>/.knowledge-space/chunks/<file_id>/<file_id>_chunk_<i>.md`
- Metadata Chroma estesi: `chunk_id`, `base_name`, `file_name`, `file_id`, `chunk_index`, `content_hash`
- Migrazione retroattiva di `state.json` esistenti

---

### Step 8-ter — AppContext e bootstrap ✅

**Il collo di bottiglia del progetto.** Unico punto in cui le dipendenze vengono assemblate. CLI, MCP e REST ricevono un `AppContext` già pronto.

**Implementato:**

| Componente | Dove | Descrizione |
|-----------|------|-------------|
| `AppContext` | `knowledge_space/context.py` | Dataclass con tutti i manager e le factory |
| `build_app_context()` | `knowledge_space/bootstrap.py` | Entry point unico per costruire il contesto |
| Test | `packages/knowledge-space/tests/` | Costruzione con path temporanei, mocking factory |

**Campi di `AppContext`:**

```python
class AppContext:
    runtime_paths: RuntimePaths
    global_index: GlobalIndex
    workspace_manager: WorkspaceManager
    domain_manager: DomainManager
    base_manager_factory: Callable[[WorkspaceConfig, BaseConfig], KnowledgeBaseManager]
    embedder_factory: Callable[[str], EmbeddingStrategy]
    llm_factory: Callable[[str], LLMStrategy]
    graph_store_factory: Callable[[GraphConfigData], GraphStore] | None
    base_config_loader: BaseConfigLoader
```

**Vincoli:**
- Nessuna variabile globale
- `RuntimePaths` già esiste in `knowledge_space/runtime_paths.py` (da rivedere se va qui o nel contesto)
- `knowledge-base` non conosce XDG/APP_NAME — il wiring avviene solo in `knowledge-space`

**Nota:** `RuntimePaths` è mantenuto in `knowledge_space/runtime_paths.py` (non spostato in `context.py`). I file sono:
- `knowledge_space/context.py` — `AppContext` dataclass
- `knowledge_space/bootstrap.py` — `build_app_context()` entry point
- `tests/test_context.py` — 16 test (struttura, factory, wiring end-to-end)

---

## §3 — Fase 1B: Ricerca sui documenti processati

**Obiettivo:** Pipeline di retrieval su vettori Chroma (dense/sparse/hybrid) con pre-retrieval e post-retrieval.

**Stato:** ✅ Fatto

**Dipende da:** Step 8-ter (AppContext)

---

### Step 8 — Pipeline retrieval ✅

Pipeline a 3 step: pre-retrieval → retrieval → post-retrieval.

**Implementato:**
- `strategies/pre_retrieval.py`: 4 strategy (`identity`, `multi_query`, `step_back`, `least_to_most`)
- `strategies/retrieval.py`: 3 strategy (`dense`, `sparse`, `hybrid`) con fusione `rrf`/`weighted_sum`
- `strategies/post_retrieval.py`: 7 strategy (`identity`, `relevance`, `mmr`, `cross_encoder`, `llm`, `llm_chain_extract`, `selective_context`)
- `search_service.py`: `SearchService` con orchestrazione 3 step e fallback automatico LLM→identity
- `base_config.py`: sezioni `[pre_retrieval]`, `[retrieval]`, `[post_retrieval]` aggiunte a `BaseConfig`
- `strategies/__init__.py`: `RetrievalResult`, `PreRetrievalRegistry`, `RetrievalRegistry`, `PostRetrievalRegistry`
- 85 test

#### Pre-retrieval (espansione testuale)

| Strategy | Descrizione | Richiede LLM |
|----------|-------------|:---:|
| `identity` | No-op | No |
| `multi_query` | Genera N sotto-query con LLM | Sì |
| `step_back` | Genera domanda astratta con LLM | Sì |
| `least_to_most` | Decompone in sottoproblemi con LLM | Sì |

Stadi concatenati: ogni stadio riceve le query del precedente e produce varianti.

#### Retrieval (dense / sparse / hybrid)

| Strategy | Descrizione | Note |
|----------|-------------|------|
| `dense` | Similarity search su Chroma | Sempre disponibile |
| `sparse` | BM25-like | Fallback automatico a `rank_bm25` se modello non espone `embed_sparse` |
| `hybrid` | Ensemble dense + sparse | Fusione: `rrf` (default) o `weighted_sum` |

**Query mode:** `original` (embed_query) o `hyde` (documento ipotetico → embed_documents).

#### Post-retrieval (reranking / compression)

| Strategy | Tipo | Richiede modello |
|----------|------|:---:|
| `identity` | No-op | No |
| `relevance` | Rule-based | No |
| `mmr` | Rule-based | No (usa embedding chunk) |
| `cross_encoder` | Model-based | Sì (`reranker_model`) |
| `llm` | LLM-based | Sì (`reranker_model`) |
| `llm_chain_extract` | Compressor | Sì (`compressor_model`) |
| `selective_context` | Compressor | Sì (`compressor_model`) |

#### Orchestrazione

`SearchService` o metodo `search` su `KnowledgeBaseManager`: query + config + top_k → 3 step sequenziali.

Se un metodo richiede LLM ma non è configurato → fallback automatico a `identity` con warning.

---

## §4 — Fase 1C: GraphRAG

**Obiettivo:** Grafo Neo4j da chunk/embedding esistenti, propagazione incrementale, retrieval su grafo.

**Stato:** ✅ Fatto

**Dipende da:** Step 8-ter (AppContext), Step 7 (KnowledgeBaseManager)

**Implementato:**
- `graph/store.py`: `GraphStore` Protocol, `Neo4jGraphStore`, `MockGraphStore`, factory
- `graph/schema.py`: `GraphSchema`, `NodeSchema`, `EdgeSchema`, caricamento/salvataggio JSON
- `graph/extraction.py`: `EntityRelationExtractor`, `GraphExtractionResult`, parsing JSON robusto
- `graph/resolver.py`: `EntityResolver` Protocol, `ExactMatchResolver`, `SpaCySemanticMatchResolver` (fallback)
- `graph/writer.py`: `Neo4jWriter` con write_nodes, write_edges, delete, update_properties, indici
- `graph/chunk_loader.py`: `KSChunkLoader` per leggere chunk da disco + embedding da Chroma
- `graph/retriever.py`: 6 retriever (`vector`, `vector_cypher`, `hybrid`, `hybrid_cypher`, `text2cypher`, `tools`)
- `base_config.py`: sezione `[graph]` aggiunta a `BaseConfig`
- 82 test (3 skipped: Neo4j integration, SpaCy semantic)

### Prerequisiti (F0) — già fatti ✅

- Chunk in `<base>/.knowledge-space/chunks/<file_id>/<file_id>_chunk_<i>.md`
- `file_id` (UUID stabile), `chunk_id = base::file_id::i`
- Metadata Chroma completi
- Diff incrementale vettoriale funzionante
- Move/rename vettoriale funzionante
- Blocco cambio config vettoriale funzionante

### Pipeline GraphRAG

```
KSChunkLoader → Schema → LLMEntityRelationExtractor → Neo4jWriter → EntityResolver
```

**KSChunkLoader** (custom): legge chunk da disco + embedding da Chroma, produce `TextChunks` ordinati.

**Schema del grafo:** caricato da `graph/schema.json` se esiste; estratto/costruito solo la prima volta.

**Entity resolution:** `SpaCySemanticMatchResolver` (default), fallback a `exact` se extra `[nlp]` mancante.

### Propagazione al grafo (5 trigger)

| Trigger | Propagazione |
|---------|-------------|
| 1 — content change | Eager: re-estrazione LLM mirata su chunk cambiati |
| 2 — move/rename | Property-only: update `file_name`/`path` su Neo4j |
| 3 — cambio modello | Property-only: update `embedding` su nodi Chunk |
| 4 — cambio chunking | Full: delete + re-estrazione LLM |
| 5 — cambio ingestion | Full: come trigger 4 |

### Retrieval su grafo

Configurabile via `[graph].retriever` per-base:

| Valore | Classe | LLM | Note |
|--------|--------|:---:|------|
| `vector` | VectorRetriever | No | Similarità pura |
| `vector_cypher` | VectorCypherRetriever | No | Vector + traversal |
| `hybrid` | HybridRetriever | No | Vector + BM25 |
| `hybrid_cypher` | HybridCypherRetriever | No | **Default** |
| `text2cypher` | Text2CypherRetriever | Sì | LLM → Cypher |
| `tools` | ToolsRetriever | Sì | LLM seleziona tool |

---

## §5 — Fase 2: Testing e validazione

**Obiettivo:** Validare end-to-end la pipeline con dataset sintetici e profili predefiniti.

**Stato:** ❌ Non iniziato

**Dipende da:** Step 8 (retrieval), Step 8-ter (AppContext)

---

### Step 9 — Dataset sintetico legale ❌

Dataset focalizzato su diritto svizzero/UE, documenti in IT/EN.

| # | Documento | Formato | Lingua |
|---|-----------|---------|--------|
| 1 | Costituzione svizzera (estratti) | PDF, TXT | IT |
| 2 | Bundesverfassung (stessi articoli) | PDF | DE |
| 3 | Swiss Code of Obligations (art. 319-362) | PDF, TXT | EN |
| 4 | GDPR (art. 1-49) | PDF, TXT, DOCX | IT, EN |
| 5 | Sentenza fittizia TF | MD | IT |
| 6 | Contratto lavoro fittizio | DOCX | IT |
| 7 | EU AI Act (Titoli I-IV) | PDF, TXT | EN |

**Query golden:** 2-4 per documento con risposta attesa (fattuale, definizione, cross-document).

**Script da creare:** `fetch.py`, `extract.py`, `generate.py`, `validate.py` in `tests/data/synthetic/legal/`.

---

### Step 10 — Profili predefiniti ❌

Configurazioni TOML per 3 scenari d'uso:

| | `ricercatore` | `consulente` | `studente` |
|---|---|---|---|
| Ingestion | `docling` | `pymupdf4llm` | `markitdown` |
| Chunking | `recursive` ~1200/200 | `markdown` | `recursive` ~800/150 |
| Embedding | `gte-large-en-v1.5` | `bge-m3` | `multilingual-e5-small` |
| Pre-retrieval | `multi_query` o `hyde` | `identity` | `identity` |
| Retrieval | `hybrid` | `dense` | `dense` |
| Post-retrieval | `llm_chain_extract` | `identity` | `identity` |
| GraphRAG | `hybrid_cypher` | `vector_cypher` | `vector` |

---

### Step 11 — Test end-to-end ❌

Pipeline completa (ingest → chunk → embed → retrieve) sul dataset legale per ciascun profilo. Verifica recall ≥ soglia sui query golden.

---

### Step 12 — Logging su file ❌

`setup_logging()` in `knowledge_space/logging.py`:
- File handler: `RotatingFileHandler` su `<state_home>/logs/ks.log` (5 MB × 3 backup)
- Console handler: INFO di default, DEBUG con `--verbose`
- `KS_LOG_LEVEL` env var con precedenza
- Uncaught exception hook
- Silenzio librerie verbose (chromadb, sentence_transformers, urllib3)

---

## §6 — Fase 3: MCP + CLI

**Obiettivo:** Esporre i manager tramite CLI e server MCP.

**Stato:** ❌ Non iniziato

**Dipende da:** Step 8-ter, Step 12

---

### Step 13 — CLI con Typer ❌

Comandi: `workspace`, `domain`, `base`, `file`, `chunk`, `tree`, `search`, `reindex`, `graph`, `config`, `auth`, `models`, `profiles`, `status`.

**Modalità standalone** (Fase 1-3): ogni comando è un processo separato, crea `AppContext` temporaneo, opera su `state.json`/Chroma, termina.

**Scrittura TOML** (`config set`/`unset`): rileva automaticamente trigger di reindex e chiede conferma.

**Profili** (`profiles list`/`show`/`apply`/`save`/`diff`/`edit`/`remove`): gestisce profili in `~/.config/knowledge-space/profiles/`.

**Autocompletamento:** shell completion per tutti i comandi, in particolare `config set`/`unset` su key e value.

---

### Step 14 — Server MCP ❌

Server MCP con trasporto stdio (default) e SSE (opzionale). In Fase 3 opera come processo standalone; in Fase 4+ diventa bridge verso il backend REST.

---

## §7 — Fase 4: REST + Frontend

**Obiettivo:** Backend REST + frontend React.

**Stato:** ❌ Non iniziato

**Dipende da:** Step 13 (CLI)

---

### Step 15 — Backend REST ❌

Thin layer FastAPI sopra i manager. Router: `health`, `workspaces`, `domains`, `bases`, `files`, `search`, `config`, `models`.

---

### Step 16 — Frontend React ❌

- Visualizzazione struttura ad albero (workspace → domini → basi → file → chunk)
- Modifica TOML dall'interfaccia
- Selettore modello embedding con badge lingue (🇮🇹 IT, 🇬🇧 EN, 🌍 multilingua)
- Avviso contesto (max_context_tokens vs chunk_size)

---

### Step 17 — Polish e documentazione ❌

- Rimuovere codice legacy
- Aggiornare README, AGENTS.md
- Valutare versione Python minima (`>=3.14` vs `>=3.12`)

---

### Step 18 — Imballaggio ❌

**Provvisorio — scelte da definire.**

| Opzione | Pro | Contro |
|---------|-----|--------|
| Docker (`python:3.12-slim`) | Riproducibile | Nessuna GPU |
| PyInstaller (.exe) | Maturato | Antivirus false positive |
| Nuitka | Compilato in C | Build lenta |

---

## §8 — Scelte consolidate

### Persistenza

| Aspetto | Scelta |
|---------|--------|
| Formato stato | JSON (`state.json` per workspace) |
| Formato config | TOML (human-friendly, con commenti) |
| Vector store | Chroma (collection per base) |
| Grafo | Neo4j (uno per workspace) |
| Chunk su disco | Prodotto derivato, non editabile |

### Identificatori

| Aspetto | Scelta |
|---------|--------|
| `file_id` | UUID4 stabile per la vita del file |
| `chunk_id` | `base::file_id::i` (disaccoppiato dal nome) |
| Chroma IDs | Deterministici (no `uuid4()`) |

### Configurazione

| Aspetto | Scelta |
|---------|--------|
| Cascata | hardcoded → `defaults.toml` → `base.toml` |
| Strategy pattern | Registry per ingestion, chunking, embedding, retrieval, LLM |
| Cambio config | Bloccato se collection non vuota |
| Secrets | Mai nei TOML — env var o `UserSettings` |

### Modelli

| Aspetto | Scelta |
|---------|--------|
| Dominio | Pydantic (`Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef`) |
| Logica operativa | Classi manager/service separate dai modelli |
| Iniezione dipendenze | `AppContext` a livello di applicazione |

---

## §9 — Rischi e considerazioni trasversali

### Concurrency

- `state.json` e indice globale non sono concurrent-safe. Se REST gira con più worker, serve sincronizzazione.
- Chroma PersistentClient: safe per singolo processo, conflitti con più processi.
- Watchdog usa thread: per i test, permettere observer fittizio iniettabile.

### Sicurezza

- Non esporre `hf_key` o altri secrets via API.
- Validare path dagli utenti (path traversal).
- Se backend esposto in rete: autenticazione.

### Compatibilità Python

- `requires-python = ">=3.14"` è restrittivo. Valutare `>=3.12`.

### Esecuzione simultanea REST e MCP

- CLI può esporre `serve` e `mcp` come comandi separati.
- Futuro: MCP in modalità SSE sullo stesso server FastAPI.

### LLM e modelli

- `EmbeddingStrategy` per-base può richiedere modelli diversi in RAM: valutare lazy loading.
- Ogni componente LLM sceglie il proprio modello nel TOML (nessuna sezione globale).

### Benchmark

- Il benchmark comparativo tra profili è fuori scope per la tesi. La validazione si limita a test end-to-end (recall ≥ soglia).

---

*Questo documento sostituisce: 90-roadmap-overview.md, 91a/b/c-roadmap-fase1-*.md, 92-roadmap-fase2.md, 93-roadmap-fase3.md, 94-roadmap-fase4.md.*
