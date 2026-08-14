# Refactor 001 — Componente grafo: semplificazione KISS (piano unico)

**Autore piano:** agente master · **Tipo:** refactor · **Stato:** in stesura (bozza) · **Priorità:** alta

## Obiettivo

Ridurre il componente grafo (`packages/knowledge-base/src/knowledge_base/graph/`, ~2100 righe) all'osso e completare l'integrazione: meno configurazione, meno modalità, meno file. Assorbe e sostituisce le spec feat-016 (GraphManager), feat-017 (CLI), feat-018 (watcher), feat-019 (MCP), feat-020 (ricerca attiva).

**Invarianti (non negoziabili):**
1. **1 grafo per workspace** (mai per-base): chunk di tutte le basi nello stesso Neo4j; `base_name` è proprietà dei nodi Chunk.
2. **La ricerca sul grafo rispetta domini/basi/file/chunk ATTIVI come la ricerca vettoriale**: pre-retrieval `active_base_names` via `is_base_searchable`; post-retrieval `filter_active_chunks` (stessi chunk_id); entità = raggiungibilità dai chunk attivi (nessun filtro su base_name delle entità).

## Componenti (decisioni)

### 1. Loader (`chunk_loader.py`) — **cambia solo la fonte degli embedding**

Legge il testo dei chunk da disco (``<base>/.knowledge-space/chunks/``) — invariato. **Embedding: due fonti, secondo il modello della base rispetto a ``[graph] embedding_model`` (vedi 7-bis):**

- base con stesso modello → embedding riciclati da Chroma (come oggi);
- base con modello diverso → embedding **ricalcolati** dal testo col modello del grafo (serve l'embedder del grafo iniettato nel loader).

`upsert_chunks` (propagazione incrementale) resta, ma nel caso mismatch ricalcola anche gli embedding dei chunk cambiati.

### 2. Schema (`schema.py`) — **eliminato come input, diventa output**

Nessuno schema persistente (niente `schema.json`, niente modalità FREE/manuale/EXTRACTED/da-file). Grafo schema-less; a richiesta lo si deriva dal DB (ispezione/doc): `CALL db.labels()`, `db.relationshipTypes()`, `db.schema.nodeTypeProperties()` → sempre allineato al corpus (le entità nuove compaiono da sole). Estrazione guidata dal prompt, non dallo schema.

### 3. Estrazione (`extraction.py`) — **semplificata, niente pipeline neo4j-graphrag**

`neo4j-graphrag` si usa SOLO per i retriever (driver `neo4j` per la connessione). La costruzione è codice nostro: `KSChunkLoader` → `EntityRelationExtractor` → `Neo4jWriter` → resolver (~100 righe di orchestrazione, già scritte). Motivo: la pipeline presume file grezzi (data loading, split, embed) — noi abbiamo già chunk+embedding; e la propagazione incrementale non calza con le sue run batch.

| Prima | Dopo |
|---|---|
| Label libere (Person, Organization...) | Label fisse: nodi `Entity {name, label}` — semantica nella proprietà `label` (es. `"Persona"`) |
| Tipi relazione liberi | Relazioni sempre `RELATED_TO` con proprietà `type` |
| Id locali transitori (n1, n2) | Riferimenti **per name**: `{nodes: [{name, label}], edges: [{source, target, type}]}` |
| `system_prompt` configurabile | Un solo prompt, fisso nel codice |
| `extract_batch` con merge interno | Per-chunk; aggregazione nel GraphManager |
| JSON invalido → vuoto silenzioso | invariato (warning + skip) |

### 4. Writer (`writer.py`) — **da 10 a 8 metodi**

**Eliminare:** `write_nodes_multi_label` (inutile con label fissa), `update_properties` (generico senza chiamanti). **Tenere:** `write_nodes`, `write_edges`, `delete_chunks`, `delete_file_nodes`, `update_chunk_file_name`, `update_chunk_embeddings`, `create_vector_index`, `create_fulltext_index`. Il writer scrive anche `(c:Chunk)-[:MENTIONS]->(e:Entity)` per ogni entità estratta dal chunk (relazione strutturale, distinta da `RELATED_TO`).

**Propagazione: i 5 trigger della doc restano** (content change eager/lazy, move/rename property-only, cambio modello property-only, cambio chunking full, cambio ingestion full) + blocco cambio config (già implementato in `base_config.py`, invariato).

### 5. Resolver (`resolver.py`) — **1 resolver, niente spaCy**

**Eliminare:** `SpaCySemanticMatchResolver` (spacy + modello ~40MB, 150 righe, beneficio dubbio), `_NoOpResolver`, `resolver_factory` a 3 vie (via config `resolver=`). Il `FuzzyMatchResolver` della doc non è mai esistito — non implementarlo. **Tenere:** `ExactMatchResolver` su coppia `(name_normalizzato, label_dominio)`; gli id locali sono spariti → dedup vera nel prompt (nomi normalizzati), resolver come rete di sicurezza.

### 6. Retriever (`retriever.py`) — **1 solo retriever**

**Tenere:** `HybridCypherRetriever` (vector + fulltext + traversal `[:MENTIONS]`, con `retrieval_query` di default invariato) + filtro `active_base_names` (param `search(query, *, top_k=5, active_base_names=None)`, `None` = nessun filtro, compatibilità test). **Eliminare:** `VectorRetriever`, `VectorCypherRetriever`, `HybridRetriever`, `Text2CypherRetriever`, `ToolsRetriever` (mai implementato), `RetrieverFactory`, config `[graph].retriever` (istanziazione diretta nel GraphManager). Restano i 2 indici (li usa l'hybrid).

### Configurazione residua `[graph]` (TOML, cascata per-base)

```toml
[graph]
enabled = false               # interruttore (defaults.toml workspace; base.toml può escludere una base)
on_chunk_change = "lazy"      # "eager" | "lazy" — propagazione trigger 1
top_k = 5                     # default risultati graph search
extraction_model = None       # LLM per l'estrazione entità, via llm_factory (es. "lm-studio/auto"); None → no-op con warning
embedding_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # multilingua it+en, 118MB — stesso default delle basi (riciclo embedding sempre attivo)
```

**Via dalla config:** `retriever`, `schema_mode`, `resolver`, `schema_model`, `vector_index`, `fulltext_index`, `retrieval_query`, `return_properties`, `chunk_embedding_property`, `params` (costanti nel codice o non più esistenti). **Non nel TOML:** connessione Neo4j (`graph.json` o env `NEO4J_URI`/`NEO4J_AUTH`), nomi indici (costanti, creati una volta per workspace).

**LLM pattern (doc 75-llm.md):** nessuna sezione `[llm]` globale — ogni componente sceglie il proprio modello nel TOML e lo costruisce via `llm_factory(model)` (bootstrap). `extraction_model` segue questo pattern: `lm-studio/auto` (locale) o `openai-compatible/<path-modello>` (remoto, es. `openai-compatible/openrouter/auto-beta`; chiavi in env var).

## Orchestrazione (nuovo codice)

### 7. GraphManager — `packages/knowledge-base/src/knowledge_base/graph_manager.py` (da feat-016, riallineato)

- `__init__(workspace, config_loader, graph_store_factory, llm_factory)` — store da `GraphConfigData` (`bolt_uri`, `database`) in `<workspace>/.knowledge-space/graph/graph.json` o env `NEO4J_URI`/`NEO4J_AUTH`; salvato al primo build.
- `build_graph()` — full build per base attiva: `KSChunkLoader` → estrazione (LLM) → `write_nodes`/`write_edges`/`MENTIONS` (MERGE idempotente) → resolver. Nessuno schema coinvolto.
- `sync_base(base_name)` — ri-estrazione solo chunk nuovi/modificati (via `content_hash`), idempotente.
- `remove_base(base_name)` — `delete_file_nodes` per ogni file.
- Se `graph.enabled == false` o nessun LLM → no-op con warning (l'estrazione entità richiede LLM).
- `bootstrap.py`: cablare `graph_store_factory` in AppContext.

### 7-bis. Embedding del grafo (opzione 2: ricalcolo su mismatch)

**Un solo modello embedding per workspace**, multilingua (it+en) e leggero: default `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (118MB, 384 dim — configurabile in `[graph] embedding_model`). È lo **stesso default delle basi** (`[embedding] model`): nel caso comune il riciclo da Chroma non scatta mai e serve un solo download. Motivo: un unico spazio vettoriale per l'indice `chunk-embeddings` e per l'embedder della query del retriever.

- `KSChunkLoader` riceve l'embedder del grafo e il modello atteso.
- Base con `embedding_model` == modello del grafo → **riciclo** embedding da Chroma (zero ricalcolo).
- Base con modello diverso → **ricalcolo** embedding col modello del grafo durante build/sync (opzione 2: nessuna base esclusa). Il ricalcolo è una tantum per chunk; Chroma non viene toccato (il grafo ha i propri embedding sui nodi `:Chunk`).
- Retriever: embedder della query = sempre il modello del grafo.
- Trigger 3 (cambio modello del grafo) → `update_chunk_embeddings` property-only sui chunk già nel grafo; i chunk ricalcolati alla prossima sync.

### 8. CLI `ks graph` — `src/knowledge_space/cli/graph.py` (da feat-017, riallineato)

- `graph init [-w]` — `build_graph()`.
- `graph sync [-w] [--base <name>]` — `sync_base()` per base o tutte.
- `graph status [-w]` — connessione Neo4j, basi, chunk, entità/relazioni (COUNT).
- `graph schema [-w]` — derivazione dal DB (labels/relationshipTypes/properties) — sostituisce `re-extract-schema` (schema non più persistente).
- `graph search [-w] QUERY` — ricerca con filtro attivi (GraphSearchService).
- Gating: `graph.enabled == false` → `"Grafo disabilitato: ks config set graph.enabled true"`. Errore connessione → `verify_connectivity` con messaggio chiaro.
- Registrare il gruppo in `cli/__init__.py`; allineare `docs/85-cli.md`.

### 9. Propagazione watcher (da feat-018)

Hook in `workspace_manager.sync_and_ingest()`: se `graph.enabled` per la base → content change → `sync_base` (eager: ri-estrazione mirata / lazy: solo Chroma); base rimossa → `remove_base`; move/rename → `update_chunk_file_name` property-only. Gating: check veloce, errori non fatali (Neo4j giù → WARNING, riallineamento al prossimo sync).

### 10. Ricerca su grafo — `packages/knowledge-base/src/knowledge_base/graph_search_service.py` (da feat-020)

`GraphSearchService.search(workspace, query, top_k)`: `active_base_names` via `is_base_searchable` → retriever (hybrid_cypher) → `filter_active_chunks`. Usato da CLI `graph search` e MCP `graph_search`.

### 11. Tool MCP (da feat-019)

In `packages/mcp-server/src/mcp_server/server.py`: `graph_status(workspace)`, `graph_search(workspace, query, base=None, top_k=5)` (GraphSearchService), `graph_sync(workspace, base=None)`. Gating `graph.enabled`; dipendenze `neo4j` lazy.

## File da toccare (riepilogo)

| File | Modifica |
|------|----------|
| `graph/schema.py` | Ridurre a helper di derivazione dal DB (o rimuovere) |
| `graph/extraction.py` | Prompt a label fisse, riferimenti per name, rimozione id locali |
| `graph/writer.py` | Rimuovere `write_nodes_multi_label`, `update_properties`; aggiungere `MENTIONS` |
| `graph/resolver.py` | Solo `ExactMatchResolver`; via spaCy, noop, factory |
| `graph/retriever.py` | Solo `HybridCypherRetriever` + `active_base_names`; via factory e altri 5 |
| `graph/chunk_loader.py` | Embedder del grafo: riciclo da Chroma se stesso modello, ricalcolo se diverso |
| `graph/store.py` | Query derivazione schema (labels/relationshipTypes/properties) |
| `graph_manager.py` | **Nuovo**: GraphManager |
| `graph_search_service.py` | **Nuovo**: ricerca con filtro attivi |
| `src/knowledge_space/cli/graph.py` | **Nuovo**: 5 comandi |
| `src/knowledge_space/cli/__init__.py` | Registrare gruppo graph |
| `src/knowledge_space/bootstrap.py` | Cablare `graph_store_factory` |
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | Hook post-ingest (trigger 1/2/delete) |
| `packages/mcp-server/src/mcp_server/server.py` | 3 tool graph |
| `docs/40-graph.md`, `docs/85-cli.md` | Riscrivere: niente pipeline in costruzione, schema derivato, comandi reali |

## Verifica

```bash
ks config set graph.enabled true
ks graph init -w ~/ws2                    # → "Grafo costruito: N entità, M relazioni"
ks graph status -w ~/ws2                  # → Neo4j connesso, basi, chunk, entità
ks graph schema -w ~/ws2                  # → labels/relazioni derivati dal DB
ks graph search -w ~/ws2 "ciao"           # rispetta domini/basi/file attivi
cp nuovo.pdf ~/ws2/Base/; sleep 8         # watcher → sync_base (eager)
ks graph status -w ~/ws2                  # → conteggi aumentati
ks domain deactivate "Paper Accademici"; ks graph search -w ~/ws2 "x"
# → 0 risultati dal dominio inattivo; riattiva → tornano
```
