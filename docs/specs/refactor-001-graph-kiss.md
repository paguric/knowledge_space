# Refactor 001 — Componente grafo: semplificazione KISS

**Autore piano:** agente master · **Tipo:** refactor · **Stato:** in stesura (bozza) · **Priorità:** alta

## Obiettivo

Ridurre il componente grafo (`packages/knowledge-base/src/knowledge_base/graph/`, ~2100 righe) all'osso: meno configurazione, meno modalità, meno file. La pipeline resta: chunk → estrazione LLM → scrittura Neo4j → dedup → retrieval.

## Decisioni concordate (in ordine di pipeline)

### 1. Loader (`chunk_loader.py`) — **invariato**

`KSChunkLoader` legge chunk da disco + embedding da Chroma. Nessuna modifica.

### 2. Propagazione incrementale — **mantenuta**

`upsert_chunks` (chunk cambiati → ri-estrazione mirata) resta. Nessuna modifica.

### 3. Schema (`schema.py`) — **eliminato come input, diventa output**

**Problema risolto:** uno schema generato alla prima esecuzione non scopre le entità che entrano successivamente nel corpus.

**Soluzione:** nessuno schema persistente (niente `schema.json`, niente modalità FREE/manuale/EXTRACTED/da-file). Il grafo è schema-less; quando serve uno schema (text2cypher, ispezione, doc), lo si deriva dal DB al momento:

```cypher
CALL db.labels()
CALL db.relationshipTypes()
CALL db.schema.nodeTypeProperties()
```

Sempre allineato al corpus corrente → nessun meccanismo di aggiornamento incrementale da progettare.

**Estrazione guidata dal prompt, non dallo schema:** l'LLM estrae con label fisse — `(:Entity {name, label})`, relazioni `RELATED_TO` — più i nodi strutturali `Document`/`Chunk` (FROM_DOCUMENT, NEXT_CHUNK). La semantica di dominio sta nella proprietà `label` dell'entità (es. `label: "Persona"`).

### 4. Estrazione (`extraction.py`) — **semplificata, niente pipeline neo4j-graphrag**

**Linea guida**: la libreria `neo4j-graphrag` si usa SOLO per la ricerca (retriever, step 7) e il driver `neo4j` per la connessione. La **costruzione** del grafo è codice nostro: `KSChunkLoader` → `EntityRelationExtractor` → `Neo4jWriter` → resolver (~100 righe di orchestrazione, già scritte). Motivo: la pipeline della libreria presume di partire da file grezzi (data loading, split, embed) — noi abbiamo già chunk+embedding; e la propagazione incrementale (ri-estrazione solo dei chunk cambiati) non calza con le sue run batch.

**Semplificazioni del modulo:**

| Prima | Dopo |
|---|---|
| Label libere (Person, Organization, Concept...) | Label fisse: nodi `Entity {name, label}` — la semantica sta nella proprietà `label` (es. `"Persona"`) |
| Tipi relazione liberi (WORKS_AT...) | Relazioni sempre `RELATED_TO` con proprietà `type` |
| Id locali transitori (n1, n2) + mappatura id→nome | Riferimenti **per name**: `{nodes: [{name, label}], edges: [{source, target, type}]}` |
| `system_prompt` configurabile | Un solo prompt, fisso nel codice |
| `extract_batch` con merge interno | Estrazione per-chunk; aggregazione nel GraphManager |
| JSON invalido → risultato vuoto silenzioso | invariato (warning + skip) |

### 5. Writer (`writer.py`) — **da 10 a 8 metodi**

**Eliminare:** `write_nodes_multi_label` (inutile con label fissa `Entity`), `update_properties` (generico senza chiamanti concreti).

**Tenere:** `write_nodes`, `write_edges`, `delete_chunks`, `delete_file_nodes`, `update_chunk_file_name`, `update_chunk_embeddings` + `create_vector_index`/`create_fulltext_index` (in base al retriever, step 7).

**Propagazione:** i 5 trigger della doc restano invariati (content change eager, move/rename property-only, cambio modello property-only, cambio chunking full, cambio ingestion full) + blocco cambio config.

### 6. Resolver (`resolver.py`) — **1 resolver, niente spaCy**

**Eliminare:** `SpaCySemanticMatchResolver` (dipendenza `spacy` + modello ~40MB, 150 righe di union-find, beneficio dubbio con label fisse), `_NoOpResolver`, `resolver_factory` a 3 vie (via la config `resolver = semantic|exact|none`). Il `FuzzyMatchResolver` della doc non è mai esistito nel codice — non implementarlo.

**Tenere:** `ExactMatchResolver` ridotto a dedup su coppia `(name_normalizzato, label_dominio)` — con label fissa `Entity` il raggruppamento per label Cypher non serve; la discriminazione sta nella proprietà `label` di dominio ("Persona" vs "Organizzazione"). Gli id locali spariti (estrazione per name) → il resolver è solo normalizzazione + rete di sicurezza; la dedup vera avviene nel prompt di estrazione (nomi normalizzati).

### 7. Retriever (`retriever.py`) — **1 solo retriever**

**Tenere:** `HybridCypherRetriever` (vector + fulltext + traversal entità) — l'unico che sfrutta il grafo: senza traversal i risultati sarebbero identici a Chroma. Il default `retrieval_query` (traversal `[:MENTIONS]` chunk→entità) resta.

**Eliminare:** `VectorRetriever`, `VectorCypherRetriever`, `HybridRetriever`, `Text2CypherRetriever`, `ToolsRetriever` (mai implementato), `RetrieverFactory`, config `[graph].retriever` (nessuna scelta → istanziazione diretta nel GraphManager). Restano `create_vector_index` + `create_fulltext_index` (l'hybrid li usa entrambi).

### Invarianti (vincoli non negoziabili)

1. **1 grafo per workspace** (mai per-base): i chunk di tutte le basi del workspace vivono nello stesso grafo Neo4j; `base_name` è una proprietà dei nodi Chunk.
2. **La ricerca sul grafo rispetta domini/basi/file/chunk ATTIVI esattamente come la ricerca vettoriale** (spec feat-020, da allineare al retriever unico):
   - pre-retrieval: `active_base_names` via `is_base_searchable` → filtro `WHERE node.base_name IN $active_base_names` nel retriever;
   - post-retrieval: `filter_active_chunks` sugli stessi `chunk_id`;
   - entità: raggiungibilità dai chunk attivi (traversal), nessun filtro su `base_name` delle entità.

### File da toccare (parziale, in aggiornamento)

| File | Modifica |
|------|----------|
| `graph/schema.py` | Ridurre a helper di derivazione dal DB (o rimuovere) |
| `graph/extraction.py` | Prompt a label fisse, riferimenti per name, rimozione id locali |
| `graph/writer.py` | Rimuovere `write_nodes_multi_label` e `update_properties` |
| `graph/resolver.py` | Solo `ExactMatchResolver`; via spaCy, noop e factory |
| `graph/retriever.py` | Solo `HybridCypherRetriever` + filtro `active_base_names`; via factory e altri 5 |
| `graph/store.py` | Aggiungere query di derivazione schema (labels/relationshipTypes/properties) |
| `docs/40-graph.md` | Riscrivere: niente pipeline neo4j-graphrag in costruzione; schema derivato |

### Punti aperti (prossimi step)

- ~~Estrazione (`extraction.py`)~~ → risolto: label fisse, per name, custom
- ~~Writer (`writer.py`)~~ → risolto: 8 metodi, trigger invariati
- ~~Resolver (`resolver.py`)~~ → risolto: solo exact su (name, label); via spaCy
- ~~Retriever (`retriever.py`)~~ → risolto: solo hybrid_cypher + filtro attivi; invarianti: 1 grafo per workspace, ricerca rispetta stato attivo
- GraphManager (feat-016) e CLI `ks graph` (feat-017): definire dopo i punti sopra

### Verifica (da completare)

```bash
# pipeline end-to-end senza schema.json
ks graph build <workspace>          # nessun file schema generato
ks graph schema <workspace>         # deriva dal DB: label/relazioni correnti
# aggiungere documento con entità nuove → lo schema derivato le mostra
```
