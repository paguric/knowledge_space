# Pipeline di retrieval

## Obiettivo

Implementare la pipeline di ricerca completa, configurabile via TOML per base. La pipeline ha **tre step sequenziali**: pre-retrieval → retrieval → post-retrieval. Ogni step accetta `method = "identity"` come **no-op esplicito** (i dati passano through, senza istanziare LLM/reranker). Questo mantiene la pipeline sempre omogenea: l'intento dell'utente è dichiarato nel TOML, non dedotto dall'assenza di configurazione.

```
query → [pre-retrieval] → [retrieval] → [post-retrieval] → chunk rilevanti
         (query rewrite)  (search)      (rerank + compress)
```

Orderine fisso: **retrieve → rerank → compress** (l'LLM generatore vede solo ciò che esce dal compressor).

## Pre-retrieval: espansione testuale

Sezione `[pre_retrieval]`. Espande la query dell'utente in più varianti testuali prima del retrieval, per migliorare la recall. Gli stadi si concatenano: ognuno riceve le query prodotte dallo stadio precedente e produce nuove varianti.

```toml
[pre_retrieval]
stages = [
  { method = "identity" },
]
```

### Interfaccia `QueryRewriter`

Ogni stadio implementa la stessa interfaccia: prende N query, restituisce M query.

```python
class QueryRewriter(Protocol):
    name: str
    def rewrite(self, queries: list[str], **params) -> list[str]:
        """Prende N query, restituisce M query riscritte/ampliate."""
        ...
```

### Strategie

| Method | Descrizione | Parametri | Richiede LLM |
|--------|-------------|-----------|:---:|
| `identity` | No-op: restituisce le query in ingresso così come sono. | — | no |
| `multi_query` | Per ogni query genera N sotto-query (diverse prospettive) con LLM. | `n_queries: int = 3` | sì |
| `step_back` | Per ogni query genera una domanda astratta/concettuale (primo principio) con LLM. Restituisce `[q_originale, q_astratta]`. | — | sì |
| `least_to_most` | Decompone la query in sottoproblemi con LLM e restituisce una query per ciascuno + la query originale. Non risolve sequenzialmente: è l'agente downstream che si organizza coi documenti ricevuti. | — | sì |

### Componibilità

Stadi multipli si concatenano. Esempio — step-back + multi-query su ogni variante:

```toml
[pre_retrieval]
stages = [
  { method = "step_back" },
  { method = "multi_query", params = { n_queries = 2 } },
]
```

Flusso: `query originale → [q_orig, q_astratta] → [q1a, q1b, q2a, q2b]`. Ogni variante viene poi passata al retrieval.

## Retrieval

Sezione `[retrieval]`. Esegue la ricerca vera e propria sul vector store (dense) e/o indice testuale (sparse).

```toml
[retrieval]
method = "dense"              # "dense" | "sparse" | "hybrid"
fusion = "rrf"                # "rrf" (default, robusto) | "weighted_sum" (richiede pesi)
distance_metric = "cosine"    # "cosine" | "l2" | "ip"
expansion = "none"            # "none" | "parent_child" (in pausa)
query_mode = "original"       # "original" | "hyde"
```

### Distance metric

Controlla la metrica usata da Chroma per la ricerca **dense**. La scelta impatta gli score raw e la qualità del retrieval.

| Metrica | Cosa misura | Range score | Note |
|---------|-------------|-------------|------|
| `cosine` (default) | Similarità coseno: coseno dell'angolo tra due vettori. | [-1, 1] (Chroma restituisce `1 - cosine` → [0, 2], dove 0 = identico) | Standard per embedding. Ignora la magnitudine dei vettori. Chroma usa `1 - cosine` internamente (distanza). |
| `l2` | Distanza euclidea: distanza geometrica tra due punti. | [0, +∞), 0 = identico | Sensibile alla magnitudine. Utile se gli embedding hanno lunghezze informative. |
| `ip` | Prodotto scalare: `a · b`. | (-∞, +∞), più alto = più simile | Equivale a cosine se i vettori sono normalizzati a lunghezza 1. Più veloce di cosine. |

### Normalizzazione per `weighted_sum`

Quando `fusion = "weighted_sum"` (solo hybrid), gli score raw di dense e sparse sono su scale diverse e non confrontabili:

- **Dense**: dipende da `distance_metric`. Es. con `cosine` Chroma restituisce `1 - cosine` ([0, 2], 0 = massima similarità). Con `l2` restituisce distanza euclidea ([0, +∞)).
- **Sparse** (BM25): score non normalizzato, ~0–20+ a seconda della collezione.

Prima della fusione entrambe le liste vengono normalizzate in [0, 1] con min-max scaling (`(score - min) / (max - min)`), dove 1 = massima rilevanza. Invertendo il verso per metriche dove score basso = migliore (cosine, l2). Poi si applica:

```
final_score = dense_weight * normalized_dense + sparse_weight * normalized_sparse
```

I pesi sono validati al caricamento del TOML: `dense_weight + sparse_weight` deve fare 1.0.

### Query mode

`query_mode` controlla **come** la query viene vettorizzata prima della ricerca, ortogonalmente al pre-retrieval e al metodo di retrieval.

| Mode | Descrizione | Richiede LLM |
|------|-------------|:---:|
| `original` | Embedda la query così come arriva dal pre-retrieval usando `embed_query()`. | no |
| `hyde` | Hypothetical Document Embeddings: per ogni query genera un documento ipotetico via LLM, lo embedda con `embed_documents()` (stessa funzione usata per i chunk), e usa quel vettore per la ricerca. La similarità coseno è calcolata nello stesso spazio dei chunk. | sì |

HyDE è ortogonale all'espansione testuale: il pre-retrieval produce N varianti testuali, poi il retrieval embedda ciascuna secondo `query_mode`. Esempio — step-back + HyDE:

```toml
[pre_retrieval]
stages = [{ method = "step_back" }]

[retrieval]
method = "dense"
query_mode = "hyde"
```

Flusso: `query → pre-retrieval → [q_orig, q_astratta] → HyDE su ciascuna → 2 ipotetici documenti → 2 embedding → retrieve → merge risultati`.

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

| Fusion | Descrizione | Config |
|--------|-------------|--------|
| `rrf` (default) | Reciprocal Rank Fusion. Robusto, non richiede tuning di pesi. | — |
| `weighted_sum` | Somma pesata di score normalizzati (min-max). Richiede pesi espliciti. Vedi § [Normalizzazione per weighted_sum](#normalizzazione-per-weighted_sum). | `dense_weight`, `sparse_weight` (default 0.5/0.5, devono sommare a 1.0) |

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
    # Pre-retrieval (espansione testuale)
    "identity": {"type": "query_rewriter", "requires_llm": False, "params_schema": {}},
    "multi_query": {"type": "query_rewriter", "requires_llm": True, "params_schema": {"n_queries": int}},
    "step_back": {"type": "query_rewriter", "requires_llm": True, "params_schema": {}},
    "least_to_most": {"type": "query_rewriter", "requires_llm": True, "params_schema": {}},
    # Retrieval
    "dense": {"type": "retriever", "requires_embedder": True, "requires_sparse_model": False},
    "sparse": {"type": "retriever", "requires_embedder": False, "can_fallback_bm25": True},
    "hybrid": {"type": "retriever", "requires_embedder": True, "can_fallback_bm25": True},
    # Query mode (retrieval)
    "query_mode/original": {"type": "query_mode", "requires_llm": False},
    "query_mode/hyde": {"type": "query_mode", "requires_llm": True},
    # Post-retrieval
    "cross_encoder": {"type": "reranker", "requires_model": True},
    "llm": {"type": "reranker", "requires_llm": True},
    "llm_chain_extract": {"type": "compressor", "requires_llm": True},
}
```

## Configurazione TOML completa (esempi)

### Profilo consulente (nessuna manipolazione)

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

### Profilo ricercatore (pipeline avanzata)

```toml
[pre_retrieval]
stages = [
  { method = "step_back" },
  { method = "multi_query", params = { n_queries = 2 } },
]

[retrieval]
method = "hybrid"
fusion = "rrf"
query_mode = "hyde"

[post_retrieval]
top_k = 10
reranker = "cross_encoder"
reranker_model = "BAAI/bge-reranker-v2-m3"
compressor = "llm_chain_extract"
```

## Fasi di implementazione

- **F0 — Interfacce e registry**: definire `QueryRewriter` (con input `list[str]`, output `list[str]`), `RetrievalStrategy`, `Reranker`, `Compressor` (Protocol). Registry separati per ciascuno.
- **F1 — Identity per tutti**: implementare `identity` per pre/post-retrieval e `dense` per retrieval. Pipeline completa minimale funzionante.
- **F2 — Sparse retrieval**: BM25 fallback con `rank_bm25`. Test su modello solo-dense (es. `all-mpnet-base-v2`) che verifica il warning + fallback.
- **F3 — Hybrid retrieval**: dense + sparse + `rrf` / `weighted_sum`.
- **F4 — Pre-retrieval: espansione testuale**: `multi_query`, `step_back`, `least_to_most` (mock LLM nei test). Orchestrazione stadi concatenati.
- **F5 — HyDE**: `retrieval.query_mode = "hyde"`. Generazione documento ipotetico + `embed_documents()` invece di `embed_query()`.
- **F6 — Post-retrieval**: `cross_encoder` e `llm_chain_extract`.
- **F7 — Filtri attivi**: rispettare i flag `active` (workspace, dominio, base, file, chunk) durante la ricerca.
- **F8 — Test**: pipeline completa con mock per strategie LLM; test specifici per `identity` pass-through; test hybrid con fallback BM25; test composizione stadi; test HyDE.

## Test

| Test | Cosa verifica |
|------|---------------|
| Dense retrieval | Chunk rilevanti per query similarity |
| Sparse fallback BM25 | Modello solo-dense → BM25 attivato, warning loggato |
| Hybrid RRF | Risultati fusi da dense + sparse |
| Identity pass-through | Input = output identico per tutti i componenti |
| Multi-query espansione | N query generate, risultati unificati |
| Step-back espansione | Query astratta + originale restituite |
| Least-to-most decomposizione | Sottoproblemi estratti dalla query |
| Composizione stadi | Due stadi concatenati producono più varianti |
| HyDE retrieval | Documento ipotetico generato ed embeddato |
| Cross-encoder rerank | Ordine modificato dal reranker |
| Lazy/eager filtering | Flag `active` rispettati |

---

*Ultimo aggiornamento: 21 luglio 2026*