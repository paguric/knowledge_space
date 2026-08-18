# 40 — Grafo di conoscenza (Neo4j)

## Modello

**Un grafo per workspace** (mai per-base): i chunk di tutte le basi stanno
nello stesso database Neo4j; `base_name` è una proprietà dei nodi `Chunk`.

Nodi e relazioni (label fisse, semantica nelle proprietà):

```
(:Document {file_id, file_name, base_name})
(:Chunk    {chunk_id, base_name, file_id, file_name, index, text, embedding, content_hash})
(:Entity   {name, label})                    # label semantica: "Persona", "Organizzazione", "Legge"...

(Document)-[:HAS_CHUNK]->(Chunk)
(Chunk)-[:MENTIONS]->(Entity)                # relazione strutturale
(Entity)-[:RELATED_TO {type}]->(Entity)
```

`chunk_id` coincide con quello di Chroma: `{base_name}::{file_id}::{index}`.

Nessuno schema persistente (`schema.json` eliminato): lo schema si deriva
dal DB a richiesta (`ks graph schema`: `db.labels()`,
`db.relationshipTypes()`, `db.schema.nodeTypeProperties()`).

## Configurazione `[graph]` (TOML, cascata per-base)

```toml
[graph]
enabled = false               # interruttore
on_chunk_change = "lazy"      # "eager" | "lazy" — propagazione trigger 1
top_k = 5                     # default risultati graph search
extraction_model = "lm-studio/auto"   # LLM per l'estrazione entità (pattern doc 75)
embedding_model = "BAAI/bge-m3"
```

- `extraction_model = None` → **grafo INATTIVO**: l'estrazione entità
  richiede un LLM, senza modello non c'è nulla da estrarre (nessun
  fallback rule-based). Ogni comando è un no-op con warning.
- `embedding_model` ha lo **stesso default delle basi**: nel caso comune
  il riciclo degli embedding da Chroma è sempre attivo. Base con modello
  diverso → ricalcolo col modello del grafo (una tantum, Chroma intatto).

Connessione Neo4j: **fuori dal TOML** — env `NEO4J_URI` / `NEO4J_USER` /
`NEO4J_PASSWORD` / `NEO4J_DATABASE`; al primo `build_graph` la connessione
viene salvata in `<workspace>/.knowledge-space/graph/graph.json` e riusata.

## Pipeline

`KSChunkLoader` (testo chunk da disco + embedding da Chroma o ricalcolati)
→ `EntityRelationExtractor` (LLM, per-chunk, JSON con riferimenti **per
nome**) → `Neo4jWriter` (MERGE idempotente: Document/Chunk/HAS_CHUNK,
Entity/MENTIONS/RELATED_TO) → `ExactMatchResolver` (dedup di sicurezza su
`(nome normalizzato, label)`).

Niente `neo4j-graphrag` per la costruzione (solo driver `neo4j`, import
lazy): i chunk sono già prodotti dalla Fase 1A.

## Propagazione (hook nel watcher)

`WorkspaceManager.sync_and_ingest()` al termine propaga al grafo:

- basi rimosse → `remove_base` (Document/Chunk cancellati);
- poi `sync_base` per le basi con grafo attivo: diff per `content_hash`
  dei chunk — solo i cambiati vengono cancellati e ri-estratti;
- dopo ogni delete → `delete_orphan_entities` (Entity senza più MENTIONS).

Errori **non fatali**: Neo4j giù → WARNING nel log, riallineamento alla
sync successiva.

## Ricerca

Un solo retriever: `HybridCypherRetriever` (vector + full-text + traversal
MENTIONS, indici `chunk-embeddings` e `chunk-text`).

`GraphSearchService` applica l'**invariante attivi** come la ricerca
vettoriale: pre-retrieval `active_base_names` (via `is_base_searchable`,
domini e basi attivi), post-retrieval `filter_active_chunks` (file/chunk
attivi). Usato da `ks graph search` e dal tool MCP `graph_search`.

## Comandi

```bash
ks config set graph.enabled true          # + extraction_model (TOML)
ks graph init -w ~/ws                     # build completo
ks graph sync -w ~/ws [--base <nome>]     # propagazione incrementale
ks graph status -w ~/ws                   # connessione + conteggi dal DB
ks graph schema -w ~/ws                   # schema derivato dal DB
ks graph search -w ~/ws "domanda"         # ricerca con filtro attivi
```

## Tool MCP

Solo lettura (coerente con il vincolo MCP read-only):

- `graph_status()` — stato del grafo del workspace attivo;
- `graph_search(query, top_k)` — ricerca con filtro attivi.

## Dipendenze

`neo4j` non è tra le dipendenze del progetto: import lazy con messaggio
chiaro al primo uso (`pip install neo4j` / `uv add neo4j`).
