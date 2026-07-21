# Fase 2 — Testing e validazione

Validare end-to-end la pipeline di business completa (Fase 1) tramite dataset sintetici e profili di configurazione predefiniti, prima di esporre il sistema tramite CLI/MCP/REST.

> Per la collocazione di questa fase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md).

---

### Step 9: Dataset sintetici

I **formati supportati** in produzione (e quindi da coprire nei dataset) sono cinque:

1. **Paper accademici** (PDF a colonne, tabelle, formule, referenze, abstract).
2. **Testi legislativi** (PDF/TXT: normative, articoli, commi, lettere — es. GDPR, contratti).
3. **Preventivi / contratti** (DOCX: documenti Office con tabelle, intestazioni, paragrafi — per profilo consulente).
4. **Libri di testo** (PDF lunghi a capitoli, multi-colonna, TOC, typografia uniforme).
5. **Slide PPTX** (presentazioni con titolo/bullet/tabelle/immagini).
6. **Appunti** (Markdown testuale, sintassi semplice, liste, codice breve).

> L'insieme è **chiuso**: qualsiasi formato non in questa lista non è supportato; il manager di ingestion deve rifiutarlo con un errore esplicito.

- [ ] Definire corpus di esempio in `tests/data/synthetic/` organizzati per ciascuno dei 6 formati sopra:
  - `papers/` — paper accademici realistici (o estratti da arXiv open access), in PDF.
  - `legal/` — estratti GDPR/contratti in PDF e TXT, con struttura articoli/commi.
  - `preventivi/` — documenti DOCX con tabelle, intestazioni, paragrafi.
  - `textbooks/` — PDF di libri di testo o sample chapters pubblici (multi-colonna, TOC).
  - `slides/` — file PPTX con slide testuali + bullet + una tabella.
  - `notes/` — file Markdown con titoli, liste, codice breve.
- [ ] Variazioni linguistiche: per ciascun formato, includere campioni in **italiano** e in **inglese** (per testare la copertura linguistica degli embedding e validare che modelli solo-EN degradano su IT — vedi Step 6).
- [ ] Generare i file tramite script riproducibile (es. `tests/data/synthetic/build.py`) che usa template testo + piccole varianti, oppure scarica un sottoinsieme piccolo e open da fonti pubbliche (arXiv, EUR-Lex).
- [ ] Definire un set di **query golden** per ogni dominio, con **risposta attesa** (chunk id / snippet / keywords) per valutare recall e precision.
- [ ] Documentare la struttura del dataset e come rigenerarlo.

### Step 10: Profili di configurazione predefiniti

Definire configurazioni TOML default per scenari d'uso rappresentativi. I profili sono **punti di partenza** copiabili dall'utente, non logica hardcoded.

- [ ] **`ricercatore`** (paper accademici EN):
  - ingestion: `docling` — test set ufficiale di docling è esplicitamente paper arXiv ([arXiv:2408.09869](https://arxiv.org/abs/2408.09869)).
  - chunking: `recursive` con `chunk_size` ~1200, overlap 200. Il recursive supera il semantic su paper accademici ([arXiv:2607.01852](https://arxiv.org/abs/2607.01852); [Chroma TR](https://www.trychroma.com/research/evaluating-chunking)). Markdown-aware opzionale (qualitativo).
  - embedding: `gte-large-en-v1.5` (MTEB 65.39, ctx 8192) — [HF card](https://huggingface.co/Alibaba-NLP/gte-large-en-v1.5). Alt: `bge-large-en-v1.5` (ctx 512, MTEB 64.23). ⚠️ Entrambi EN-only: non adatti a documenti italiani.
  - pre-retrieval: `multi_query` (espansione LLM) o `hyde`.
  - retrieval: `ensemble` (dense + sparse).
  - post-retrieval: `llm_chain_extract` (compressione contestualizzata).
- [ ] **`consulente`** (testi normativi, GDPR, contratti, preventivi — multilingua IT+EN):
  - ingestion: `pymupdf4llm` per PDF (veloce, multi-colonna, TOC preservato — [docs](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)). `docling` per DOCX (preventivi, contratti) e PDF complessi con OCR/tabelle.
  - chunking: `markdown`/structure-aware (chunk=articolo; header `§/Art.` riconosciuti). **Future** (in pausa, Step 8): `parent_child` come `[retrieval].expansion` (child=comma, parent=articolo intero). Il fixed-size causa **boundary fragmentation** su GDPR documentato in [SCAR, arXiv:2606.16661](https://arxiv.org/abs/2606.16661).
  - embedding: `BAAI/bge-m3` (multilingua 100+ lingue, ctx 8192, retrieval sparse+dense integrato tipo BM25 — utile per terminologia legale esatta) — [HF card](https://huggingface.co/BAAI/bge-m3), [paper arXiv:2402.03216](https://arxiv.org/pdf/2402.03216). Alt: `intfloat/multilingual-e5-large`.
  - pre-retrieval: `identity` (query già precisa dal consulente).
  - retrieval: `dense` (top-k alto) + filtro metadati per articolo; opzionale ensemble con sparse (bge-m3 lo supporta nativamente).
  - post-retrieval: `identity` (serve il testo originale, no compressione).
- [ ] **`studente`** (slide PPTX, appunti MD, testi brevi — italiano, leggero):
  - ingestion: `markitdown` — supporta PPTX, PDF semplici, MD, DOCX, HTML ([markitdown](https://github.com/microsoft/markitdown)).
  - chunking: `recursive` con `chunk_size` ~800, overlap 150 (leggero e robusto). **Future** (in pausa, Step 5/6): `parent_child` (genitore=sezione) come `[retrieval].expansion`, oppure `late_chunking` in `[embedding].mode` se si dispone di embedding long-context ([arXiv:2409.04701](https://arxiv.org/abs/2409.04701), [Jina blog](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)).
  - embedding: `intfloat/multilingual-e5-small` (dim 384, ~470 MB, supporta IT — [HF card](https://huggingface.co/intfloat/multilingual-e5-small), Mr.TyDi MRR@10 64.4). Alt: `BAAI/bge-m3` su HW buono (più pesante ma migliore qualità e ctx 8192). ⚠️ `all-MiniLM-L6-v2` è solo-EN — NON adatto a documenti IT.
  - pre-retrieval: `identity`.
  - retrieval: `dense` top-k medio.
  - post-retrieval: `identity`.
- [ ] Salvare i profili in `configs/profiles/<name>.toml` (cartella del repo, non del workspace).
- [ ] Documentare come applicare un profilo a un workspace (`defaults.toml` del workspace = copia del profilo).
- [ ] **Per ciascun profilo, documentare nel commento TOML quali lingue supporta l'embedding scelto** (EN / multilingua incl. IT / etc.) e `max_context_tokens`, così l'utente può scegliere consapevolmente (vedi Step 6 e requisito frontend Step 15).

##### Affidabilità delle evidenze per profilo

| Profilo | Ingestion | Chunking | Embedding |
|---|---|---|---|---|
| `ricercatore` | Alta (arXiv test set) | Alta (recursive > semantic confermato) | Alta (MTEB + ctx 8192) |
| `consulente` | Media (feature doc, no benchmark diretto) | Alta (boundary fragmentation ✓ in SCAR) | Alta (SOTA MIRACL + IT + sparse) |
| `studente` | Media (feature doc, no benchmark diretto) | Media (recursive standard) | Media (IT coperto ma non score Mr.TyDi) |

#### Scelta del retriever per profilo (GraphRAG)

Per abbinare la tipologia di retrieval sul grafo a ciascun profilo, usiamo come riferimento la classificazione dei **tipi di domanda** e delle **pipeline atomiche** di GraphRAG:

> **Fonte ( Memgraph Docs ):** *Atomic Pipelines — Question and Pipeline Types*
> <https://memgraph.com/docs/ai-ecosystem/graph-rag/atomic-pipelines#question-and-pipeline-types>
>
> La documentazione categorizza le domande (specifiche, esplorative, di sintesi, globali…) e, per ciascuna, suggerisce la pipeline atomica più adatta (vector retriever, text2cypher, hybrid, hybrid+cypher, tools, ecc.). Useremo questa classificazione per rispondere, ad esempio, alla domanda: **"quale tipologia di retrieval sul grafo utilizzare per lo studente?"** individuando il tipo di domanda predominante nello scenario "studente" e leggendo la pipeline corrispondente dal reference.

> **Nota ( Memgraph vs Neo4j ):** sebbene il reference citato sia tratto dalla documentazione di **Memgraph**, il progetto utilizzerà **Neo4j** come grafico, coerentemente con quanto previsto negli [piani GraphRAG](40-graph.md). La classificazione dei tipi di domanda/pipeline è indipendente dalla backend : la mappatura similarity_retriever ↔ nome Memgraph va semplicemente ricondotta ai retriever equivalenti della libreria `neo4j-graphrag` (vedi `RetrieverFactory` in [40-graph.md §14](40-graph.md)). In altre parole, Memgraph è il solo reference concettuale per la progettazione dei profili .

#### Mapping preliminare profilo ↔ pipeline atomica

Da confermare una volta implementati i retriever della Fase 1 (Step 8-bis):

- [ ] **`ricercatore`** — question type prevalente: **exploratory / synthesis** → pipeline atomica candidate: `hybrid_cypher` (dense+sparse con augment di dati dal grafo) o `tools` se servono more-than-retrieval capabilities.
- [ ] **`consulente`** — question type prevalente: **specific / lookup** → pipeline atomica candidate: `vector_cypher` (filtri strutturali per articolo/sezione) o `text2cypher` se la domanda è già ben formalmente esprimibile come pattern di grafo.
- [ ] **`studente`** — question type prevalente: **specific** (definizioni, confronti diretti) → pipeline atomica candidate: `vector` (puro, leggero) o `vector_cypher` se lo studente filtra per esame/anno. Preferire il più economico compatibile con la recall attesa.

> **Nota — `configs/profiles/` da ridefinire**: la collocazione `configs/profiles/<name>.toml` (nella radice del progetto) non è definitiva. Alternative da valutare in Fase 2:
> - `<workspace>/.knowledge-space/profiles/<name>.toml` (per-workspace, segue layout di `.knowledge-space/`)
> - `~/.config/knowledge-space/profiles/<name>.toml` (system-wide, riutilizzabile tra workspace)
> - Sezioni incorporate in `defaults.toml` (es. `[profile.ricercatore]`)
> - Repository Git esterno di profili condivisi (community-driven)
>
> **Comandi CLI profili** (`profiles list`, `profile apply`, ...) sono progettati e implementati in Fase 2, non in Fase 1. `95-cli.md` li elenca come "da definire in Fase 2".

### Step 11: Test end-to-end e benchmark

- [ ] Test end-to-end (in `packages/knowledge-base/tests/e2e/`):
  - Per ciascun profilo (ricercatore/consulente/studente), eseguire la pipeline completa (ingest → chunk → embed → retrieve) sul dataset sintetico corrispondente.
  - Verificare che i chunk rilevanti per le query golden vengano recuperati (recall ≥ soglia).
  - Verificare che i flag `active` vengano rispettati (disattivare un dominio → nessun risultato da quelle basi).
- [ ] Benchmark comparativo:
  - Confrontare i 3 profili su metriche qualitative (recall@k, MRR, latenza ingestion, latenza query).
  - Produrre un report markdown con tabelle (es. `docs/benchmark.md`).
- [ ] **Strategy LLM-based**: usare stub/mock per query rewriting e compression nei test CI; opzionale un test manuale con LLM reale (skip di default).

> **Da definire**: modello LLM da usare nei test con LLM reale (locale come `llama-cpp` o API come OpenAI/Anthropic),soglie di recall target, peso delle metriche nel benchmark.

---

*Ultimo aggiornamento: 21 luglio 2026*