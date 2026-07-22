# Fase 1B — Ricerca sui documenti processati

Pipeline di retrieval su vettori Chroma (dense/sparse/hybrid) con pre-retrieval (espansione testuale) e post-retrieval (reranking, compression). Opera sui chunk già indicizzati dalla Fase 1A. **Nessuna dipendenza dal grafo Neo4j**: la ricerca è puramente vettoriale su Chroma, con fallback BM25 per sparse retrieval.

Al termine di questa sottofase `knowledge-base` sa:
- Espandere la query utente in più varianti testuali tramite stadi componibili (multi_query, step_back, least_to_most)
- Cambiare la rappresentazione della query per il retrieval (original / HyDE)
- Cercare chunk simili via dense/sparse/hybrid retrieval su Chroma (con fallback BM25 automatico)
- Riordinare e comprimere i risultati (identity, cross_encoder reranker, llm_chain_extract compressor)
- Rispettare i flag `active` durante la ricerca

> Per la collocazione di questa sottofase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md). Per la specifica dettagliata della pipeline: [80-retrieval.md](80-retrieval.md). La Fase 1A (ingestione e indicizzazione) deve essere completata prima di iniziare questa sottofase.

---

### Step 8: Pipeline di retrieval (pre / retrieval / post)

Implementare secondo la specifica [80-retrieval.md](80-retrieval.md). La pipeline ha tre step sequenziali: pre-retrieval → retrieval → post-retrieval. Ogni step accetta `method = "identity"` come no-op esplicito.

#### Pre-retrieval (espansione testuale)

- [ ] Interfaccia `QueryRewriter` (Protocol) con input `list[str]` e output `list[str]` e registry (`knowledge_base/strategies/retrieval/pre_retrieval.py`).
- [ ] Orchestrazione stadi concatenati: ogni stadio riceve le query del precedente e produce nuove varianti. Config a `stages = [{method = ..., params = ...}, ...]`.
- [ ] Strategy `identity`: pass-through, nessuna espansione.
- [ ] Strategy `multi_query`: per ogni query genera N sotto-query via LLM (diverse prospettive). Parametro `n_queries = 3`.
- [ ] Strategy `step_back`: per ogni query genera una domanda astratta/concettuale via LLM. Restituisce `[q_originale, q_astratta]`.
- [ ] Strategy `least_to_most`: decompone la query in sottoproblemi via LLM e restituisce una query per ciascuno + la query originale. L'agente downstream si organizza coi documenti ricevuti (nessuna risoluzione sequenziale qui).
- [ ] Test con LLM mock: identity pass-through; multi_query/step_back/least_to_most generano output coerenti; composizione di due stadi produce più varianti.

#### Retrieval (dense / sparse / hybrid)

- [ ] Interfaccia `RetrievalStrategy` e registry (`knowledge_base/strategies/retrieval/retrieval.py`).
- [ ] Strategy `dense`: similarity search su Chroma via vettori (`collection.query`). `top_k` configurabile.
- [ ] Strategy `sparse`: BM25-like. Se il modello di embedding usato per la base espone `embed_sparse` (es. `BAAI/bge-m3`), usato nativamente. Altrimenti, **fallback automatico**: il `KnowledgeBaseManager` monta un BM25 esterno (`rank_bm25`) sul testo grezzo dei chunk della base, con un warning di log all'avvio.
- [ ] Strategy `hybrid`: ensemble dense + sparse. Fusione controllata da `fusion`:
  - `rrf` (default): Reciprocal Rank Fusion — robusto, nessun peso da configurare.
  - `weighted_sum`: somma pesata di score normalizzati (min-max in [0,1]). Pesi `dense_weight` e `sparse_weight` (default 0.5/0.5, validati a somma 1.0).
- [ ] **Query mode** (`retrieval.query_mode`): `"original"` (default, embedding diretto con `embed_query()`) o `"hyde"` (genera documento ipotetico via LLM e lo embedda con `embed_documents()`). Ortogonale al pre-retrieval: gli stadi di espansione producono N varianti testuali, poi ciascuna viene embeddata secondo `query_mode`.
- [ ] Rispetto flag `active` durante la ricerca.
- [ ] Test: dense restituisce chunk con embedding simile; sparse recupera per match testuale; hybrid combina entrambi; fallback BM25 funziona senza modello native-sparse; HyDE genera documento ipotetico e lo embedda correttamente.

#### Post-retrieval (reranking / compression)

- [ ] Interfaccia `Reranker` e `Compressor` (Protocol) e registry (`knowledge_base/strategies/retrieval/post_retrieval.py`).
- [ ] Reranker `identity`: pass-through, nessun riordino.
- [ ] Reranker `cross_encoder`: modello BERT-like (es. `BAAI/bge-reranker-v2-m3`) per riordinare i top-N con punteggio di rilevanza più accurato della cosine similarity. Richiede modello caricato.
- [ ] Reranker `llm`: LLM valuta la rilevanza di ogni chunk rispetto alla query (costoso, ma più flessibile).
- [ ] Compressor `identity`: pass-through, nessuna compressione.
- [ ] Compressor `llm_chain_extract`: LLM estrae/riassume i chunk in una risposta coerente.
- [ ] Test: identity pass-through; cross_encoder modifica l'ordine dei risultati rispetto alla similarity; llm_chain_extract produce output più corto.

#### Orchestrazione pipeline

- [ ] `SearchService` o metodo `search` su `KnowledgeBaseManager`: accetta una query + `BaseConfig` + `top_k`, esegue i tre step in sequenza.
- [ ] Ogni step può essere configurato per-base nel TOML (vedi [30-configuration.md](30-configuration.md) sezione `[pre_retrieval]`, `[retrieval]`, `[post_retrieval]`).
- [ ] Se un metodo richiede LLM ma nessun LLM è configurato → **fallback automatico a `identity`** con warning (la base è comunque funzionante in degrado).
- [ ] Integrazione con `AppContext` (Fase 1A): il `SearchService` riceve `KnowledgeBaseManager` e `llm_factory` dall'`AppContext`.

> **Da definire**: integrazione LLM per query rewriting, reranking e compression (locale vs API), supporto metadati di filtraggio al retrieval.

## Scelte consolidate per questa sottofase

| Aspetto | Scelta |
|---|---|
| Repository di retrieval | Chroma (vector store) + `rank_bm25` fallback per sparse |
| Espansione testuale | Stadi concatenati: `multi_query`, `step_back`, `least_to_most` |
| Query mode (retrieval) | `"original"` (embed_query) / `"hyde"` (documento ipotetico → embed_documents) |
| Fusione hybrid | RRF (default, nessun peso) + `weighted_sum` (min-max + peso esplicito) |
| LLM per pre/post | Configurabile per-base; fallback a `identity` se LLM non disponibile |
| Reranking | Identity (default), cross_encoder (locale), LLM (API) |
| Compressione | Identity (default), llm_chain_extract (LLM) |
| Dipendenza da Fase 1A | Chroma popolato, `chunk_id`/`file_id` stabili, `content_hash` disponibile |

## Dipendenze con altre sottofasi

- **Dipende da**: Fase 1A (Chroma popolato, KnowledgeBaseManager funzionante).
- **Usata da**: Fase 1C (il search service vettoriale può essere usato come fallback per GraphRAG senza Neo4j).
- **Usata da**: Fase 3 (CLI) e Fase 4 (REST API + frontend) per rispondere a query utente.

---

*Ultimo aggiornamento: 21 luglio 2026*
