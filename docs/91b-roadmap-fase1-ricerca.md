# Fase 1B — Ricerca sui documenti processati

Pipeline di retrieval su vettori Chroma (dense/sparse/hybrid) con pre-retrieval (query rewriting) e post-retrieval (reranking, compression). Opera sui chunk già indicizzati dalla Fase 1A. **Nessuna dipendenza dal grafo Neo4j**: la ricerca è puramente vettoriale su Chroma, con fallback BM25 per sparse retrieval.

Al termine di questa sottofase `knowledge-base` sa:
- Riscrivere la query utente (identità, HyDE, multi-query)
- Cercare chunk simili via dense/sparse/hybrid retrieval su Chroma (con fallback BM25 automatico)
- Riordinare e comprimere i risultati (identity, cross_encoder reranker, llm_chain_extract compressor)
- Rispettare i flag `active` durante la ricerca

> Per la collocazione di questa sottofase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md). Per la specifica dettagliata della pipeline: [80-retrieval.md](80-retrieval.md). La Fase 1A (ingestione e indicizzazione) deve essere completata prima di iniziare questa sottofase.

---

### Step 8: Pipeline di retrieval (pre / retrieval / post)

Implementare secondo la specifica [80-retrieval.md](80-retrieval.md). La pipeline ha tre step sequenziali: pre-retrieval → retrieval → post-retrieval. Ogni step accetta `method = "identity"` come no-op esplicito.

#### Pre-retrieval (query rewriting)

- [ ] Interfaccia `QueryRewriter` (Protocol) e registry (`knowledge_base/strategies/retrieval/pre_retrieval.py`).
- [ ] Strategy `identity`: pass-through, nessuna riscrittura.
- [ ] Strategy `hyde`: `HypotheticalDocumentEmbedder` — genera un documento fittizio via LLM, ne calcola l'embedding, lo usa per la ricerca.
- [ ] Strategy `multi_query`: genera N varianti della query via LLM, recupera chunk per ciascuna, unisce i risultati (dedup).
- [ ] Test con LLM mock: query identity restituisce la stessa query; HyDE/multi_query generano output coerenti.

#### Retrieval (dense / sparse / hybrid)

- [ ] Interfaccia `RetrievalStrategy` e registry (`knowledge_base/strategies/retrieval/retrieval.py`).
- [ ] Strategy `dense`: similarity search su Chroma via vettori (`collection.query`). `top_k` configurabile.
- [ ] Strategy `sparse`: BM25-like. Se il modello di embedding usato per la base espone `embed_sparse` (es. `BAAI/bge-m3`), usato nativamente. Altrimenti, **fallback automatico**: il `KnowledgeBaseManager` monta un BM25 esterno (`rank_bm25`) sul testo grezzo dei chunk della base, con un warning di log all'avvio.
- [ ] Strategy `hybrid`: ensemble dense + sparse. Fusione controllata da `fusion`:
  - `rrf` (default): Reciprocal Rank Fusion — robusto, nessun peso da configurare.
  - `weighted_sum`: media ponderata dei punteggi normalizzati (richiede pesi configurabili in TOML, da definire).
- [ ] Rispetto flag `active` durante la ricerca.
- [ ] Test: dense restituisce chunk con embedding simile; sparse recupera per match testuale; hybrid combina entrambi; fallback BM25 funziona senza modello native-sparse.

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

> **Da definire**: integrazione LLM per query rewriting, reranking e compression (locale vs API), pesi della `weighted_sum`, supporto metadati di filtraggio al retrieval.

## Scelte consolidate per questa sottofase

| Aspetto | Scelta |
|---|---|
| Repository di retrieval | Chroma (vector store) + `rank_bm25` fallback per sparse |
| Fusione hybrid | RRF (default, nessun peso) + `weighted_sum` opzionale |
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
