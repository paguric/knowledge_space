# Fase 1B — Ricerca sui documenti processati

Pipeline di retrieval su vettori Chroma (dense/sparse/hybrid) con pre-retrieval (espansione testuale) e post-retrieval (reranking, compression). Opera sui chunk già indicizzati dalla Fase 1A. **Nessuna dipendenza dal grafo Neo4j**: la ricerca è puramente vettoriale su Chroma, con fallback BM25 per sparse retrieval.

Al termine di questa sottofase `knowledge-base` sa:
- Espandere la query utente in più varianti testuali tramite stadi componibili (multi_query, step_back, least_to_most)
- Cambiare la rappresentazione della query per il retrieval (original / HyDE)
- Cercare chunk simili via dense/sparse/hybrid retrieval su Chroma (con fallback BM25 automatico)
- Riordinare i risultati con metodi rule-based (relevance, MMR), cross-encoder o LLM
- Comprimere i risultati con llm_chain_extract o selective_context (arXiv:2310.06201)
- Rispettare i flag `active` durante la ricerca

> Per la collocazione di questa sottofase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md). Per la specifica dettagliata della pipeline: [80-retrieval.md](80-retrieval.md). La Fase 1A (ingestione e indicizzazione) deve essere completata prima di iniziare questa sottofase.

---

### Step 8: Pipeline di retrieval (pre / retrieval / post)

Implementare secondo la specifica [80-retrieval.md](80-retrieval.md). La pipeline ha tre step sequenziali: pre-retrieval → retrieval → post-retrieval. Ogni step accetta `method = "identity"` come no-op esplicito.

#### Pre-retrieval (espansione testuale)

- [ ] Interfaccia `QueryRewriter` (Protocol) con input `list[str]` e output `list[str]` e registry (`knowledge_base/strategies/retrieval/pre_retrieval.py`).
- [ ] Orchestrazione stadi concatenati: ogni stadio riceve le query del precedente e produce nuove varianti. Config a `stages = [{method = ..., params = ...}, ...]`.
- [ ] Strategy `identity`: pass-through, nessuna espansione.
- [ ] Strategy `multi_query`: per ogni query genera N sotto-query via LLM (diverse prospettive). Parametro `n_queries = 3`, `model` (vedi [75-llm.md](75-llm.md) per modelli supportati).
- [ ] Strategy `step_back`: per ogni query genera una domanda astratta/concettuale via LLM. Restituisce `[q_originale, q_astratta]`. Parametro `model`.
- [ ] Strategy `least_to_most`: decompone la query in sottoproblemi via LLM e restituisce una query per ciascuno + la query originale. L'agente downstream si organizza coi documenti ricevuti (nessuna risoluzione sequenziale qui). Parametro `model`.
- [ ] Test con LLM mock (vedi [75-llm.md §Test](75-llm.md#test)): identity pass-through; multi_query/step_back/least_to_most generano output coerenti; composizione di due stadi produce più varianti.

#### Retrieval (dense / sparse / hybrid)

- [ ] Interfaccia `RetrievalStrategy` e registry (`knowledge_base/strategies/retrieval/retrieval.py`).
- [ ] Strategy `dense`: similarity search su Chroma via vettori (`collection.query`). `top_k` e `distance_metric` configurabili.
- [ ] Strategy `sparse`: BM25-like. Se il modello di embedding usato per la base espone `embed_sparse` (es. `BAAI/bge-m3`), usato nativamente. Altrimenti, **fallback automatico**: il `KnowledgeBaseManager` monta un BM25 esterno (`rank_bm25`) sul testo grezzo dei chunk della base, con un warning di log all'avvio.
- [ ] Strategy `sparse`: BM25-like. Se il modello di embedding usato per la base espone `embed_sparse` (es. `BAAI/bge-m3`), usato nativamente. Altrimenti, **fallback automatico**: il `KnowledgeBaseManager` monta un BM25 esterno (`rank_bm25`) sul testo grezzo dei chunk della base, con un warning di log all'avvio.
- [ ] Strategy `hybrid`: ensemble dense + sparse. Fusione controllata da `fusion`:
  - `rrf` (default): Reciprocal Rank Fusion — robusto, nessun peso da configurare.
  - `weighted_sum`: somma pesata di score normalizzati (min-max in [0,1]). Pesi `dense_weight` e `sparse_weight` (default 0.5/0.5, validati a somma 1.0).
- [ ] **Query mode** (`retrieval.query_mode`): `"original"` (default, embedding diretto con `embed_query()`) o `"hyde"` (genera documento ipotetico via LLM e lo embedda con `embed_documents()`). Se `"hyde"`, richiede `hyde_model` nel TOML. Ortogonale al pre-retrieval: gli stadi di espansione producono N varianti testuali, poi ciascuna viene embeddata secondo `query_mode`.
- [ ] Rispetto flag `active` durante la ricerca.
- [ ] Test: dense restituisce chunk con embedding simile; sparse recupera per match testuale; hybrid combina entrambi; fallback BM25 funziona senza modello native-sparse; HyDE genera documento ipotetico e lo embedda correttamente.

#### Post-retrieval (reranking / compression)

- [ ] Interfaccia `Reranker` e `Compressor` (Protocol) e registry (`knowledge_base/strategies/retrieval/post_retrieval.py`).
- [ ] **Rule-based reranker**:
  - [ ] Reranker `identity`: pass-through, nessun riordino.
  - [ ] Reranker `relevance`: riordina per score del retriever (discendente). Dopo hybrid fusion riapplica l'ordinamento per score fuso.
  - [ ] Reranker `mmr`: Maximum Marginal Relevance, bilancia rilevanza e diversità tramite embedding dei chunk. Parametro `mmr_lambda` (default 0.7).
- [ ] **Model-based reranker**:
  - [ ] Reranker `cross_encoder`: modello BERT-like (es. `BAAI/bge-reranker-v2-m3`, `cross-encoder/ms-marco-MiniLM-L6-v2`) per riordinare i top-N con punteggio di rilevanza più accurato. Richiede `reranker_model`.
- [ ] **LLM-based reranker**:
  - [ ] Reranker `llm`: LLM valuta la rilevanza di ogni chunk rispetto alla query (costoso, ma più flessibile). Richiede `reranker_model` (vedi [75-llm.md](75-llm.md)).
- [ ] **Compressor**:
  - [ ] Compressor `identity`: pass-through, nessuna compressione.
  - [ ] Compressor `llm_chain_extract`: LLM estrae/riassume i chunk in una risposta coerente. Richiede `compressor_model` (vedi [75-llm.md](75-llm.md)).
  - [ ] Compressor `selective_context`: comprime il contesto rimuovendo token a bassa self-information (arXiv:2310.06201). Richiede `compressor_model` e `compression_ratio` (es. 0.5 = 50%).
- [ ] Test: identity pass-through; relevance ordine corretto dopo hybrid; mmr introduce diversità; cross_encoder modifica l'ordine; llm rerank coerente col prompt; llm_chain_extract output più corto; selective_context rapporto rispettato.

#### Orchestrazione pipeline

- [ ] `SearchService` o metodo `search` su `KnowledgeBaseManager`: accetta una query + `BaseConfig` + `top_k`, esegue i tre step in sequenza.
- [ ] Ogni step può essere configurato per-base nel TOML (vedi [30-configuration.md](30-configuration.md) sezione `[pre_retrieval]`, `[retrieval]`, `[post_retrieval]`).
- [ ] Se un metodo richiede LLM ma nessun LLM è configurato → **fallback automatico a `identity`** con warning (la base è comunque funzionante in degrado).
- [ ] Integrazione con `AppContext` (Fase 1A): il `SearchService` riceve `KnowledgeBaseManager` e `llm_factory` dall'`AppContext`.

> L'integrazione LLM è definita in [75-llm.md](75-llm.md) (Step 6-bis, Fase 1A): `LLMStrategy` Protocol, registry, `llm_factory` in `AppContext`. Ogni componente sceglie il proprio modello nel TOML. In Fase 1B si usano i mock per i test; provider reali (OpenAI, Ollama) si aggiungono qui.

## Scelte consolidate per questa sottofase

| Aspetto | Scelta |
|---|---|
| Repository di retrieval | Chroma (vector store) + `rank_bm25` fallback per sparse |
| Metrica distanza dense | `cosine` (default) / `l2` / `ip`. Chroma restituisce distanza, normalizzata con min-max per confronto con BM25 |
| Espansione testuale | Stadi concatenati: `multi_query`, `step_back`, `least_to_most` |
| Query mode (retrieval) | `"original"` (embed_query) / `"hyde"` (documento ipotetico → embed_documents) |
| Fusione hybrid | RRF (default, nessun peso) + `weighted_sum` (min-max + peso esplicito) |
| LLM per pre/post | Ogni componente sceglie il proprio modello nel TOML (nessuna sezione `[llm]` globale). `LLMStrategy` definito in Step 6-bis ([75-llm.md](75-llm.md)). Fallback a `identity` se modello non specificato. |
| Reranking | Rule-based: `identity`, `relevance`, `mmr`. Model: `cross_encoder`. LLM: `llm` |
| Compressione | `identity`, `llm_chain_extract`, `selective_context` (arXiv:2310.06201) |
| Dipendenza da Fase 1A | Chroma popolato, `chunk_id`/`file_id` stabili, `content_hash` disponibile |

## Dipendenze con altre sottofasi

- **Dipende da**: Fase 1A (Chroma popolato, KnowledgeBaseManager funzionante).
- **Usata da**: Fase 1C (il search service vettoriale può essere usato come fallback per GraphRAG senza Neo4j).
- **Usata da**: Fase 3 (CLI) e Fase 4 (REST API + frontend) per rispondere a query utente.

---

*Ultimo aggiornamento: 21 luglio 2026*
