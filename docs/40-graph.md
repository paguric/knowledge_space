# Pipeline GraphRAG da chunk/embeddings esistenti

> **Stato:** non iniziato | **Step:** 8-bis | **Fase:** 1C | **Aggiornato:** 22 luglio 2026

## Panoramica

Costruzione del grafo della conoscenza su Neo4j riprendendo la pipeline `neo4j-graphrag` dal **Lexical Graph Builder**, senza rifare data loading, splitting ed embedding (già calcolati in KS). Un grafo per workspace, propagazione incrementale su cambiamenti (content change, move/rename, cambio modello/strategia), retrieval configurabile per-base.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Grafo Neo4j | Uno per workspace |
| Resume da | Lexical graph + estrazione entità + risoluzione |
| Schema | Caricato da `schema.json` se esiste; estratto solo la prima volta |
| Resolver default | `SpaCySemanticMatchResolver` (semantic), fallback exact |
| Propagazione content change | `eager` (default) o `lazy` |
| Propagazione move/rename | Property-only (no re-estrazione) |
| Propagazione cambio modello | Property-only: update embedding su nodi Chunk |
| Propagazione cambio chunking/ingestion | Full re-estrazione LLM |
| Retrieval | Configurabile per-base: `vector`, `vector_cypher`, `hybrid`, `hybrid_cypher`, `text2cypher`, `tools` |

## Dettagli

### Layout filesystem

Path rilevanti per GraphRAG (layout completo in [30-configuration.md](30-configuration.md)):

- **Chunk su disco**: `<base>/.knowledge-space/chunks/<file_id>/<file_id>_chunk_<i>.md` — prodotto derivato, non editabile.
- **Schema del grafo**: `<workspace>/.knowledge-space/graph/schema.json`
- **Stato del grafo**: `<workspace>/.knowledge-space/graph/graph.json`

La **configurazione del comportamento** (schema, `on_chunk_change`, `resolver`) è in `[graph]` del `BaseConfig` per-base.

### Modello dati (estensioni)

Vedi [20-data-model.md](20-data-model.md). Riassunto:

- `ChunkRef`: aggiunge `chunk_id` (deterministico `base::file_id::i`), `content_hash` (sha1). Campi `edited`/`edited_mtime` rimossi.
- `FileEntry`: aggiunge `file_id` (UUID4 stabile).
- `KnowledgeBase`: aggiunge `embedding_model`, `chunking_method`, `ingestion_library` (per blocco cambio config).
- `GraphConfigData`: `bolt_uri`, `database`, `schema_ref`, `embedding_model`, `retriever` (default workspace).
- Metadata Chroma: `source`, `chunk_index`, `base_name`, `file_name`, `file_id`, `file_mtime`, `content_hash`.

### Pipeline di resume

Assembla un `neo4j_graphrag.experimental.pipeline.Pipeline`:

1. **`KSChunkLoader`** (custom, §4) — produce `TextChunks` con embedding da Chroma + `DocumentInfo`.
2. **Schema** (§6-bis): se `schema.json` esiste → `GraphSchema.from_file`; altrimenti manuale/EXTRACTED/FREE + `save(...)`.
3. **`LLMEntityRelationExtractor(llm=..., create_lexical_graph=True)`** — crea il lexical graph autonomamente (NO `LexicalGraphBuilder` separato, §6).
4. **`Neo4jWriter(driver, neo4j_database=...)`** — `MERGE` idempotente su `__entity__tmp_internal_id` e chunk id.
5. **Entity resolver** (§7): `SpaCySemanticMatchResolver` (default) con `filter_query = "WHERE NOT entity:Resolved"`.

```python
await pipeline.run_async(file_path=..., document_metadata={"base_name":..., "file_mtime":...})
```

### `KSChunkLoader` (§4)

Sostituisce data loader + text splitter + chunk embedder. Legge chunk da disco, recupera embedding da Chroma, propaga `chunk_id` deterministico. Salta chunk/file/basi inattivi.

Espone `upsert_chunks(base, file_id, changed_chunks)` per propagazione incrementale:
1. Ricalcola embedding solo per i chunk cambiati.
2. `collection.upsert(...)` preservando metadata esistenti.
3. Ricalcola `content_hash`.

### Propagazione al grafo (§5)

**Eager cascade** su content change (trigger 1):

1. `KnowledgeBaseManager` re-ingest + re-chunk + `KSChunkLoader.upsert_chunks` → Chroma aggiornato.
2. Cascade `on_chunk_change = "eager"`: pipeline §3 solo sui chunk cambiati, `filter_query` mirato.
3. Marcatore `:Resolved` sulle entità nuove/mergeate.

**Lazy**: solo Chroma update; grafo si riallinea al prossimo `ks graph sync`.

| Trigger | Propagazione al grafo |
|---|---|
| 1 — content change | eager: re-estrazione LLM mirata |
| 2 — move/rename | property-only: update `file_name`/`path` |
| 3 — cambio modello | property-only: update `embedding` |
| 4 — cambio chunking | full: delete + re-inserimento completo |
| 5 — cambio ingestion | full: come trigger 4 |

### Evitare il lexical graph due volte (§6)

`LLMEntityRelationExtractor` con `create_lexical_graph=True` crea autonomamente nodi Document/Chunk e relazioni. **Non eseguire** `LexicalGraphBuilder` separato prima dell'estrattore.

### Schema del grafo (§6-bis)

| Stato file | `[graph].schema` | Azione |
|---|---|---|
| Esiste | qualsiasi | `GraphSchema.from_file(...)` — no LLM |
| Mancante | `"manuale"` | `SchemaBuilder` dal TOML + `save(...)` |
| Mancante | `"EXTRACTED"` | `SchemaFromTextExtractor` (una tantum) + `save(...)` |
| Mancante | `"FREE"` | niente schema, niente file |

Forzare re-estrazione: `ks graph re-extract-schema <workspace>`.

### Entity resolution (§7)

| Resolver | Tecnica | Extra | Quando |
|---|---|---|---|
| `SpaCySemanticMatchResolver` | embeddings spaCy + cosine | `[nlp]` | **Default**: buon compromesso |
| `FuzzyMatchResolver` | Levenshtein (RapidFuzz) | `[fuzzy-matching]` | Match ortografico, typo |
| `SinglePropertyExactMatchResolver` | match esatto `name` + `label` | nessuno | Più veloce, conservativo |

Configurazione via `[graph].resolver`:

```toml
[graph]
resolver = "semantic"   # default
# resolver = "exact"    # no extra
# resolver = "fuzzy"    # extra [fuzzy-matching]
# resolver = "none"     # no resolution
```

Fallback automatico a `exact` se extra `[nlp]` non installato (con warning).

### Grafo Neo4j uno per workspace (§8)

- Un solo DB Neo4j per workspace.
- `graph.json` registra `bolt_uri`, `database`, `schema_ref`, `embedding_model`.
- Ogni entità/chunk ha `base_name` come property.
- `[graph]` nel `BaseConfig` per-base gestisce: schema, resolver, `on_chunk_change`, `chunk_embedding_property`. Parametri di connessione a livello workspace.

### Blocco cambio config (§9)

Al caricamento di `BaseConfig`, KS confronta i valori configurati con quelli in `state.json`. Se differiscono **e** collection non vuota → errore:

```
ks reindex <base> --model-change       # trigger 3
ks reindex <base> --chunking-change    # trigger 4
ks reindex <base> --ingestion-change   # trigger 5
```

### Retrieval: metodo configurabile (§14)

La pipeline separa **costruzione** del grafo dalla **ricerca**. L'app istanzia il retriever specificato in `[graph].retriever` per-base (fallback: `GraphConfigData.retriever` workspace-level, default `"hybrid_cypher"`).

| Valore TOML | Classe neo4j-graphrag | Vector idx | Full-text idx | LLM | Note |
|---|---|:---:|:---:|:---:|---|
| `vector` | `VectorRetriever` | sì | no | no | Similarità pura ANN |
| `vector_cypher` | `VectorCypherRetriever` | sì | no | no | Vector + traversal Cypher |
| `hybrid` | `HybridRetriever` | sì | sì | no | Vector + BM25 |
| `hybrid_cypher` | `HybridCypherRetriever` | sì | sì | no | **Default**. Hybrid + retrieval_query |
| `text2cypher` | `Text2CypherRetriever` | no | no | sì | LLM → Cypher, richiede `schema.json` |
| `tools` | `ToolsRetriever` | dipende | dipende | sì | LLM seleziona tool |

**Parametri in `[graph]` (TOML per-base):**

| Campo | Default | Usato da |
|---|---|---|
| `retriever` | `"hybrid_cypher"` | tutti |
| `top_k` | `5` | vettoriali/hybrid |
| `vector_index` | `"chunk-embeddings"` | `vector*`/`hybrid*` |
| `fulltext_index` | `"chunk-text"` | `hybrid*` |
| `retrieval_query` | vedi defaults.toml | `*_cypher` |
| `return_properties` | `["chunk_id", "text"]` | `vector` |

**Factory:** `RetrieverFactory.build(base_config, graph_config, driver, embedder, llm)`.

**Indici Neo4j:** vector index (`create_vector_index`) + full-text index (`create_fulltext_index`) per retriever `hybrid*`. Creazione una tantum per workspace (idempotente).

### Fasi di implementazione

- **F0** — Prerequisiti: chunk in `<base>/.knowledge-space/chunks/<file_id>/`, `file_id` UUID, metadata Chroma completi, watcher ignora `.knowledge-space/`.
- **F1** — Pacchetto e dipendenze: `neo4j-graphrag` + `neo4j` + extra `[nlp]`, modulo `knowledge_base/graph/`, `graph.json`.
- **F2** — `KSChunkLoader`: implementazione + `upsert_chunks`.
- **F3** — Pipeline GraphRAG: assemblaggio, schema, `Neo4jWriter` idempotente, runner.
- **F4** — Entity resolution: `SpaCySemanticMatchResolver`, marcatore `:Resolved`, fallback automatico.
- **F5** — Propagazione al grafo: eager/lazy, delete file, move/rename.
- **F6** — Blocco cambio config.
- **F7** — Test di integrazione.
- **F8** — Documentazione.

### Rischi e limiti noti

- Resolver semantico non è magico: near miss teorici possibili.
- Re-estrazione su content change costa una chiamata LLM per chunk cambiato (mitigato da `content_hash`).
- Race conditions watcher: Chroma safe per singolo processo; per più processi serve sincronizzazione.
- Neo4j non embedded: serve istanza in esecuzione.
- Re-estrazione schema non migra entità vecchie.

### Test

| Test | Cosa verifica |
|------|---------------|
| Unit `KSChunkLoader` | TextChunks ordinate, embedding coerenti |
| Unit `upsert_chunks` | Chunks cambiati → upsert, content_hash aggiornato |
| Integrazione Neo4j | End-to-end, idempotenza, dedup resolver |
| Eager cascade | Content change → entità ri-estratte solo sui chunk cambiati |
| Blocco config | Cambio model/method/library → errore atteso |
| Fallback resolver | `[nlp]` mancante → warning + fallback a exact |
| Schema reload | Secondo run con `schema.json` → no LLM |
| Move/rename | `chunk_id` immutato, property aggiornate |

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 7 (KnowledgeBaseManager), Step 6-bis (LLMStrategy) | Step 13 (CLI `ks graph`), Step 15 (REST query GraphRAG) |
