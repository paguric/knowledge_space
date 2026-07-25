# Pipeline di retrieval

> **Stato:** non iniziato | **Step:** 8 | **Fase:** 1B | **Aggiornato:** 22 luglio 2026

## Panoramica

Pipeline di ricerca completa, configurabile via TOML per base. Tre step sequenziali: pre-retrieval (espansione testuale) → retrieval (dense/sparse/hybrid) → post-retrieval (rerank + compress). Ogni step accetta `method = "identity"` come no-op esplicito. Ogni componente LLM-dipendente specifica il proprio modello (vedi [75-llm.md](75-llm.md)).

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Pipeline | 3 step: pre-retrieval → retrieval → post-retrieval |
| No-op esplicito | `method = "identity"` per ogni step |
| Pre-retrieval | `identity`, `multi_query`, `step_back`, `least_to_most` (stadi concatenati) |
| Retrieval | `dense`, `sparse` (BM25 fallback), `hybrid` (rrf / weighted_sum) |
| Query mode | `original` (embed_query) / `hyde` (documento ipotetico) |
| Reranker | `identity`, `relevance`, `mmr`, `cross_encoder`, `llm` |
| Compressor | `identity`, `llm_chain_extract`, `selective_context` |
| Fallback LLM | identity + warning se modello non specificato |

## Dettagli

### Flusso generale

```
query → [pre-retrieval] → [retrieval] → [post-retrieval] → chunk rilevanti
         (query rewrite)  (search)      (rerank + compress)
```

Ordine fisso: **retrieve → rerank → compress**.

### Pre-retrieval: espansione testuale

Sezione `[pre_retrieval]`. Espande la query in più varianti testuali prima del retrieval. Stadi concatenati: ognuno riceve le query del precedente e produce varianti.

```toml
[pre_retrieval]
stages = [{ method = "identity" }]
```

**Interfaccia `QueryRewriter`:**

```python
class QueryRewriter(Protocol):
    name: str
    def rewrite(self, queries: list[str], **params) -> list[str]:
        """Prende N query, restituisce M query riscritte/ampliate."""
        ...
```

**Strategie:**

| Method | Descrizione | Parametri | Richiede LLM |
|--------|-------------|-----------|:---:|
| `identity` | No-op | — | no |
| `multi_query` | Genera N sotto-query (diverse prospettive) | `n_queries: int = 3`, `model: str` | sì |
| `step_back` | Genera domanda astratta/concettuale | `model: str` | sì |
| `least_to_most` | Decompone in sottoproblemi | `model: str` | sì |

Se `model` è omesso e `requires_llm = True` → fallback a `identity` con warning.

**Componibilità** — stadi multipli si concatenano:

```toml
[pre_retrieval]
stages = [
  { method = "step_back",   model = "openai/gpt-4o-mini" },
  { method = "multi_query", model = "openai/gpt-4o-mini", params = { n_queries = 2 } },
]
```

Flusso: `query → [q_orig, q_astratta] → [q1a, q1b, q2a, q2b]`.

### Retrieval

Sezione `[retrieval]`. Ricerca su vector store (dense) e/o indice testuale (sparse).

```toml
[retrieval]
method = "dense"              # "dense" | "sparse" | "hybrid"
fusion = "rrf"                # "rrf" | "weighted_sum"
distance_metric = "cosine"    # "cosine" | "l2" | "ip"
expansion = "none"            # "none" | "parent_child" (in pausa)
query_mode = "original"       # "original" | "hyde"
```

**Distance metric:**

| Metrica | Cosa misura | Range score | Note |
|---------|-------------|-------------|------|
| `cosine` (default) | cos(∠vettori) | [0, 2] (Chroma: `1 - cosine`) | Standard per embedding |
| `l2` | distanza euclidea | [0, +∞) | Sensibile alla magnitudine |
| `ip` | prodotto scalare | (-∞, +∞) | Equivale a cosine se normalizzati |

**Normalizzazione per `weighted_sum`:** score dense e sparse vengono normalizzati in [0, 1] con min-max scaling prima della fusione. Pesi devono sommare a 1.0.

**Query mode:**

| Mode | Descrizione | Richiede LLM |
|------|-------------|:---:|
| `original` | Embedda la query con `embed_query()` | no |
| `hyde` | Genera documento ipotetico via LLM, embedda con `embed_documents()` | sì (`hyde_model`) |

```toml
# Esempio step-back + HyDE
[pre_retrieval]
stages = [{ method = "step_back", model = "openai/gpt-4o-mini" }]

[retrieval]
method = "dense"
query_mode = "hyde"
hyde_model = "openai/gpt-4o-mini"
```

**Interfaccia `RetrievalStrategy`:**

```python
class RetrievalStrategy(Protocol):
    name: str
    def search(self, query: str, top_k: int = 10, **filters) -> list[dict]:
        """Restituisce chunk rilevanti con score."""
        ...
```

**Metodi di retrieval:**

- **Dense**: similarity search su Chroma (sempre disponibile).
- **Sparse**: BM25-like. Modello con sparse nativo → usato diretramente; altrimenti fallback a `rank_bm25` (puro Python) con warning.
- **Hybrid**: ensemble dense + sparse. Fusione: `rrf` (default, robusto) o `weighted_sum` (richiede pesi).

**Parent-Child expansion (in pausa):** pattern Small-to-Big. `[retrieval].expansion = "parent_child"`. Il retrieval matcha sui child ma restituisce il parent collegato. Vedi [60-chunking.md](60-chunking.md).

### Post-retrieval: rerank e compress

Sezione `[post_retrieval]`.

```toml
[post_retrieval]
top_k = 10
reranker = "identity"          # "identity" | "relevance" | "mmr" | "cross_encoder" | "llm"
compressor = "identity"        # "identity" | "llm_chain_extract" | "selective_context"
```

**Interfacce:**

```python
class Reranker(Protocol):
    name: str
    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]: ...

class Compressor(Protocol):
    name: str
    def compress(self, query: str, chunks: list[dict]) -> str: ...
```

**Reranker:**

| Method | Tipo | Descrizione | Parametri |
|--------|------|-------------|-----------|
| `identity` | rule-based | No-op | — |
| `relevance` | rule-based | Riordina per score originale | — |
| `mmr` | rule-based | Maximum Marginal Relevance (rilevanza + diversità) | `mmr_lambda: float = 0.7` |
| `cross_encoder` | model-based | Cross-encoder (es. `BAAI/bge-reranker-v2-m3`) | `reranker_model` |
| `llm` | LLM-based | LLM valuta rilevanza | `reranker_model` |

**Compressor:**

| Method | Descrizione | Richiede LLM |
|--------|-------------|:---:|
| `identity` | No-op | no |
| `llm_chain_extract` | LLM estrae/riassume | sì (`compressor_model`) |
| `selective_context` | Comprime rimuovendo token a bassa self-information (arXiv:2310.06201) | sì (`compressor_model`) |

```toml
# Esempio selective_context
[post_retrieval]
compressor = "selective_context"
compression_ratio = 0.5
compressor_model = "openai/gpt-4o-mini"
```

### Registry delle strategie

```python
{
    # Pre-retrieval
    "identity":      {"type": "query_rewriter", "requires_llm": False},
    "multi_query":   {"type": "query_rewriter", "requires_llm": True, "params_schema": {"n_queries": int, "model": str}},
    "step_back":     {"type": "query_rewriter", "requires_llm": True, "params_schema": {"model": str}},
    "least_to_most": {"type": "query_rewriter", "requires_llm": True, "params_schema": {"model": str}},
    # Retrieval
    "dense":  {"type": "retriever", "requires_embedder": True},
    "sparse": {"type": "retriever", "can_fallback_bm25": True},
    "hybrid": {"type": "retriever", "requires_embedder": True, "can_fallback_bm25": True},
    # Query mode
    "query_mode/original": {"type": "query_mode", "requires_llm": False},
    "query_mode/hyde":     {"type": "query_mode", "requires_llm": True, "params_schema": {"model": str}},
    # Post-retrieval — reranker
    "identity":      {"type": "reranker", "requires_llm": False},
    "relevance":     {"type": "reranker", "requires_llm": False},
    "mmr":           {"type": "reranker", "requires_llm": False, "params_schema": {"mmr_lambda": float}},
    "cross_encoder": {"type": "reranker", "requires_model": True, "params_schema": {"reranker_model": str}},
    "llm":           {"type": "reranker", "requires_llm": True, "params_schema": {"reranker_model": str}},
    # Post-retrieval — compressor
    "llm_chain_extract":  {"type": "compressor", "requires_llm": True, "params_schema": {"compressor_model": str}},
    "selective_context":  {"type": "compressor", "requires_llm": True, "params_schema": {"compressor_model": str, "compression_ratio": float}},
}
```

### Configurazione TOML completa — profili d'esempio

**Profilo consulente (nessuna manipolazione):**

```toml
[pre_retrieval]
stages = [{ method = "identity" }]

[retrieval]
method = "dense"
query_mode = "original"

[post_retrieval]
top_k = 10
reranker = "identity"
compressor = "identity"
```

**Profilo ricercatore (pipeline avanzata):**

```toml
[pre_retrieval]
stages = [
  { method = "step_back",   model = "openai/gpt-4o-mini" },
  { method = "multi_query", model = "openai/gpt-4o-mini", params = { n_queries = 2 } },
]

[retrieval]
method = "hybrid"
fusion = "rrf"
query_mode = "hyde"
hyde_model = "openai/gpt-4o-mini"

[post_retrieval]
top_k = 10
reranker = "cross_encoder"
reranker_model = "BAAI/bge-reranker-v2-m3"
compressor = "llm_chain_extract"
compressor_model = "openai/gpt-4o-mini"
```

### Test

| Test | Cosa verifica |
|------|---------------|
| Dense retrieval | Chunk rilevanti per query similarity |
| Sparse fallback BM25 | Modello solo-dense → BM25 attivato, warning loggato |
| Hybrid RRF | Risultati fusi da dense + sparse |
| Identity pass-through | Input = output identico per tutti i componenti |
| Multi-query espansione | N query generate, risultati unificati |
| Step-back espansione | Query astratta + originale restituite |
| HyDE retrieval | Documento ipotetico generato ed embeddato |
| MMR rerank | Diversità introdotta, nessun chunk duplicato |
| Cross-encoder rerank | Ordine modificato, punteggi più accurati |
| Selective context compress | Output più corto, rapporto rispettato |
| Filtri attivi | Flag `active` rispettati |

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 7 (KnowledgeBaseManager), Step 6-bis (LLMStrategy) | Step 13 (CLI `search`), Step 15 (REST `search`) |
