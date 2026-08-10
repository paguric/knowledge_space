# Feature 020 — Ricerca su sotto-grafo attivo (compartimentalizzazione domini/basi/file/chunk)

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media (dopo feat-016; requisito di feat-019 `graph_search`)

## Obiettivo

La ricerca su grafo rispetta la compartimentalizzazione del sistema attivo, con la stessa semantica della ricerca vettoriale: basi inattive o in domini inattivi escluse a monte; file/chunk disattivati esclusi a valle; il contesto grafo è limitato al sotto-grafo raggiungibile dai chunk attivi.

## Causa

I retriever di `graph/retriever.py` eseguono query su tutto il grafo Neo4j senza alcun filtro di attivazione.

## Fix (KISS)

1. **`GraphSearchService`** (nuovo `packages/knowledge-base/src/knowledge_base/graph_search_service.py`):
   - `search(workspace, query, top_k)`:
     1. `active_base_names = [b for b, kb in workspace.bases.items() if is_base_searchable(b, kb, workspace.domains)]` (riuso helper di `search_service.py`);
     2. costruisce il retriever da `RetrieverFactory.build(...)` passando `active_base_names`;
     3. post-filtra con `filter_active_chunks(results, kb)` (riuso diretto, stesso formato `chunk_id`).

2. **Filtro pre-retrieval nei retriever**: firma `search(query, *, top_k=5, active_base_names=None, **kwargs)`:
   - `VectorRetriever` / `HybridRetriever`: `WHERE node.base_name IN $active_base_names` dopo `YIELD` (o in `WHERE` full-text);
   - `VectorCypherRetriever` / `HybridCypherRetriever`: vincolo nella `retrieval_query` sui candidati chunk;
   - `Text2CypherRetriever`: vincolo nel template della query generata (limite: possibile; se non iniettabile → post-filtro sui chunk_id);
   - `active_base_names == None` → nessun filtro (compatibilità test esistenti).

3. **Entità condivise**: nessun filtro sul `base_name` delle entità — l'appartenenza al sotto-grafo attivo è la raggiungibilità dai chunk candidati attivi (il traversal parte da chunk già filtrati, quindi il contesto è corretto per costruzione).

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/graph_search_service.py` | **Nuovo**: GraphSearchService |
| `packages/knowledge-base/src/knowledge_base/graph/retriever.py` | Parametro `active_base_names` in 5 retriever |
| `packages/knowledge-base/tests/test_graph.py` | Test filtro active (mock store) |

### Verifica

```bash
# Base in dominio inattivo → nessun risultato dal grafo
ks domain deactivate Paper Accademici
# (graph_search su query che matcherebbe solo lì → 0 risultati)
ks domain activate Paper Accademici
# → risultati tornano
# File disattivato → i suoi chunk non compaiono tra i risultati
```
