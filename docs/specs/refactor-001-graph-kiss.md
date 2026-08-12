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

### File da toccare (parziale, in aggiornamento)

| File | Modifica |
|------|----------|
| `graph/schema.py` | Ridurre a helper di derivazione dal DB (o rimuovere) |
| `graph/extraction.py` | Prompt con label fisse Entity/RELATED_TO (da confermare) |
| `graph/store.py` | Aggiungere query di derivazione schema (labels/relationshipTypes/properties) |

### Punti aperti (prossimi step)

- Estrazione (`extraction.py`): prompt, batch, parsing
- Writer (`writer.py`): quali metodi servono davvero
- Resolver (`resolver.py`): quanti resolver tenere (oggi 4: semantic/fuzzy/exact/noop)
- Retriever (`retriever.py`): quanti dei 6 metodi tenere (oggi: vector, vector_cypher, hybrid, hybrid_cypher, text2cypher, tools)
- GraphManager (feat-016) e CLI `ks graph` (feat-017): definire dopo i punti sopra

### Verifica (da completare)

```bash
# pipeline end-to-end senza schema.json
ks graph build <workspace>          # nessun file schema generato
ks graph schema <workspace>         # deriva dal DB: label/relazioni correnti
# aggiungere documento con entità nuove → lo schema derivato le mostra
```
