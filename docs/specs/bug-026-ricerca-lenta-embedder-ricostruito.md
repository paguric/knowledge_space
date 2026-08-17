# Bug 026 — ricerca lenta: embedder ricostruito e query ri-embeddata per ogni base

- **Autore:** master
- **Tipo:** bugfix
- **Stato:** da implementare
- **Priorità:** alta

## Causa

1. `src/knowledge_space/cli/search.py` costruisce un **nuovo
   `SearchService` per ogni base** (dentro il loop): `_build_dense_strategy`
   chiama `embedder_factory()` → **ricaricamento del modello
   SentenceTransformer da disco per ogni base** (il costo dominante:
   `ks search` su 3 basi = ~15 s, quasi tutto caricamento modello).
2. `SearchService` non ha cache dell'embedder (ha solo `_llm_cache`);
   la **query viene ri-embeddata per ogni base** (e per ogni query
   generata dalla pre-retrieval).
3. La `collection_factory` è senza argomenti e legata a una sola base
   nel CLI → impedisce di condividere un SearchService tra le basi.

## Fix

1. `SearchService._embedder_cache` (per `model_name`, come
   `KnowledgeBaseManager` e `GraphManager`): un solo caricamento per
   modello.
2. Cache della **query embedding** per `(model_name, query)` nel
   SearchService: il vettore si calcola una volta e si passa a
   `DenseRetrieval.search(..., query_embedding=...)` (nuovo parametro
   opzionale; escluso `hyde`).
3. CLI: **un solo `SearchService` fuori dal loop basi**; la
   `collection_factory` diventa parametro per-chiamata
   (`search(..., collection_factory=...)`) risolta dal CLI con la
   collection della base corrente.

## File da toccare

| File | Modifica |
| --- | --- |
| `packages/knowledge-base/src/knowledge_base/search_service.py` | cache embedder + cache query embedding; `search(..., collection_factory=None)` propagata a `_build_dense_strategy` |
| `packages/knowledge-base/src/knowledge_base/strategies/retrieval.py` | `DenseRetrieval.search(..., query_embedding=None)` |
| `src/knowledge_space/cli/search.py` | un SearchService fuori dal loop; `collection_factory` per-chiamata |
| `packages/knowledge-base/tests/test_retrieval.py` | `query_embedding` passato → niente embed della query |
| `packages/knowledge-base/tests/` (SearchService) | cache embedder/query: factory chiamata una volta per N basi |

## Verifica

```bash
uv run pytest packages/knowledge-base/tests/ -q
time ks search "x" -w <workspace-con-3-basi>   # prima ~15 s → dopo <2 s
```
