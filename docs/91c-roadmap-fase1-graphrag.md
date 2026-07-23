# Fase 1C — Indicizzazione e retrieval su grafo (GraphRAG)

Costruire il grafo della conoscenza su Neo4j **riprendendo** la pipeline `neo4j-graphrag` a partire dal lexical graph, senza rifare ingestion/chunking/embedding (già calcolati in Fase 1A). Supportare la propagazione incrementale al grafo su cambiamenti (content change, move/rename, cambio config) e la ricerca su grafo via retriever Neo4j configurabili.

Al termine di questa sottofase `knowledge-base` sa:
- Leggere chunk da disco e embedding da Chroma via `KSChunkLoader`
- Costruire lo schema del grafo (manuale, EXTRACTED, FREE)
- Estrarre entità e relazioni via LLM e scriverle su Neo4j (idempotente via MERGE)
- Risolvere entità duplicate (semantico spaCy, fuzzy, exact)
- Propagare al grafo cambiamenti vettoriali: content change (eager/lazy), move/rename (property-only), cambio modello/chunking/ingestion (full re-index)
- Cercare su grafo via retriever configurabili (vector, vector_cypher, hybrid, hybrid_cypher, text2cypher, tools)

> Per la collocazione di questa sottofase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md). Per la specifica della pipeline GraphRAG: [40-graph.md](40-graph.md). Per la specifica della propagazione incrementale al grafo: [45-indexing-incrementale.md](45-indexing-incrementale.md). **Prerequisito**: Fase 1A completata (Chroma, `file_id`, `content_hash`, diff incrementale vettoriale).

---

### Step 8-bis: Pipeline GraphRAG

Piano completo in [40-graph.md](40-graph.md) + [45-indexing-incrementale.md](45-indexing-incrementale.md).

#### F0 — Prerequisiti sull'ingest esistente (implementati in Fase 1A)

Questi prerequisiti sono già coperti dalla Fase 1A, Step 7. Vengono elencati qui solo come vincolo di dipendenza:

- [x] Chunk in `<base>/.knowledge-space/chunks/<file_id>/<file_id>_chunk_<i>.md`.
- [x] `FileEntry.file_id` (UUID stabile), `chunk_id = base::file_id::i`.
- [x] Metadata Chroma: `chunk_id`, `base_name`, `file_name`, `file_id`, `chunk_index`, `content_hash`.
- [x] `collection.upsert` (no `add_documents(uuid4())`).
- [x] Watcher sorgente ignora `.knowledge-space/`.
- [x] Modelli Pydantic estesi: `ChunkRef` (senza `edited`/`edited_mtime`), `FileEntry` (con `file_id`), `KnowledgeBase` (con `chunking_method`/`ingestion_library`), `WorkspaceConfigData`, `GraphConfigData`.
- [x] Diff incrementale vettoriale funzionante (trigger 1 di [45-indexing-incrementale.md](45-indexing-incrementale.md)).
- [x] Move/rename vettoriale (trigger 2 di [45-indexing-incrementale.md](45-indexing-incrementale.md)).
- [x] Blocco cambio config vettoriale (trigger 3/4/5 di [45-indexing-incrementale.md](45-indexing-incrementale.md)).

#### F1 — Pacchetto e dipendenze

- [ ] Aggiungere `neo4j-graphrag` + `neo4j` + extra `[nlp]` a `knowledge-base`.
- [ ] Creare modulo `knowledge_base/graph/` con `__init__.py`.
- [ ] Creare `graph.json` workspace-level con `bolt_uri`, `database`, `schema_ref`, `embedding_model`.
- [ ] Aggiungere sezione `[graph]` al `BaseConfig` per-base (vedi [30-configuration.md](30-configuration.md)):
  - `schema`, `resolver`, `on_chunk_change`, `chunk_embedding_property`, `retriever`, `top_k`, `vector_index`, `fulltext_index`, `retrieval_query`, `return_properties`.
  - `extraction_model`, `schema_model` (opzionali, vedi [75-llm.md](75-llm.md)): modello LLM per entity extraction e schema extraction.
- [ ] Test caricamento `GraphConfigData` roundtrip JSON.

#### F2 — `KSChunkLoader`

- [ ] Implementare `KSChunkLoader` (custom `neo4j-graphrag`):
  - Legge `<base>/.knowledge-space/chunks/<file_id>/<file_id>_chunk_<i>.md` in ordine `i`.
  - Recupera embedding da Chroma (`collection.get(where={"file_id": file_id, "chunk_index": i})`).
  - Propaga `chunk_id = f"{base_name}::{file_id}::{i}"`.
  - Rispetta flag `active`.
- [ ] Espone `upsert_chunks(base, file_id, changed_chunks: list[ChangedChunk])` per la propagazione incrementale dal vettoriale al grafo.
- [ ] Test unit: `TextChunks` ordinate, embedding coerenti con Chroma reale (fixture), idempotenza su run ripetuti.

#### F3 — Pipeline GraphRAG

- [ ] Assemblaggio pipeline `Pipeline` di `neo4j-graphrag` con:
  1. `KSChunkLoader` → `TextChunks` + `DocumentInfo`
  2. Schema loader (vedi §6-bis di [40-graph.md](40-graph.md))
  3. `LLMEntityRelationExtractor(llm=..., create_lexical_graph=True)` — crea Document/Chunk/NEXT_CHUNK/FROM_DOCUMENT/MENTIONS
  4. `Neo4jWriter(driver, neo4j_database=...)` — MERGE su `__entity__tmp_internal_id` e `chunk_id` deterministico
  5. Entity resolver (vedi F4)
- [ ] Runner `await pipeline.run_async(file_path=..., document_metadata={...})`.
- [ ] Schema loader: `GraphSchema.from_file` se `graph/schema.json` esiste; altrimenti SchemaBuilder/SchemaFromTextExtractor + `save`.
- [ ] Comando `ks graph re-extract-schema <workspace>` per forzare re-estrazione.
- [ ] Test integrazione (test container o DB Neo4j locale): end-to-end su 2 file, verifica nodi/relazioni, idempotenza.

#### F4 — Entity resolution incrementale

- [ ] Resolver default: `SpaCySemanticMatchResolver(driver, filter_query="WHERE NOT entity:Resolved")`.
- [ ] Marcatore `:Resolved` sulle entità già mergeate.
- [ ] Fallback automatico a `SinglePropertyExactMatchResolver` se extra `[nlp]` non installato (warning).
- [ ] Configurabilità via `[graph].resolver`: `"semantic"` (default), `"exact"`, `"fuzzy"` (extra `[fuzzy-matching]`), `"none"` (`perform_entity_resolution=False`).
- [ ] Test: dedup entità con semantic resolver; fallback exact su extra mancante.

#### F5 — Propagazione al grafo (eager/lazy su source change)

Il `KnowledgeBaseManager` orchestra la cascata. Integra i trigger di [45-indexing-incrementale.md](45-indexing-incrementale.md) con la pipeline GraphRAG:

- [ ] **Trigger 1 — content change (eager)**: dopo upsert Chroma, se `[graph].on_chunk_change = "eager"`, lancia pipeline §3 sui soli chunk cambiati (scope mirato: `WHERE (entity)-[:MENTIONS]->(:Chunk {id: '<chunk_id>'})` per il resolver).
- [ ] **Trigger 1 — content change (lazy)**: solo upsert Chroma; `ks graph sync <workspace>` esplicito riallinea il grafo.
- [ ] **Trigger 2 — move/rename**: update property `file_name`/`path` sui nodi `Chunk`/`Document` in Neo4j. Niente re-estrazione.
- [ ] **Trigger 3 — cambio embedding model**: dopo re-embed vettoriale (Fase 1A), propaga i nuovi vettori come property `embedding` sui nodi `Chunk` in Neo4j (via `KSChunkLoader.upsert_chunks` + Cypher `SET chunk.embedding = $emb`). Niente re-estrazione entità.
- [ ] **Trigger 4 — cambio chunking**: dopo re-chunk vettoriale, delete vecchi nodi `Chunk`/`Document` del file + re-estrazione LLM completa.
- [ ] **Trigger 5 — cambio ingestion**: come trigger 4.
- [ ] **Delete file**: `Chroma.delete(ids=[...])` + cleanup nodi `Chunk`/`Document`/relazioni orfane su Neo4j.
- [ ] Estensione comandi `ks reindex` (da Fase 1A) con la parte grafo: `--model-change` → property update Neo4j; `--chunking-change` / `--ingestion-change` → re-estrazione LLM.

#### F6 — Blocco cambio config (parte grafo)

Il blocco lato vettoriale è già implementato in Fase 1A. Qui si aggiunge la validazione della coerenza grafo:

- [ ] Se `[graph].schema` cambia (es. da `"manuale"` a `"EXTRACTED"`) → warning che informa l'utente che il nuovo schema si applica solo ai prossimi chunk, non retroattivamente. Per forzare re-estrazione: `ks graph re-extract-schema <workspace>` + re-run pipeline.

#### F7 — Test di integrazione

Vedi [40-graph.md §13](40-graph.md) per il dettaglio:

- [ ] `KSChunkLoader`: `TextChunks` ordinate, embedding coerenti.
- [ ] `upsert_chunks` (content change): chunks cambiati upsertati, invariati skip.
- [ ] Integrazione Neo4j (test container): end-to-end su 2 file, verifica relazioni, idempotenza.
- [ ] Eager cascade su source change: entità ri-estratte solo sui chunk cambiati.
- [ ] Blocco config: errore atteso su cambio config con collection non vuota.
- [ ] Fallback resolver: senza `[nlp]` → warning + exact.
- [ ] Schema reload: secondo run → nessuna chiamata LLM.
- [ ] Move/rename: `file_name` aggiornato su Neo4j, niente re-estrazione.
- [ ] Mock LLM per non spendere token (vedi [75-llm.md §Test](75-llm.md#test)).

#### F7-bis — Retrieval factory per GraphRAG

- [ ] `RetrieverFactory.build(base_config, graph_config, driver, embedder, llm)` → istanzia il retriever corrispondente a `[graph].retriever` (valori: vector, vector_cypher, hybrid, hybrid_cypher, text2cypher, tools).
- [ ] Creazione indici Neo4j idempotente: vector index + fulltext index (per hybrid retriever).
- [ ] Validazione: retriever non ammesso → errore; `hybrid*` senza `fulltext_index` → errore; `*_cypher` senza `retrieval_query` → warning + default; `text2cypher` richiede `schema.json` presente.
- [ ] Test: factory restituisce classe corretta per ogni valore TOML; errore su valore sconosciuto.

#### F8 — Documentazione

- [ ] `docs/40-graph.md` — specifica completa della pipeline GraphRAG.
- [ ] `docs/45-indexing-incrementale.md` — 5 trigger di reindex e propagazione.
- [ ] Aggiornamenti a `20-data-model.md` / `30-configuration.md` / `10-architecture.md` / `91a-roadmap-fase1-ingestione.md` / questo file.

## Scelte consolidate per questa sottofase

| Aspetto | Scelta |
|---|---|
| Grafo Neo4j | Uno per workspace |
| Resume da | Lexical graph (delegato all'estrattore) + estrazione + risoluzione |
| Schema | Caricato da `schema.json` se esiste; estratto/costruito solo la prima volta |
| Resolver | Semantico (spaCy) come default, fallback exact, configurabile in `[graph].resolver` |
| Propagazione content change | `[graph].on_chunk_change = "eager"` (default) o `"lazy"` |
| Propagazione move/rename | Property-only: `file_name`/`path` su nodi `Chunk`/`Document` |
| Propagazione cambio modello | Property-only: `embedding` sui nodi `Chunk` |
| Propagazione cambio chunking/ingestion | Full re-estrazione: delete vecchi nodi + re-estrazione LLM via `extraction_model` (vedi [75-llm.md](75-llm.md)) |
| Retrieval su grafo | Configurabile `[graph].retriever` per-base (default `hybrid_cypher`) |
| Dipendenza da Fase 1A | Chroma, `file_id`, chunk su disco, diff incrementale |

## Dipendenze con altre fasi

- **Dipende da**: Fase 1A (Chroma, `file_id`, chunk su disco, diff incrementale, blocco cambio config).
- **Opzionalmente usa**: Fase 1B (ricerca vettoriale come fallback per text2cypher o tools retriever).
- **Usata da**: Fase 3 (CLI: comandi `ks graph` e `ks reindex` estesi), Fase 4 (REST API: query GraphRAG).

---

*Ultimo aggiornamento: 21 luglio 2026*
