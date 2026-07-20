# Pipeline GraphRAG da chunk/embeddings esistenti

Questo documento descrive come Knowledge Space costruisce il grafo della conoscenza su Neo4j **riprendendo** la pipeline ufficiale `neo4j-graphrag` a partire dallo **Lexical Graph Builder**, senza rifare data loading, splitting ed embedding (già calcolati e persistenti in KS).

## Obiettivo e contesto

La pipeline `SimpleKGPipeline` di `neo4j-graphrag` parte da file grezzi e percorre:

```
data_loader -> text_splitter -> chunk_embedder -> lexical_graph_builder
            -> schema_builder -> entity_relation_extractor -> kg_writer -> entity_resolver
```

KS ha già i primi tre step (ingestione, chunking su disco, embedding in Chroma). Il resume parte da **lexical_graph_builder** (in realtà delegato all'estrattore, vedi §3) e percorre il resto, per alimentare un **grafo Neo4j uno per workspace** con cui fare GraphRAG.

Le decisioni consolidate a valle della discussione sono:

| Decisione | Scelta |
|---|---|
| Grafo Neo4j | **Uno per workspace** (non per base) |
| Resume da | Lexical graph + estrazione entità/relazioni + risoluzione |
| Link embedding↔chunk | **ID deterministico `base::file::i` + metadata `chunk_index` in Chroma** |
| Edit chunk da parte dell'utente | **Auto re-embedding via watcher** (`eager` cascade su grafo) |
| Snapshot originale | **Sì**, in `.knowledge-space/snapshots/` per audit |
| Cambio modello embedding | **Bloccato** se la collection non è vuota (serve re-index esplicito) |
| Posizione chunk su disco | **`<base>/.chunks/<file_stem>/<file_stem>_chunk_<i>.md`** (dotfolder dentro la base) |
| Schema del grafo | **Caricato** se `schema.json` esiste; estratto/costruito solo la prima volta |
| Resolver entità | **Semantico (spaCy)** come default, con fallback automatico a exact |

## 1. Layout filesystem

Il layout completo del filesystem del workspace e delle basi (inclusi `.chunks/`, `snapshots/`, `schema.json`, `graph/`) è specificato in un unico punto: [03-configuration.md § Filesystem](03-configuration.md#filesystem).

Per comodità, riassunto dei path rilevanti per la pipeline GraphRAG:

- **Chunk su disco**: `<base>/.chunks/<file_stem>/<file_stem>_chunk_<i>.md` — dotfolder dentro la base, ignorato dal watcher sorgente (F0.4), editabile dall'utente.
- **Snapshot originale**: `<workspace>/.knowledge-space/snapshots/<base>/<file_stem>/<file_stem>_chunk_<i>.orig.md` — per audit pre-edit.
- **Schema del grafo**: `<workspace>/.knowledge-space/schema.json` — caricato, non ricreato (vedi §6-bis).
- **Stato del grafo**: `<workspace>/.knowledge-space/graph/graph.json` — `bolt_uri`, `database`, `embedding_model`, riferimento allo schema.

La **configurazione del comportamento** del grafo (schema, `on_chunk_edit`, `resolver`) resta in `[graph]` del `BaseConfig` per-base (vedi [03-configuration.md](03-configuration.md)).

## 2. Modello dati (estensioni)

Vedi [02-data-model.md](02-data-model.md) per i modelli Pydantic. Riassunto delle estensioni:

- `ChunkRef`: aggiunge `chunk_id: str` (deterministico `base::file::i`), `edited: bool = False`, `edited_mtime: Optional[str] = None`, `content_hash: str` (sha1 del testo).
- `KnowledgeBase`: aggiunge `embedding_model: Optional[str]` (modello usato per indicizzare la collection Chroma; serve §9 per blocco cambio modello).
- `WorkspaceConfigData`: aggiunge `graph: Optional[GraphConfigData]` con `bolt_uri`, `database`, `schema_ref` (path a `schema.json`), `embedding_model` per coerenza.
- Metadata Chroma di ogni chunk: `source`, `chunk_index`, `base_name`, `file_name`, `file_mtime`, `edited`, `edited_mtime`, `content_hash`.

## 3. Pipeline di resume

La pipeline assembla un `neo4j_graphrag.experimental.pipeline.Pipeline` con i componenti seguenti, in ordine:

1. **`KSChunkLoader`** (custom, vedi §4) — produce `TextChunks(...)` con `TextChunk(text, index, metadata={"embedding": <vettore Chroma>, "chunk_id": ...})` + `DocumentInfo(path, metadata)`.
2. **Schema** (vedi §6-bis per dettagli critici):
   - Se `.knowledge-space/schema.json` **esiste già** → `GraphSchema.from_file(...)` (no re-estrazione, no ricostruzione). È il caso normale dopo il primo run.
   - Se non esiste e `[graph].schema = "manuale"` → `SchemaBuilder` con `node_types`/`relationship_types`/`patterns` dal TOML, quindi `save(".knowledge-space/schema.json")` per materializzarlo.
   - Se non esiste e `[graph].schema = "EXTRACTED"` → `SchemaFromTextExtractor` (una tantum sul corpus), quindi `save(...)`.
   - Se `[graph].schema = "FREE"` → niente schema; estrazione libera.
   - Comando CLI per forzare re-estrazione: `ks graph re-extract-schema <workspace>`.
3. **`LLMEntityRelationExtractor(llm=..., create_lexical_graph=True)`** — crea lui la parte **Document/Chunk/NEXT_CHUNK/FROM_DOCUMENT/MENTIONS** a partire dai `TextChunks` + `DocumentInfo` forniti dal loader. **Importante**: non si esegue `LexicalGraphBuilder` separato, per evitare di creare il lexical graph due volte (vedi §6).
4. **`Neo4jWriter(driver, neo4j_database=...)`** — write con `MERGE` su `__entity__tmp_internal_id` e chunk id deterministico → idempotente.
5. **Entity resolver** (vedi §7 per la scelta):
   - **Default raccomandato**: `SpaCySemanticMatchResolver(driver, filter_query="WHERE NOT entity:Resolved")` — risolve "OpenAI" ≈ "OpenAI Inc." tramite embeddings spaCy + cosine similarity. Richiede extra `[nlp]` (`pip install "neo4j-graphrag[nlp]"`).
   - Alternative configurabili via `[graph].resolver`: `"exact"` (`SinglePropertyExactMatchResolver` — più veloce, solo match stringa esatto), `"fuzzy"` (`FuzzyMatchResolver` — Levenshtein via RapidFuzz, extra `[fuzzy-matching]`), `"none"` (`perform_entity_resolution=False`).
   - `:Resolved` etichetta i nodi già mergeati così i run successivi non li ri-processano.

Runner (per file o batch):

```python
await pipeline.run_async(file_path=..., document_metadata={"base_name":..., "file_mtime":...})
```

`DocumentInfo` (path, metadata) deriva dal modello dominio KS. L'esecuzione rispetta i flag `active` a tutti i livelli (workspace/domain/base/file/chunk).

## 4. `KSChunkLoader` (componente custom)

Sostituisce data loader + text splitter + chunk embedder della `SimpleKGPipeline`.

Input: `(base_name, file_path, mtime)` dal modello dominio.

Output: `TextChunks` ordinate per `index`, con `TextChunk.metadata["embedding"]` preso da Chroma.

Logica:
- Legge `<base>/.chunks/<file_stem>/*_chunk_<i>.md` in ordine `i`.
- Per ogni `i`, recupera l'embedding dal Chroma collection della base via `collection.get(where={"source": file_path, "chunk_index": i}, include=["embeddings"])`.
- Propaga `chunk_id = f"{base_name}::{file_stem}::{i}"` (lo stesso id usato in Chroma e come `Neo4jNode.id` nel writer).
- Salta chunk/ file/ basi inattivi scorrendo `WorkspaceConfigData`.

Espone inoltre `upsert_chunk(base, file, index, new_text)`:
1. Ricalcola embedding via `EmbeddingStrategy` (modello corretto per la base).
2. `collection.upsert(ids=[chunk_id], documents=[new_text], embeddings=[emb], metadatas=[...])` preservando i metadata esistenti.
3. Setta `edited=true`, `edited_mtime=now`, ricalcola `content_hash`.
4. Scrive lo snapshot originale in `.knowledge-space/snapshots/<base>/<file_stem>/<file_stem>_chunk_<i>.orig.md` **solo se non esiste già** (è l'originale pre-edit, da preservare una tantum). Il file chunk su disco non va scritto qui: è l'utente che ha editato il file, KS riflette.

## 5. Edit handler (eager cascade)

`ChunkWatcher` dedicato: osserva `<base>/.chunks/**/*.md` con **debounce ~500ms** e confronto `content_hash` (skip se hash invariato, per evitare re-embed su save identici o stati intermedi dell'editor).

Su `modified` di `..._chunk_<i>.md`:
1. `KSChunkLoader.upsert_chunk` → snapshot + upsert Chroma.
2. Cascade `on_chunk_edit = "eager"` (default): rilancia il pipeline §3 sul singolo chunk, con `filter_query` mirato `WHERE (entity)-[:MENTIONS]->(:Chunk {id: '<chunk_id>'})` per il resolver scope (non tocca altre entità).
3. Marcatore `:Resolved` sulle entità nuove/mergeate.

`[graph].on_chunk_edit = "lazy"` (alternativa): esegue solo lo step 1; il grafo si riallinea al prossimo run esplicito.

Eventi:
- `deleted`: `Chroma.delete(ids=[chunk_id])` + Cypher di cleanup su Document/Chunk orfani (custom `KGWriter` o script separato).
- `moved`/`renamed`: gestito come delete+create del chunk, propagando il nuovo `chunk_id`.

## 6. Decisione tecnica: evitare il lexical graph due volte

`LLMEntityRelationExtractor` con `create_lexical_graph=True` crea autonomamente i nodi `Document` e `Chunk` e le relazioni `NEXT_CHUNK`, `FROM_DOCUMENT`, `MENTIONS` entity↔chunk. Se si eseguisse `LexicalGraphBuilder` separato **prima** dell'estrattore, si creerebbero i nodi Document/Chunk due volte.

La scelta consolidata: **non eseguire `LexicalGraphBuilder` separato**. Passare solo `TextChunks` (con embedding+index+chunk_id) e `DocumentInfo` all'estrattore, lasciare a lui la costruzione del lexical graph. Da verificare in F7.3 con un test di integrazione che conta i nodi `Document` e `Chunk` attesi dopo due run dello stesso file.

## 6-bis. Schema del grafo: caricare, non ricreare

Lo schema (lista di `node_types`/`relationship_types`/`patterns` che grounda l'LLM) **non va ricreato a ogni run** della pipeline. È una decisione di dominio stabile.

Stati possibili di `.knowledge-space/schema.json`:

| Stato file | `[graph].schema` | Azione |
|---|---|---|
| Esiste | qualsiasi | `GraphSchema.from_file(...)` — **sempre ricaricato, no LLM**. È il caso normale dopo il primo run. |
| Mancante | `"manuale"` | `SchemaBuilder` con `node_types`/`relationship_types`/`patterns` dal TOML e `save(...)` → materializza il file per i run successivi. |
| Mancante | `"EXTRACTED"` | `SchemaFromTextExtractor` (una tantum, una chiamata LLM sul corpus/titoli) e `save(...)`. |
| Mancante | `"FREE"` | niente schema, niente file. |

Per forzare la re-estrazione (utente che cambia idea sui tipi dopo aver visto il grafo): comando CLI `ks graph re-extract-schema <workspace>` che cancella `schema.json` e ripristina `[graph].schema` al valore voluto. Il re-run completo del pipeline viene lanciato esplicitamente (non è automatico: le entità già estratte col vecchio schema non vengono automaticamente migrate; vanno rimosse o lasciate coesistere).

Nota: lo schema manuale è **statico per definizione** (l'utente lo ha scritto una volta nel TOML). La "materializzazione" su `schema.json` serve solo per uniformare il path di caricamento di tutti i casi; potenzialmente si potrebbe anche non salvare e ricostruire dall'oggetto `SchemaBuilder` ogni volta, ma materializzare rende il tavolo di debug ispettabile e il flusso uniforme con il caso `EXTRACTED`.

## 7. Entity resolution: resolver semantico come default

La pipeline include un passo di entity resolution (vedi §3, passo 5) per collassare duplicati (entità che l'LLM ha battezzato diversamente tra chunk/file). Uno schema stringente non basta: l'LLM può sempre emettere "OpenAI" e "OpenAI Inc." per la stessa entità.

Tre implementazioni sono disponibili in `neo4j-graphrag`:

| Resolver | Tecnica | Extra | Quando |
|---|---|---|---|
| `SpaCySemanticMatchResolver` | embeddings spaCy + cosine similarity sui nomi | `[nlp]` (`pip install "neo4j-graphrag[nlp]"`) | **Default raccomandato**: distingue "OpenAI" ≈ "OpenAI Inc." ma non "OpenAI" ≈ "CloseAI". Buon compromesso precisione/costo. |
| `FuzzyMatchResolver` | Levenshtein (RapidFuzz) | `[fuzzy-matching]` | Match ortografico veloce, niente embeddings. Utile per typo e varianti ortografiche. |
| `SinglePropertyExactMatchResolver` | match esatto `name` + `label` | nessuno | Il più veloce, più conservativo. Niente risoluzione semantica. |

Configurazione via `[graph].resolver`:

```toml
[graph]
resolver = "semantic"   # default: SpaCySemanticMatchResolver
# resolver = "exact"    # SinglePropertyExactMatchResolver (no extra)
# resolver = "fuzzy"    # FuzzyMatchResolver (extra [fuzzy-matching])
# resolver = "none"     # perform_entity_resolution = False
```

In tutti i casi con resolver attivo, si usa `filter_query = "WHERE NOT entity:Resolved"` per processare sole le entità nuove a ogni run incrementale, e l'etichetta `:Resolved` marca i nodi già mergeati così i run successivi non li ri-processano. Il costo del resolver è proporzionale al numero di entità nuove, non al totale.

Validazione all'avvio: se `[graph].resolver = "semantic"` ma l'extra `[nlp]` non è installato, KS logga un warning e **fallback** a `exact` (così la base continua a funzionare in degrado). Stesso discorso per `fuzzy` senza `[fuzzy-matching]`.

## 8. Grafo Neo4j uno per workspace

- Il workspace possiede un solo DB Neo4j (o una sola istanza con `database` separato per workspace).
- `graph.json` (`<workspace>/.knowledge-space/graph/graph.json`) registra `bolt_uri`, `database`, `schema_ref`, `embedding_model` per coerenza.
- Ogni entità/chunk ha `base_name` come property; le `Domain` KS possono diventare property aggiuntiva (`domain_name`) per query GraphRAG cross-base. Scelta conservativa: usare property (più flessibile, niente label proliferanti).
- `[graph]` nel `BaseConfig` per-base gestisce: schema (manuale/EXTRACTED/FREE), `resolver`, `on_chunk_edit`, `chunk_embedding_property`. I **parametri di connessione** (bolt_uri, credenziali) sono a livello workspace in `graph.json` (perché il DB è uno per workspace), non per-base.

## 9. Blocco cambio modello embedding

Al caricamento di `BaseConfig`, se `[embedding].model` differisce da `bases[<base>].embedding_model` registrato in `config.json` **e** la collection Chroma non è vuota → errore che suggerisce il comando di re-index completa:

```
ks reindex <base> --model-change
```

`ks reindex <base> --model-change`: crea una nuova collection, re-embed dei chunk letti da disco, aggiorna `embedding_model` registrato, invalida/sostituisce la vector search finché completato. Fuori scope del primo sviluppo; prerequisito del blocco è solo il check + errore.

## 10. Dipendenze

- Aggiungere a `knowledge-base`: `neo4j-graphrag` + `neo4j` driver.
- Extra necessari per il resolver default: `[nlp]` (`pip install "neo4j-graphrag[nlp]"`).
- Extra opzionali: `[fuzzy-matching]` per `FuzzyMatchResolver`.

## 11. Fasi di implementazione

Ordine consigliato (bloccanti dall'alto in basso):

- **F0 — Prerequisiti su ingest esistente**
  - F0.1 Spostare i chunk da `chunks_dir` globale a `<base>/.chunks/<file_stem>/<file_stem>_chunk_<i>.md`. Rimuovere la variabile globale `chunks_dir` (legacy cleanup Step 13).
  - F0.2 ID deterministico `base::file::i` in Chroma e come `Neo4jNode.id`.
  - F0.3 Estensione metadata Chroma + upsert (no `add_documents(uuid4())`).
  - F0.4 Watcher sorgente ignora i path che iniziano con `.` (`.chunks/`, `.knowledge-space/`).
  - F0.5 `ChunkRef`/`FileEntry`/`KnowledgeBase` Pydantic estesi (vedi §2).
  - F0.6 `EmbeddingStrategy` (Step 6 roadmap) usata sia in indicizzazione sia come Embedder GraphRAG.
  - F0.7 Test idempotenza: riesecuzione di `add_file` non duplica record Chroma né chunk su disco.

- **F1 — Pacchetto e dipendenze**
  - F1.1 `neo4j-graphrag` + `neo4j` + extra `[nlp]` in `knowledge-base`.
  - F1.2 Modulo `knowledge_base/graph/`.
  - F1.3 `graph.json` workspace + sezione `[graph]` TOML per-base (vedi [03-configuration.md](03-configuration.md)).
  - F1.4 Test caricamento `GraphConfigData` roundtrip JSON.

- **F2 — `KSChunkLoader`**
  - F2.1 Implementazione del loader (§4).
  - F2.2 Espone `upsert_chunk` (§4).
  - F2.3 Rispetto dei flag `active`.
  - F2.4 Test unit con fixture Chroma temporanea: `TextChunks` ordinate e embedding coerenti.

- **F3 — Pipeline GraphRAG**
  - F3.1 Assemblaggio pipeline (§3).
  - F3.2 Schema: caricamento `GraphSchema.from_file` se esiste; altrimenti manuale/EXTRACTED/FREE + `save` (vedi §6-bis).
  - F3.3 `Neo4jWriter` con `MERGE` idempotente.
  - F3.4 Runner `await pipeline.run_async(file_path=..., document_metadata={...})`.

- **F4 — Entity resolution incrementale**
  - F4.1 Resolver default `SpaCySemanticMatchResolver` con `filter_query = "WHERE NOT entity:Resolved"`.
  - F4.2 Marcatore `:Resolved`.
  - F4.3 Fallback automatico a `exact` se extra `[nlp]` mancante.
  - F4.4 Configurabilità via `[graph].resolver` (vedi §7).

- **F5 — ChunkWatcher (eager cascade)**
  - F5.1 Watcher su `<base>/.chunks/**/*.md` con debounce + hash check.
  - F5.2 Workflow `upsert_chunk` -> pipeline §3 con scope mirato (§5).
  - F5.3 `on_chunk_edit` eager/lazy da `[graph]`.
  - F5.4 Delete/rename handling.
  - F5.5 Test: edit chunk -> Chroma aggiornato, grafo allineato, idempotenza su re-save identico.

- **F6 — Blocco cambio modello**
  - F6.1 Errore se `model` differisce da `embedding_model` registrato e collection non vuota.
  - F6.2 (deferred) `ks reindex <base> --model-change`.

- **F7 — Test di integrazione** (vedi §12).

- **F8 — Documentazione** (questo file + aggiornamenti).

## 12. Rischi e limiti noti

- **Resolver semantico non è magico**: `SpaCySemanticMatchResolver` collassa nomi simili per significato;Near misses come "OpenAI" ≈ "CloseAI" potrebbero in teoria essere sbagliati ma la cosine similarity ha una soglia. Possibile regolare la soglia o passare a `fuzzy` se si vedono falsi positivi. L'exact resta fallback sicuro.
- **Ri-estrazione su edit (eager)**: costa una chiamata LLM per chunk editato. Mitigato dal debounce + hash check.
- **Edit che espande un chunk oltre `chunk_size`**: si rispetta l'edit manuale, niente ri-chunking automatico (cancellerebbe le modifiche). Warning opzionale se la lunghezza diverge molto dal config.
- **Race conditions watcher**: Chroma PersistentClient è safe per singolo processo; il `ChunkWatcher` deve condividere la stessa istanza collection del watcher sorgente. Per più processi (REST + MCP) serve sincronizzazione (vedi [05-roadmap-overview.md](05-roadmap-overview.md) Considerazioni e rischi).
- **Neo4j non embedded**: serve un'istanza Neo4j in esecuzione (locale o remota). Documentare requisiti runtime in una sezione "Prerequisiti" del README o in `docs/12-rest-api.md`.
- **Re-estrazione schema non migra le entità vecchie**: cambiare schema non riscrive le entità estratte col vecchio; l'utente deve cancellarle Cypher-side o accettare coesistenza.

## 13. Test

- **F7.1 Unit `KSChunkLoader`**: `TextChunks` ordinate, embedding coerenti con Chroma reale (fixture), idempotenza su run ripetuti.
- **F7.2 Unit edit**: modifica `..._chunk_1.md` -> `upsert` Chroma (niente duplicato), `edited=true`, snapshot scritto una sola volta.
- **F7.3 Integrazione Neo4j** (test container o DB locale): end-to-end su 2 file, verifica `NEXT_CHUNK`/`FROM_DOCUMENT`/`MENTIONS`, idempotenza, dedup resolver (semantic + exact fallback).
- **F7.4 Eager cascade**: edit chunk -> entità ri-estratte, grafo allineato, `filter_query` non tocca altri chunk.
- **F7.5 Blocco modello**: cambio `model` con collection non vuota -> errore atteso.
- **F7.6 Fallback resolver**: `[graph].resolver = "semantic"` senza extra `[nlp]` installato -> warning + fallback a `exact`.
- **F7.7 Schema reload**: secondo run con `schema.json` esistente -> nessuna chiamata LLM allo `SchemaFromTextExtractor` (verificato con mock counter).
- **F7.8 Mock LLM**: per non spendere token nei test di estrazione.

## 14. Retrieval: metodo di ricerca configurabile dall'utente

La pipeline GraphRAG separa la **costruzione** del grafo (SimpleKGPipeline, §3) dalla **ricerca** (retrievers di `neo4j-graphrag`). L'app non hardcodizza un solo retriever: espone tutti i metodi supportati e **istanzia quello specificato dall'utente** nella config per-base `[graph].retriever` (con fallback a `GraphConfigData.retriever` workspace-level, default `"hybrid_cypher"`).

### Tabella dei valori ammessi per `[graph].retriever`

| Valore TOML        | Classe `neo4j-graphrag`     | Richiede vector index | Richiede full-text index | Usa LLM | Note |
|--------------------|-----------------------------|:---:|:---:|:---:|------|
| `vector`           | `VectorRetriever`           | sì  | no  | no  | Similarità pura ANN. Supporta `filters`, `return_properties`. |
| `vector_cypher`    | `VectorCypherRetriever`     | sì  | no  | no  | Vector + `retrieval_query` Cypher per arricchire con traversal. |
| `hybrid`           | `HybridRetriever`           | sì  | sì  | no  | Vector + BM25 (full-text). No `filters`. |
| `hybrid_cypher`    | `HybridCypherRetriever`     | sì  | sì  | no  | **Default**. Hybrid + `retrieval_query`. Ideale per GraphRAG generico. |
| `text2cypher`      | `Text2CypherRetriever`      | no  | no  | sì  | LLM traduce la domanda in Cypher. Richiede `neo4j_schema` (usato `schema.json`). No embedder. |
| `tools`            | `ToolsRetriever`            | dipende dai tool | dipende | sì  | LLM seleziona/combinarà tool (altri retriever via `convert_to_tool()`). Per workflow multi-modali. |

> I retriever per DB vettoriali esterni (`WeaviateNeo4jRetriever`, `PineconeNeo4jRetriever`, `QdrantNeo4jRetriever`) **non** sono esposti come valore TOML: il progetto usa Chroma come vector store (e Neo4j solo per il grafo). Se in futuro si vuole supportare un vector DB esterno, aggiungere valori `weaviate`/`pinecone`/`qdrant` con extra corrispondenti.

### Parametri di retrieval in `[graph]` (TOML per-base)

| Campo | Tipo | Default |Usato da |
|---|---|---|---|
| `retriever` | str | `"hybrid_cypher"` | tutti (selezione) |
| `top_k` | int | `5` | tutti i vettoriali/hybrid |
| `vector_index` | str | `"chunk-embeddings"` | `vector*`/`hybrid*` |
| `fulltext_index` | str | `"chunk-text"` | `hybrid*` (obbligatorio) |
| `retrieval_query` | str (multiline) | vedi `defaults.toml` | `*_cypher` (arricchimento Cypher) |
| `return_properties` | list[str] | `["chunk_id", "text"]` | `vector` (espostoending) |

### Fallback workspace-level

`GraphConfigData.retriever` (default `"hybrid_cypher"`) è il valore usato se una base **non** specifica `[graph].retriever` nel suo TOML. Questo permette di cambiare il retriever di default per tutto il workspace in un solo punto (vedi [02-data-model.md](02-data-model.md) `GraphConfigData`).

### Factory lato app

Il modulo `knowledge_base/graph/` esporrà una `RetrieverFactory` che, dato il `BaseConfig` (e il `GraphConfigData` del workspace), restituisce l'istanza del retriever corretta + l'`embedder` e il `driver` Neo4j già costruiti dall'`AppContext`. Pattern:

```python
retriever = RetrieverFactory.build(base_config, graph_config, driver, embedder, llm)
rag = GraphRAG(retriever=retriever, llm=llm)
response = rag.search(query_text=query, retriever_config={"top_k": base_config.graph.top_k})
```

Validazione all'avvio:
- `retriever` non ammesso → errore di config con la tabella above.
- `hybrid*` senza `fulltext_index` → errore.
- `*_cypher` senza `retrieval_query` → warning + `retrieval_query` di default (ritorna solo `node` + `score`).
- `text2cypher` richiede `schema.json` materializzato (fallback: estrazione on-the-first-run, vedi §6-bis).

### Indici da creare su Neo4j

Oltre al vector index (`create_vector_index`) sul nodo `Chunk`, per i retriever `hybrid*` serve un **full-text index** (BM25) sul testo del chunk:

```python
from neo4j_graphrag.indexes import create_fulltext_index
create_fulltext_index(driver, "chunk-text", node_label="Chunk", node_properties=["text"])
```

La creazione degli indici va fatta una sola volta per workspace (idempotente) durante la fase F3 o in un comando `ks graph init <workspace>`.

### Limiti

- Vector index usa **ANN** (approximate nearest neighbor): può non restituire i top-k esatti (vedi [Neo4j vector index limitations](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/#limitations-and-issues)).
- `text2cypher` non garantisce query Cypher sintatticamente valide: l'app deve gestire `Text2CypherRetrievalError` con fallback a un retriever vettoriale.
- `tools` ha costo di una chiamata LLM per il routing; preferire per query complesse.

Fonti: [User Guide: RAG](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html), [repo neo4j-graphrag-python](https://github.com/neo4j/neo4j-graphrag-python).

---

*Ultimo aggiornamento: 17 luglio 2026*