# Roadmap, scelte e rischi

## Fasi di implementazione

Il lavoro è diviso in **4 fasi**:

1. **Fase 1 — Logica di business completa**: tutta la logica di backend funzionante e testata (modelli, managers, configurazione, pipeline di ingestion/chunking/embedding/indicizzazione e retrieval). Al termine di questa fase `knowledge-base` è una libreria completa e testabile in isolamento.
2. **Fase 2 — Testing e validazione**: dataset sintetici e profili di configurazione predefiniti (ricercatore/legale/studente) per validare end-to-end la pipeline completa e confrontare le configurazioni.
3. **Fase 3 — MCP + CLI**: server MCP per interrogare i workspace e interfaccia a riga di comando. Entrambi si appoggiano ai manager già consolidati nella Fase 1.
4. **Fase 4 — REST + Frontend**: layer FastAPI sopra i manager e frontend React collegato alle API.

---

## Fase 1 — Logica di business completa

### Step 0: Modello di dominio e persistenza ibrida

Fondamenta su cui poggiano tutti gli altri step.

- [x] Definire modelli Pydantic in `knowledge_base/models.py`:
  - `ChunkRef`, `FileEntry`, `KnowledgeBase`, `Domain`, `Workspace`, `GlobalIndexData`, `WorkspaceConfigData`.
- [x] Creare `GlobalIndex` per caricare/salvare l'indice globale (path iniettabile, nessuna conoscenza di app/XDG).
- [x] Creare `WorkspaceConfig` per caricare/salvare la configurazione del workspace (path iniettabile).
- [x] Rimuovere le variabili globali dai nuovi moduli (legacy non ancora toccato).
- [x] Scrivere test di roundtrip JSON per `WorkspaceConfig` e `GlobalIndex` (16 test).

### Step 1: Workspace e sincronizzazione col filesystem

- [x] Creare `WorkspaceManager`:
  - `add(path)` / `remove(path)` / `list()`
  - `load(path)` → restituisce `Workspace`
  - `sync(workspace)` → allinea basi (cartelle) col filesystem
  - `set_last_workspace(path)` / `get_last_workspace()`
- [x] Integrare `watchdog` per sincronizzazione a runtime (`WorkspaceWatcher`, observer iniettabile).
- [x] Scrivere test per CRUD workspace e sincronizzazione FS (8 test).

### Step 2: Domini

- [x] Creare `DomainManager`:
  - `create(workspace, name, base_names)` / `delete(workspace, name)`
  - `auto_generate(workspace)` dalla struttura di cartelle (lvl1 + sottocartelle → dominio; foglie del sottoalbero → basi)
  - `activate(workspace, name)` / `deactivate(workspace, name)`
  - `add_base(workspace, domain, base)` / `remove_base(workspace, domain, base)`
- [x] Scrivere test per creazione, auto-generazione e flag `active` (10 test).

### Step 3: Configurazione delle basi (TOML)

Implementare la configurazione per-base come da [configuration.md](configuration.md): file TOML, cascata di default, strategy registry.

- [ ] Aggiungere `RuntimePaths` (Pydantic) in `knowledge-space` con path XDG e convenzioni `.knowledge-space/` del workspace.
- [ ] Definire `BaseConfig` (Pydantic) con sezioni `ingestion`, `chunking`, `embedding`.
- [ ] Implementare `BaseConfigLoader` con cascata: default hardcoded → `defaults.toml` del workspace → `bases/<base_name>.toml`.
- [ ] Leggere TOML con `tomllib` (stdlib Python 3.11+).
- [ ] Validare il TOML all'avvio: warning + fallback al default per valori non riconosciuti.
- [ ] Definire il **registry delle strategie** (pattern strategy/plugin) per ingestion, chunking, embedding.
- [ ] Scrivere test per: cascata di default, override, validazione, file mancanti.

### Step 4: Strategie di ingestion

Implementare diverse strategie di ingestion come plugin registrabili nel config TOML.

- [ ] Definire l'interfaccia `IngestionStrategy` (Protocol/ABC): `convert(source_path: Path) -> str`.
- [ ] Implementare strategy `docling` (già esistente, incapsulare).
- [ ] Implementare strategy `pypdf` (dipendenza leggera).
- [ ] Registrare le strategy nel registry.
- [ ] Scrivere test con file di esempio per ciascuna strategy (formati: PDF, Markdown, testo).

> **Da definire**: quali altre librerie di ingestion supportare (es. `unstructured`, `markitdown`, `textract`). Per la Fase 1 bastano `docling` + `pypdf`.

### Step 5: Strategie di chunking

Implementare diverse strategie di chunking come plugin.

- [ ] Definire l'interfaccia `ChunkingStrategy` (Protocol/ABC): `split(text: str) -> list[Chunk]`.
- [ ] Implementare strategy `fixed_size` (già esistente con `CharacterTextSplitter`).
- [ ] Implementare strategy `recursive` (langchain `RecursiveCharacterTextSplitter`).
- [ ] Implementare strategy `sentence` (split per frasi, es. `langchain_text_splitters`).
- [ ] Implementare strategy `markdown` (split rispettando la struttura Markdown, es. `MarkdownHeaderTextSplitter`).
- [ ] Registrare le strategy nel registry.
- [ ] Scrivere test per ciascuna strategy con testi di esempio.

> **Da definire**: parametri specifici di ciascuna strategy (chunk_size, overlap, separatori, ecc.) e come verranno passati dal `BaseConfig`.

### Step 6: Embedding configurabile per base

- [ ] Definire l'interfaccia `EmbeddingStrategy` (Protocol/ABC): `embed(texts: list[str]) -> list[list[float]]`.
- [ ] Implementare strategy `sentence-transformers` (già esistente, incapsulare) che accetta il nome del modello dal config.
- [ ] Implementare strategy `huggingface` (langchain `HuggingFaceEmbeddings`).
- [ ] **Supportare molteplici modelli di embedding** via registry; ogni strategia deve esporre metadati discoverable:
  - `model_name` (es. `BAAI/bge-m3`, `intfloat/multilingual-e5-small`, `Alibaba-NLP/gte-large-en-v1.5`).
  - `languages` (lista, es. `["en"]`, `["en", "it"]`, `["multilingual"]`).
  - `dim` (dimensione vettore).
  - `max_context_tokens` (lunghezza massima contesto, es. 512 per `all-mpnet-base-v2`, 8192 per `gte-large-en-v1.5` e `bge-m3`).
  - `license` (Apache 2.0, MIT, CC-BY-NC-4.0, …).
  - `requires_api` (bool; `False` per locali, `True` per OpenAI/Cohere).
- [ ] **Esposizione frontend (Fase 4)**: l'API REST e il frontend devono elencare i modelli registrati con i loro metadati, in particolare **quali lingue supportano** (italiano / inglese / multi) e la dimensione del contesto, così che l'utente possa scegliere consapevolmente il modello compatibile col proprio corpus.
- [ ] Garantire che ogni base usi il proprio modello di embedding (collection Chroma separata).
- [ ] Scrivere test di consistenza: embedding della stessa query con modelli diversi produce vettori di dimensioni diverse.

> **Da definire**: supporto per modelli locali vs API (es. `OpenAIEmbeddings`), caching degli embedding, device (CPU/GPU).

> **NOTA IMPORTANTE — dimensione del contesto** (da tenere in considerazione durante l'implementazione di Step 5 e 6): ogni modello di embedding ha un `max_context_tokens` (es. `all-mpnet-base-v2` = 384/512, `gte-large-en-v1.5` = 8192, `bge-m3` = 8192). Se un chunk troppo grande non può essere convertito dal modello, il manager deve **lanciare un errore esplicito** (non troncare silenziosamente). Si raccomanda di:
> - Aggiungere un validatore nel `KnowledgeBaseManager` (Step 7) che stima la lunghezza in token del chunk (es. via `tiktoken` per modelli EN, o tokenizer del modello stesso) PRIMA di invocare l'embedding.
> - L'errore deve includere: nome base, file, indice chunk, lunghezza token stimata, `max_context_tokens` del modello.
> - Opzionalmente, loggare un warning quando un chunk supera l'80% del `max_context_tokens` (soglia configurabile in `BaseConfig`).
> - Il chunking (Step 5) dovrebbe in heat prendere `max_context_tokens` dal `BaseConfig.embedding` per regolare `chunk_size` di conseguenza quando possibile, riducendo le probabilità di eccedere.

### Step 7: KnowledgeBaseManager e indicizzazione

Implementare la logica operativa sulle basi di conoscenza, orchestrando ingestion → chunking → embedding.

- [ ] Creare `KnowledgeBaseManager`:
  - `add(workspace, path)` / `remove(workspace, name)`
  - `add_file(kb, path)` → pipeline: ingestion → chunking → embedding → vector store
  - `remove_file(kb, path)` → rimozione da indice e vector store
  - `sync(kb)` → allinea file con filesystem (mtime check)
- [ ] Il manager legge `BaseConfig` (Step 3) per istanziare le strategy corrette.
- [ ] **Validazione lunghezza chunk vs `max_context_tokens`** dell'embedding (vedi nota Step 6): errore esplicito se un chunk eccede il limite del modello.
- [ ] Encapsulare Chroma/langchain nel manager (nessuna variabile globale).
- [ ] Salvataggio dei chunk su disco (opzionale/da rivalutare).
- [ ] Scrivere test per ingestion, rimozione, sync mtime, ricerca base, e **test che verifichi il lancio dell'errore quando un chunk eccede `max_context_tokens`**.

### Step 8: Pipeline di retrieval (pre / retrieval / post)

Implementare la pipeline di ricerca completa, configurabile via TOML per base. La pipeline ha **tre step sequenziali**: pre-retrieval → retrieval → post-retrieval. Ogni step accetta `method = "identity"` come **no-op esplicito** (i dati passano through, senza istanziare LLM/reranker): pipeline sempre omogenea, intento dell'utente dichiarato nel TOML. Utile per es. profilo `legal` dove le leggi non devono essere riassunte.

- [ ] **Pre-retrieval (query rewriting)** — sezione `[pre_retrieval]`:
  - Definire l'interfaccia `QueryRewriter` (Protocol/ABC): `rewrite(query: str) -> list[str]` (una query può generare sub-query).
  - Implementare strategy: `identity` (no-op, 1:1), `hyde` (Hypothetical Document Embeddings), `multi_query` (espansione con LLM in N sub-query).
  - Parametri strategy-specific in `params = {...}` (es. `multi_query` accetta `n_queries=3`, `llm=...`).
  - Registrare nel registry.
- [ ] **Retrieval** — sezione `[retrieval]`:
  - `method = "dense" | "sparse" | "hybrid"` — scelta esplicita utente.
  - Retrieval **dense**: similarity search sul vector store.
  - Retrieval **sparse**:
    - Se il modello embedding della base espone `embed_sparse` (es. `BAAI/bge-m3`), usarlo nativamente.
    - **Altrimenti fallback automatico a BM25 esterno** (`rank_bm25` sul testo grezzo dei chunk), con warning di log all'avvio.
  - Retrieval **hybrid**: ensemble di dense + sparse + fusione; `fusion = "rrf" | "weighted_sum"` (default `rrf`, robusto senza tuning pesi).
  - Rispettare i flag `active` (workspace, dominio, base, file, chunk) durante la ricerca.
  - `search(query, workspace?, domain?, kb?)` → restituisce chunk rilevanti con score.
- [ ] **Post-retrieval (rerank + compress)** — sezione `[post_retrieval]`:
  - `top_k = 10` — numero di risultati finali (applicato **ultimi**, dopo ogni altra elaborazione).
  - `reranker = "identity" | "cross_encoder" | "llm"` — riordino dei top-N; `reranker_model` opzionale (es. `BAAI/bge-reranker-v2-m3`).
  - `compressor = "identity" | "llm_chain_extract" | ...` — compression/sintesi dei contenuti passati al LLM.
  - Ordine fisso: **retrieve → rerank → compress** (l'LLM generatore vede solo ciò che esce dal compressor).
  - Definire due interfacce separate (`Reranker`, `Compressor`) perché rispondono a domande diverse ("quali sono i più rilevanti?" vs "quali contenuti passare al LLM?").
  - Implementare strategy: `identity` per entrambe (no-op), `cross_encoder` con model esterno, `llm_chain_extract` (langchain `LLMChainExtractor`).
  - Registrare nel registry.
- [ ] Estendere `BaseConfig` con sezioni `[pre_retrieval]`, `[retrieval]`, `[post_retrieval]`.
- [ ] Aggiungere dipendenza soft `rank_bm25` (BM25 fallback, puro Python).
- [ ] Validazione all'avvio: se `[retrieval].method` richiede sparse ma il modello embedding non lo supporta nativamente, montare BM25 fallback e loggare un warning (info ai fini di audit).
- [ ] Scrivere test per ciascuna fase della pipeline (con mock per le strategy LLM-based); test specifici per `identity` (no-op pass-through) e per hybrid con modello solo-dense (verifica del fallback BM25).

> **Da definire**: integrazione con LLM per query rewriting, reranking e compression (locale vs API), pesi della `weighted_sum`, supporto metadati di filtraggio al retrieval.

### Step 8-bis: Pipeline GraphRAG + edit-aware re-embedding

Costruire il grafo della conoscenza su Neo4j **riprendendo** la pipeline `neo4j-graphrag` a partire dal lexical graph, senza rifare ingestion/chunking/embedding (già calcolati da KS). Supportare l'aggiunta incrementale di documenti e l'edit dei chunk da parte dell'utente. Piano completo in [graph.md](graph.md).

- [ ] **F0 — Prerequisiti sull'ingest esistente**:
  - Spostare i chunk da `chunks_dir` globale a `<base>/.chunks/<file_stem>/<file_stem>_chunk_<i>.md`.
  - ID deterministico chunk `base::file::i` in Chroma e come `Neo4jNode.id`.
  - Estensione metadata Chroma (`chunk_index`, `base_name`, `file_name`, `edited`, `content_hash`, ...) + `collection.upsert` (no `add_documents(uuid4())`).
  - Watcher sorgente ignora i path che iniziano con `.` (`.chunks/`, `.knowledge-space/`).
  - Estensione modelli Pydantic (`ChunkRef`, `KnowledgeBase`, `WorkspaceConfigData`, `GraphConfigData`) — vedi [data-model.md](data-model.md).
  - Test di idempotenza: riesecuzione di `add_file` non duplica record Chroma né chunk su disco.
- [ ] **F1 — Pacchetto e dipendenze**: `neo4j-graphrag` + `neo4j` + extra `[nlp]` in `knowledge-base`; modulo `knowledge_base/graph/`; `graph.json` workspace + `[graph]` TOML per-base (vedi [configuration.md](configuration.md)).
- [ ] **F2 — `KSChunkLoader`**: componente custom che legge chunk da disco ed embedding da Chroma, espone `upsert_chunk` per edit-aware re-embedding.
- [ ] **F3 — Pipeline GraphRAG**: assemblaggio `KSChunkLoader -> schema (caricato da `schema.json` se esiste) -> LLMEntityRelationExtractor(create_lexical_graph=True) -> Neo4jWriter(MERGE)`.
- [ ] **F4 — Entity resolution incrementale**: `SpaCySemanticMatchResolver` default con `filter_query="WHERE NOT entity:Resolved"`, fallback a `exact` se extra `[nlp]` mancante.
- [ ] **F5 — ChunkWatcher (eager cascade)**: watcher su `.chunks/**/*.md` con debounce + hash check; su edit -> upsert Chroma + re-estrazione LLM mirata sul chunk; handling delete/rename.
- [ ] **F6 — Blocco cambio modello embedding**: errore se `[embedding].model` differisce da `embedding_model` registrato e collection non vuota.
- [ ] **F7 — Test di integrazione**: vedi [graph.md §13](graph.md).
- [ ] **F7-bis — Retrieval factory**: `RetrieverFactory.build(base_config, graph_config, driver, embedder, llm)` per istanziare uno qualsiasi dei retriever supportati (vector, vector_cypher, hybrid, hybrid_cypher, text2cypher, tools) in base a `[graph].retriever` (vedi [graph.md §14](graph.md)). Creazione indici Neo4j (vector + full-text) idempotente.
- [ ] **F8 — Documentazione**: `docs/graph.md` + aggiornamenti `data-model.md`/`configuration.md`/`architecture.md`/questo file.

**Scelte consolidate**:

| Aspetto | Scelta |
|---|---|
| Grafo Neo4j | Uno per workspace |
| Resume da | Lexical graph (delegato all'estrattore) + estrazione + risoluzione |
| Schema | Caricato da `schema.json` se esiste; estratto/costruito solo la prima volta |
| Resolver | Semantico (spaCy) come default, fallback exact, configurabile in `[graph].resolver` |
| Edit chunk | Auto re-embedding via watcher + eager cascade su grafo |
| Snapshot originale | Sì, in `.knowledge-space/snapshots/` per audit |
| Cambio modello emb. | Bloccato se collection non vuota |
| Retrieval | Configurabile `[graph].retriever` per-base (default `hybrid_cypher`); l'app istanzia solo il metodo scelto dall'utente |

---

## Fase 2 — Testing e validazione

Validare end-to-end la pipeline di business completa (Fase 1) tramite dataset sintetici e profili di configurazione predefiniti, prima di esporre il sistema tramite CLI/MCP/REST.

### Step 9: Dataset sintetici

I **formati supportati** in produzione (e quindi da coprire nei dataset) sono cinque:

1. **Paper accademici** (PDF a colonne, tabelle, formule, referenze, abstract).
2. **Testi legislativi** (PDF/TXT: normative, articoli, commi, lettere — es. GDPR, contratti).
3. **Libri di testo** (PDF lunghi a capitoli, multi-colonna, TOC, typografia uniforme).
4. **Slide PPTX** (presentazioni con titolo/bullet/tabelle/immagini).
5. **Appunti** (Markdown testuale, sintassi semplice, liste, codice breve).
6. **Corpo di mail in formato testuale** (TXT/`.eml`: thread, quote con `>`, mittente/soggetto/data).

> L'insieme è **chiuso**: qualsiasi formato non in questa lista non è supportato; il manager di ingestion deve rifiutarlo con un errore esplicito.

- [ ] Definire corpus di esempio in `tests/data/synthetic/` organizzati per ciascuno dei 6 formati sopra:
  - `papers/` — paper accademici realistici (o estratti da arXiv open access), in PDF.
  - `legal/` — estratti GDPR/contratti in PDF e TXT, con struttura articoli/commi.
  - `textbooks/` — PDF di libri di testo o sample chapters pubblici (multi-colonna, TOC).
  - `slides/` — file PPTX con slide testuali + bullet + una tabella.
  - `notes/` — file Markdown con titoli, liste, codice breve.
  - `emails/` — file `.txt`/`.eml` con thread di 2–3 messaggi (quote `>`, mittente, data).
- [ ] Variazioni linguistiche: per ciascun formato, includere campioni in **italiano** e in **inglese** (per testare la copertura linguistica degli embedding e validare che modelli solo-EN degradano su IT — vedi Step 6).
- [ ] Generare i file tramite script riproducibile (es. `tests/data/synthetic/build.py`) che usa template testo + piccole varianti, oppure scarica un sottoinsieme piccolo e open da fonti pubbliche (arXiv, EUR-Lex).
- [ ] Definire un set di **query golden** per ogni dominio, con **risposta attesa** (chunk id / snippet / keywords) per valutare recall e precision.
- [ ] Documentare la struttura del dataset e come rigenerarlo.

### Step 10: Profili di configurazione predefiniti

Definire configurazioni TOML default per scenari d'uso rappresentativi. I profili sono **punti di partenza** copiabili dall'utente, non logica hardcoded.

- [ ] **`researcher`** (paper accademici EN):
  - ingestion: `docling` — test set ufficiale di docling è esplicitamente paper arXiv ([arXiv:2408.09869](https://arxiv.org/abs/2408.09869)). Alt: `PyMuPDF4LLM` per pipeline veloci senza GPU.
  - chunking: `recursive` con `chunk_size` ~1200, overlap 200. Il recursive supera il semantic su paper accademici ([arXiv:2607.01852](https://arxiv.org/abs/2607.01852); [Chroma TR](https://www.trychroma.com/research/evaluating-chunking)). Markdown-aware opzionale (qualitativo).
  - embedding: `gte-large-en-v1.5` (MTEB 65.39, ctx 8192) — [HF card](https://huggingface.co/Alibaba-NLP/gte-large-en-v1.5). Alt: `bge-large-en-v1.5` (ctx 512, MTEB 64.23). ⚠️ Entrambi EN-only: non adatti a documenti italiani.
  - pre-retrieval: `multi_query` (espansione LLM) o `hyde`.
  - retrieval: `ensemble` (dense + sparse).
  - post-retrieval: `llm_chain_extract` (compressione contestualizzata).
- [ ] **`legal`** (testi legislativi/GDPR, multilingua IT+EN):
  - ingestion: `pdfplumber` + `pdfminer.six` — ❌ **fonte specifica assente**: la preferenza è inferita dalle capacità di coordinate/layout ([pdfplumber README](https://github.com/jsvine/pdfplumber)). Da validare nel dataset sintetico Step 9. Alt robusto: `docling` (OCR + tabelle + layout).
  - chunking: `markdown`/structure-aware + Parent-Child (chunk=articolo, parent=articolo intero). Il fixed-size causa **boundary fragmentation** su GDPR documentato in [SCAR, arXiv:2606.16661](https://arxiv.org/abs/2606.16661).
  - embedding: `BAAI/bge-m3` (multilingua 100+ lingue, ctx 8192, retrieval sparse+dense integrato tipo BM25 — utile per terminologia legale esatta) — [HF card](https://huggingface.co/BAAI/bge-m3), [paper arXiv:2402.03216](https://arxiv.org/pdf/2402.03216). Alt: `intfloat/multilingual-e5-large`.
  - pre-retrieval: `identity` (query già precisa dal legale).
  - retrieval: `dense` (top-k alto) + filtro metadati per articolo; opzionale ensemble con sparse (bge-m3 lo supporta nativamente).
  - post-retrieval: `identity` (serve il testo originale, no compressione).
- [ ] **`student`** (libri di testo, slide, appunti — italiano, leggero):
  - ingestion: `PyMuPDF4LLM` per PDF (multi-colonna, TOC, veloce — [PyMuPDF4LLM docs](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)) + `markitdown` per slide PPTX/EPUB ([markitdown](https://github.com/microsoft/markitdown)).
  - chunking: `Parent-Child` (genitore=sezione); alt `Late Chunking` se si dispone di embedding long-context ([arXiv:2409.04701](https://arxiv.org/abs/2409.04701), [Jina blog](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)). `fixed_size` 800/150 come fallback leggero.
  - embedding: `intfloat/multilingual-e5-small` (dim 384, ~470 MB, supporta IT — [HF card](https://huggingface.co/intfloat/multilingual-e5-small), Mr.TyDi MRR@10 64.4). Alt: `BAAI/bge-m3` su HW buono (più pesante ma migliore qualità e ctx 8192). ⚠️ `all-MiniLM-L6-v2` è solo-EN — NON adatto a documenti IT.
  - pre-retrieval: `identity`.
  - retrieval: `dense` top-k medio.
  - post-retrieval: `identity`.
- [ ] **`tecnico`** (documentazione markdown, codice, IT+EN):
  - ingestion: ingest diretta per markdown; `markitdown` per normalizzare sorgenti miste.
  - chunking: `MarkdownHeaderTextSplitter` + `Recursive` (code block mai spezzato — [Pinecone](https://www.pinecone.io/learn/chunking-strategies/)).
  - embedding: `BAAI/bge-m3` (multilingua + sparse retrieval preserva identificatori di codice "token weights similar to BM25" — [bge-m3 card](https://huggingface.co/BAAI/bge-m3)). Alt EN-only: `gte-large-en-v1.5`.
  - pre-retrieval: `identity`.
  - retrieval: `dense` + sparse ensemble.
  - post-retrieval: `identity`.
- [ ] Salvare i profili in `configs/profiles/<name>.toml` (cartella del repo, non del workspace).
- [ ] Documentare come applicare un profilo a un workspace (`defaults.toml` del workspace = copia del profilo).
- [ ] **Per ciascun profilo, documentare nel commento TOML quali lingue supporta l'embedding scelto** (EN / multilingua incl. IT / etc.) e `max_context_tokens`, così l'utente può scegliere consapevolmente (vedi Step 6 e requisito frontend Step 15).

##### Affidabilità delle evidenze per profilo

| Profilo | Ingestion | Chunking | Embedding |
|---|---|---|---|
| `researcher` | Alta (arXiv test set) | Alta (recursive > semantic confermato) | Alta (MTEB + ctx 8192) |
| `legal` | ❌ Bassa (fonte assente — da validare) | Alta (boundary fragmentation ✓ in SCAR) | Alta (SOTA MIRACL + IT + sparse) |
| `student` | Media (feature doc, no benchmark diretto) | Alta (Late Chunking ✓) | Media (IT coperto ma non score Mr.TyDi) |
| `tecnico` | Bassa (qualitativa) | Media (Pinecone qualitativo) | Media (estrapolazione) |

#### Scelta del retriever per profilo (GraphRAG)

Per abbinare la tipologia di retrieval sul grafo a ciascun profilo, usiamo come riferimento la classificazione dei **tipi di domanda** e delle **pipeline atomiche** di GraphRAG:

> **Fonte ( Memgraph Docs ):** *Atomic Pipelines — Question and Pipeline Types*
> <https://memgraph.com/docs/ai-ecosystem/graph-rag/atomic-pipelines#question-and-pipeline-types>
>
> La documentazione categorizza le domande (specifiche, esplorative, di sintesi, globali…) e, per ciascuna, suggerisce la pipeline atomica più adatta (vector retriever, text2cypher, hybrid, hybrid+cypher, tools, ecc.). Useremo questa classificazione per rispondere, ad esempio, alla domanda: **"quale tipologia di retrieval sul grafo utilizzare per lo studente?"** individuando il tipo di domanda predominante nello scenario "studente" e leggendo la pipeline corrispondente dal reference.

> **Nota ( Memgraph vs Neo4j ):** sebbene il reference citato sia tratto dalla documentazione di **Memgraph**, il progetto utilizzerà **Neo4j** come grafico, coerentemente con quanto previsto negli [piani GraphRAG](graph.md). La classificazione dei tipi di domanda/pipeline è indipendente dalla backend : la mappatura similarity_retriever ↔ nome Memgraph va semplicemente ricondotta ai retriever equivalenti della libreria `neo4j-graphrag` (vedi `RetrieverFactory` in [graph.md §14](graph.md)). In altre parole, Memgraph è il solo reference concettuale per la progettazione dei profili .

#### Mapping preliminare profilo ↔ pipeline atomica

Da confermare una volta implementati i retriever della Fase 1 (Step 8-bis):

- [ ] **`researcher`** — question type prevalente: **exploratory / synthesis** → pipeline atomica candidate: `hybrid_cypher` (dense+sparse con augment di dati dal grafo) o `tools` se servono more-than-retrieval capabilities.
- [ ] **`legal`** — question type prevalente: **specific / lookup** → pipeline atomica candidate: `vector_cypher` (filtri strutturali per articolo/sezione) o `text2cypher` se la domanda è già ben formalmente esprimibile come pattern di grafo.
- [ ] **`student`** — question type prevalente: **specific** (definizioni, confronti diretti) → pipeline atomica candidate: `vector` (puro, leggero) o `vector_cypher` se lo studente filtra per esame/anno. Preferire il più economico compatibile con la recall attesa.

### Step 11: Test end-to-end e benchmark

- [ ] Test end-to-end (in `packages/knowledge-base/tests/e2e/`):
  - Per ciascun profilo (researcher/legal/studente), eseguire la pipeline completa (ingest → chunk → embed → retrieve) sul dataset sintetico corrispondente.
  - Verificare che i chunk rilevanti per le query golden vengano recuperati (recall ≥ soglia).
  - Verificare che i flag `active` vengano rispettati (disattivare un dominio → nessun risultato da quelle basi).
- [ ] Benchmark comparativo:
  - Confrontare i 3 profili su metriche qualitative (recall@k, MRR, latenza ingestion, latenza query).
  - Produrre un report markdown con tabelle (es. `docs/benchmark.md`).
- [ ] **Strategy LLM-based**: usare stub/mock per query rewriting e compression nei test CI; opzionale un test manuale con LLM reale (skip di default).

> **Da definire**: modello LLM da usare nei test con LLM reale (locale come `llama-cpp` o API come OpenAI/Anthropic),soglie di recall target, peso delle metriche nel benchmark.

---

## Fase 3 — MCP + CLI

Esporre i manager consolidati nella Fase 1 tramite MCP e CLI.

### Step 12: CLI con Typer

- [ ] Aggiungere `typer` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/cli.py`.
- [ ] Implementare comandi per workspace, domini, basi, file, ricerca.
- [ ] La CLI **legge** ma non scrive i file TOML (vedi [configuration.md](configuration.md)).
- [ ] Scrivere test di integrazione per i comandi CLI.

### Step 13: Server MCP

- [ ] Aggiungere `mcp` alle dipendenze di `mcp-server`.
- [ ] Rimuovere la dipendenza `mcp-server` da `knowledge-space`; aggiungere `knowledge-base` come dipendenza di `mcp-server`.
- [ ] Implementare `mcp_server/server.py` con trasporto stdio.
- [ ] Implementare i tool MCP (`list_workspaces`, `add_workspace`, `search`, `list_domains`, `activate_domain`, etc.).
- [ ] Scrivere test per MCP.

---

## Fase 4 — REST + Frontend

### Step 14: Backend REST

Thin layer FastAPI sopra i manager già testati.

- [ ] Aggiungere `fastapi` e `uvicorn` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/api/app.py` con `create_app`.
- [ ] Implementare router `health`, `workspaces`, `domains`, `bases`, `files`, `search`, `config`.
- [ ] Aggiungere CORS.
- [ ] Scrivere test per l'API.
- [ ] **Endpoint `/api/v1/models/embeddings`**: elenca i modelli di embedding registrati con i loro metadati (`model_name`, `languages`, `dim`, `max_context_tokens`, `license`, `requires_api`). Il frontend lo usa per mostrare all'utente le opzioni.

### Step 15: Frontend React / GUI

- [ ] Collegare il frontend alle API REST.
- [ ] Permettere modifica dei file TOML dall'interfaccia (quando prevista da configuration.md).
- [ ] Visualizzare struttura ad albero (workspace → domini → basi → file → chunk).
- [ ] **Selettore modello di embedding**: quando l'utente configura una base, mostrare l'elenco dei modelli disponibili (da `/api/v1/models/embeddings`) e **evidenziare esplicitamente quali lingue supporta ciascun modello** (es. badge "🇮🇹 IT", "🇬🇧 EN", "🌍 multilingua"). Questo aiuta l'utente a scegliere un modello compatibile col proprio corpus e a evitare errori (es. modelli solo-EN su documenti italiani).
- [ ] **Avviso contesto**: mostrare `max_context_tokens` del modello e confrontarlo con `chunk_size` della strategia di chunking scelta, avvisando l'utente se configura un `chunk_size` che rischia di eccedere il limite (vedi nota Step 6 — lancio errore al runtime).

### Step 16: Polish e documentazione

- [ ] Rimuovere codice legacy e variabili globali residue (`base.py`, `workspace.py`, `domain.py` vecchi).
- [ ] Rimuovere entrypoint CLI da `knowledge-base`.
- [ ] Aggiornare i `README.md` di tutti i pacchetti.
- [ ] Aggiornare `AGENTS.md` con le convenzioni del progetto.
- [ ] Aggiungere test end-to-end.
- [ ] Valutare la versione minima di Python: `>=3.14` è molto restrittiva. Considerare `>=3.11` o `>=3.12`.

---

## Considerazioni e rischi

### Concurrency

- L'indice globale (`GlobalIndex`) e i `config.json` non sono concurrent-safe. Se il server REST gira con più worker, l'accesso deve essere sincronizzato.
- **Chroma** PersistentClient è generalmente sicuro per un singolo processo; più processi contemporanei possono creare conflitti.
- **watchdog** usa thread. Per i test, permettere di iniettare un observer fittizio.

### Sicurezza

- Non esporre `hf_key` o altri secrets via API.
- Validare i path passati dagli utenti per evitare path traversal.
- Se il backend è esposto in rete, aggiungere autenticazione.

### Compatibilità Python

- `requires-python = ">=3.14"` è molto avanzato. Valutare `>=3.11` o `>=3.12`.

### Esecuzione simultanea REST e MCP

- La CLI può esporre due comandi separati: `serve` e `mcp`.
- In futuro, MCP in modalità SSE sullo stesso server FastAPI.

### Strategie LLM-dipendenti

- Query rewriting (HyDE, multi-query) e compression richiedono un LLM. Per la Fase 1 usare mock/stub nei test; l'integrazione reale con un LLM (locale o API) sarà decisione di configurazione.
- `EmbeddingStrategy` per base può richiedere modelli diversi caricati in memoria contemporaneamente: valutare uso di RAM e lazy loading.

## Riepilogo delle scelte consigliate

| Aspetto | Scelta consigliata |
|---------|-------------------|
| Monorepo | Mantenere workspace uv con 3 pacchetti |
| Persistenza | Ibrida: indice globale + file `config.json` per workspace |
| Configurazione basi | TOML per base + `defaults.toml` (cascata) |
| Modelli di dominio | Pydantic (`Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef`) |
| Logica operativa | Classi manager/service separate dai modelli di dominio |
| Strategy pattern | Registry per ingestion, chunking, embedding, pre/post-retrieval |
| Profili di config | `researcher` / `legal` / `student` in `configs/profiles/` |
| Testing e2e | Dataset sintetici + query golden in `tests/data/synthetic/` |
| Backend REST | FastAPI + Pydantic + uvicorn |
| Server MCP | SDK ufficiale `mcp`, trasporto stdio (poi SSE) |
| CLI | Typer |
| Configurazione app | `RuntimePaths` + `UserSettings` + `AppConfig`, passaggio esplicito |
| Persistenza | Repository pattern a medio termine |
| Iniezione dipendenze | `AppContext` a livello di applicazione |
| Versione Python | Valutare `>=3.11` o `>=3.12` al posto di `>=3.14` |

---

*Ultimo aggiornamento: 21 luglio 2026*