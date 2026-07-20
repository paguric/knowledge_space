# Pipeline di retrieval

## Obiettivo

Implementare la pipeline di ricerca completa, configurabile via TOML per base. La pipeline ha **tre step sequenziali**: pre-retrieval → retrieval → post-retrieval. Ogni step accetta `method = "identity"` come **no-op esplicito** (i dati passano through, senza istanziare LLM/reranker). Questo mantiene la pipeline sempre omogenea: l'intento dell'utente è dichiarato nel TOML, non dedotto dall'assenza di configurazione.

```
query → [pre-retrieval] → [retrieval] → [post-retrieval] → chunk rilevanti
         (query rewrite)  (search)      (rerank + compress)
```

Orderine fisso: **retrieve → rerank → compress** (l'LLM generatore vede solo ciò che esce dal compressor).

## Pre-retrieval: query rewriting

Sezione `[pre_retrieval]`. Modifica la query dell'utente prima di passarla al retrieval, per migliorare la recall.

```toml
[pre_retrieval]
method = "identity"   # "identity" | "hyde" | "multi_query"
params = {}           # parametri specifici del metodo
```

### Interfaccia `QueryRewriter`

```python
class QueryRewriter(Protocol):
    name: str
    def rewrite(self, query: str, **params) -> list[str]:
        """Restituisce una o più query riscritte."""
        ...
```

### Strategie

| Method | Descrizione | Parametri | Richiede LLM |
|--------|-------------|-----------|:---:|
| `identity` | No-op: restituisce `[query]` così com'è. | — | no |
| `hyde` | Hypothetical Document Embeddings: genera un documento ipotetico che risponderebbe alla query, usa il suo embedding per cercare. | — | sì |
| `multi_query` | Espande la query in N sotto-query con LLM (es. diverse prospettive) e unisce i risultati. | `n_queries: int = 3`, `llm: str` | sì |

## Retrieval

Sezione `[retrieval]`. Esegue la ricerca vera e propria sul vector store (dense) e/o indice testuale (sparse).

```toml
[retrieval]
method = "dense"         # "dense" | "sparse" | "hybrid"
fusion = "rrf"           # "rrf" (default, robusto) | "weighted_sum" (richiede pesi)
expansion = "none"       # "none" | "parent_child" (in pausa)
```

### Interfaccia `RetrievalStrategy`

```python
class RetrievalStrategy(Protocol):
    name: str
    def search(self, query: str, top_k: int = 10, **filters) -> list[dict]:
        """Restituisce chunk rilevanti con score. I filtri attivo (workspace,
        dominio, base, file, chunk) sono passati come kwargs."""
        ...
```

### Metodi di retrieval

**Dense** — similarity search sul vector store (Chroma). Sempre disponibile. Usa il modello di embedding configurato per la base.

**Sparse** — BM25-like. Due casi:

1. **Modello con sparse nativo** (es. `BAAI/bge-m3` espone `embed_sparse`): usato direttamente.
2. **Modello senza sparse** (es. `all-mpnet-base-v2`): **fallback automatico a BM25 esterno** tramite `rank_bm25` (puro Python) sul testo grezzo dei chunk. Un warning di log viene emesso all'avvio per segnalare il fallback.

**Hybrid** — ensemble di dense + sparse con fusione configurabile:

| Fusion | Descrizione |
|--------|-------------|
| `rrf` (default) | Reciprocal Rank Fusion. Robusto, non richiede tuning di pesi. |
| `weighted_sum` | Somma pesata di score dense e sparse. Richiede peso esplicito (`dense_weight`, `sparse_weight`). |

### Parent-Child expansion (in pausa)

Pattern **Small-to-Big**. Quando `[retrieval].expansion = "parent_child"`, il retrieval matcha sui **child** (chunk piccoli prodotti dal chunker base, precisione alta) ma restituisce il **parent** collegato (chunk più ampio, più contesto).

- `parent_granularity = "section" | "paragraph"` (default: `"section"`).
- Il chunker base resta libero (ogni strategy produce child); il parent è una ricombinazione dei child che condividono lo stesso header/parent_id.
- Implementazione rimandata dopo la validazione Fase 2.

## Post-retrieval: rerank e compress

Sezione `[post_retrieval]`. Filtraggio, riordino e compressione dei risultati prima di passarli all'LLM generatore.

```toml
[post_retrieval]
top_k = 10                    # risultati finali (applicato ultimo)
reranker = "identity"          # "identity" | "cross_encoder" | "llm"
compressor = "identity"        # "identity" | "llm_chain_extract"
```

### Interfacce separate

Reranker e Compressor rispondono a domande diverse:

- **Reranker**: "quali tra questi chunk sono i più rilevanti per la query?" (classificatore a coppie query↔chunk).
- **Compressor**: "quali contenuti, tra quelli rilevanti, devono essere passati all'LLM?" (estrazione, sintesi).

```python
class Reranker(Protocol):
    name: str
    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]:
        """Riordina i chunk per rilevanza, restituisce top_k."""
        ...

class Compressor(Protocol):
    name: str
    def compress(self, query: str, chunks: list[dict]) -> str:
        """Restituisce il testo compresso/sintetizzato da passare all'LLM."""
        ...
```

### Strategie di rerank

| Method | Descrizione | Richiede LLM |
|--------|-------------|:---:|
| `identity` | No-op: l'ordine del retrieval rimane invariato. | no |
| `cross_encoder` | Modello cross-encoder (es. `BAAI/bge-reranker-v2-m3`) per riordinare chunk per rilevanza. | no (modello dedicato) |
| `llm` | LLM riordina i chunk per rilevanza (più costoso). | sì |

Parametro `reranker_model` (opzionale) specifica il modello da usare per `cross_encoder` o `llm`:

```toml
[post_retrieval]
reranker = "cross_encoder"
reranker_model = "BAAI/bge-reranker-v2-m3"
```

### Strategie di compression

| Method | Descrizione | Richiede LLM |
|--------|-------------|:---:|
| `identity` | No-op: restituisce il testo dei chunk così com'è. Utile per profilo `consulente` (i documenti non devono essere riassunti). | no |
| `llm_chain_extract` | Langchain `LLMChainExtractor`: estrae dal chunk solo le parti rilevanti per la query. | sì |

## Registry delle strategie

Tutte le strategy (query rewriter, retriever, reranker, compressor) sono registrate nel proprio registry con metadati discoverable:

```python
{
    "identity": {"requires_llm": False, "params_schema": {}},
    "hyde": {"requires_llm": True, "params_schema": {}},
    "multi_query": {"requires_llm": True, "params_schema": {"n_queries": int}},
    "dense": {"requires_embedder": True, "requires_sparse_model": False},
    "sparse": {"requires_embedder": False, "can_fallback_bm25": True},
    "hybrid": {"requires_embedder": True, "can_fallback_bm25": True},
    "cross_encoder": {"requires_model": True},
    "llm_chain_extract": {"requires_llm": True},
}
```

## Configurazione TOML completa (esempi)

### Profilo consulente (nessuna manipolazione)

```toml
[pre_retrieval]
method = "identity"

[retrieval]
method = "dense"

[post_retrieval]
top_k = 10
reranker = "identity"
compressor = "identity"
```

### Profilo ricercatore (pipeline avanzata)

```toml
[pre_retrieval]
method = "multi_query"
params = { n_queries = 3 }

[retrieval]
method = "hybrid"
fusion = "rrf"

[post_retrieval]
top_k = 10
reranker = "cross_encoder"
reranker_model = "BAAI/bge-reranker-v2-m3"
compressor = "llm_chain_extract"
```

## Fasi di implementazione

- **F0 — Interfacce e registry**: definire `QueryRewriter`, `RetrievalStrategy`, `Reranker`, `Compressor` (Protocol). Registry separati per ciascuno.
- **F1 — Identity per tutti**: implementare `identity` per pre/post-retrieval e `dense` per retrieval. Pipeline completa minimale funzionante.
- **F2 — Sparse retrieval**: BM25 fallback con `rank_bm25`. Test su modello solo-dense (es. `all-mpnet-base-v2`) che verifica il warning + fallback.
- **F3 — Hybrid retrieval**: dense + sparse + `rrf` / `weighted_sum`.
- **F4 — Pre-retrieval avanzato**: `hyde` (mock LLM nei test) e `multi_query`.
- **F5 — Post-retrieval**: `cross_encoder` e `llm_chain_extract`.
- **F6 — Filtri attivi**: rispettare i flag `active` (workspace, dominio, base, file, chunk) durante la ricerca.
- **F7 — Test**: pipeline completa con mock per strategie LLM; test specifici per `identity` pass-through; test hybrid con fallback BM25.

## Test

| Test | Cosa verifica |
|------|---------------|
| Dense retrieval | Chunk rilevanti per query similarity |
| Sparse fallback BM25 | Modello solo-dense → BM25 attivato, warning loggato |
| Hybrid RRF | Risultati fusi da dense + sparse |
| Identity pass-through | Input = output identico per tutti i componenti |
| Multi-query espansione | N query generate, risultati unificati |
| Cross-encoder rerank | Ordine modificato dal reranker |
| Lazy/eager filtering | Flag `active` rispettati |

---

*Ultimo aggiornamento: 21 luglio 2026*