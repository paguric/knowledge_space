# Gestione della configurazione

## Stato attuale e problemi

- `settings.py` calcola i path XDG come costanti globali.
- `config.py` gestisce un file JSON con le preferenze utente (es. `hf_key`).
- `knowledge_space/main.py` chiama `setup()` e imposta **variabili globali** dentro `knowledge_base.base`, `knowledge_base.domain`, `knowledge_base.workspace`.
- I moduli di `knowledge-base` leggono queste variabili globali.

### Problemi

1. Test difficili: i test devono resettare manualmente le variabili globali.
2. Non thread-safe.
3. `knowledge-base` non è riutilizzabile in modo isolato.
4. Inversione di controllo: la libreria dipende da come il chiamante imposta le globali.
5. La configurazione di ingestion/chunking/embedding è hardcoded nel codice.

---

## Stato vs configurazione

Conviene tenere separati due concetti distinti:

| | Stato | Configurazione |
|---|------|----------------|
| Cosa | domini, basi, file, chunk, flag `active`, mtime | ingestion, chunking, embedding, parametri |
| Cambia spesso? | Sì, a runtime | No, raramente |
| Chi lo scrive | il programma | l'utente (a mano) |
| Formato | JSON (machine-friendly) | TOML (human-friendly, con commenti) |

- Lo **stato** del workspace vive in `<workspace>/.knowledge-space/config.json` (vedi [02-data-model.md](02-data-model.md)).
- La **configurazione** di ogni base vive in **TOML**, un file per base.

---

## Configurazione delle basi di conoscenza

### Filesystem

La struttura completa del filesystem (workspace, basi, chunk, graph) vive qui. La pipeline GraphRAG fa riferimento a questo layout — vedi anche [04-graph.md](04-graph.md) per le convenzioni specifiche del grafo.

```
<base_path>/                          # base = cartella foglia (watch_dir sorgente)
├── documento.pdf                      # file sorgente dell'utente
├── appunti.md
└── .chunks/                           # dotfolder, dati di proprietà dell'utente
    └── documento/
        ├── documento_chunk_0.md       # chunk editabili dall'utente
        ├── documento_chunk_1.md
        └── ...

<workspace>/.knowledge-space/
├── config.json                        # stato (albero Workspace -> Domain -> Base -> File -> Chunk)
├── defaults.toml                      # default per tutte le basi del workspace
├── bases/
│   ├── test_kb1.toml                  # configurazione specifica della base test_kb1
│   └── test_kb2.toml                  # configurazione specifica della base test_kb2
├── snapshots/                         # originazione pre-edit per audit
│   └── <base>/<file_stem>/<file_stem>_chunk_<i>.orig.md
├── schema.json                        # schema del grafo (caricato, vedi 04-graph.md §6-bis)
└── graph/                             # stato e connessione del grafo workspace
    └── graph.json                     # bolt_uri, database, embedding_model, schema ref
```

Regole:
- I chunk sono file markdown **plain**, editabili. L'utente "possiede" i propri dati.
- `.chunks/` è dentro la base (così si sposta con la base), ignorato dal watcher sorgente (vedi [04-graph.md](04-graph.md) F0.4).
- `graph.json` appartiene al workspace (un grafo per workspace), ma la **configurazione del comportamento** (schema, `on_chunk_edit`, `resolver`) è in `[graph]` del `BaseConfig` per-base — vedi [04-graph.md](04-graph.md).
- `<workspace>/.knowledge-space/defaults.toml` → default di tutto il workspace.
- `<workspace>/.knowledge-space/bases/<base_name>.toml` → configurazione specifica di una base.

Se una base non ha il proprio `.toml`, usa i default del workspace. Se non esiste `defaults.toml`, usa i default hardcoded del programma.

### Esempio di `defaults.toml`

```toml
# Default per tutte le basi del workspace

[ingestion]
library = "docling"
# params = {}

[chunking]
method = "fixed_size"
chunk_size = 1000
chunk_overlap = 200
separator = "\n\n"

[embedding]
model = "sentence-transformers/all-mpnet-base-v2"
# device = "cpu"

[graph]
# Configurazione del grafo della conoscenza (vedi docs/04-graph.md).
# I parametri di connessione al DB (bolt_uri, credenziali) sono a livello
# workspace in <workspace>/.knowledge-space/graph/graph.json, perché il
# grafo è uno per workspace; qui restano solo i comportamenti per-base.
schema = "manuale"          # "manuale" | "EXTRACTED" | "FREE"
resolver = "semantic"      # "semantic" (default, extra [nlp]) | "exact" | "fuzzy" (extra [fuzzy-matching]) | "none"
on_chunk_edit = "eager"    # "eager" (default, ri-estrazione LLM) | "lazy" (solo embedding)
chunk_embedding_property = "embedding"   # nome della proprietà vettore nel nodo Chunk

# Node/relationship types + patterns. Ignorati se schema = "EXTRACTED" o "FREE".
# Si possono anche materializzare in <workspace>/.knowledge-space/schema.json
# (vedi docs/04-graph.md §6-bis: caricato, non ricreato).
node_types = ["Person", "Organization", "Concept"]
relationship_types = ["WORKS_FOR", "RELATED_TO"]
patterns = [
    ["Person", "WORKS_FOR", "Organization"],
    ["Concept", "RELATED_TO", "Concept"],
]

# --- Retrieval (fase di ricerca, vedi docs/04-graph.md §14) ---
# Metodo di ricerca GraphRAG usato dall'app per le query su questa base.
# L'utente può specificare uno qualsiasi tra quelli supportati da
# neo4j-graphrag; l'app istanzia il retriever corrispondente.
retriever = "hybrid_cypher"   # vedi tabella in docs/04-graph.md §14
top_k = 5                     # numero di risultati (default del retriever)
# Nome del vector index Neo4j (Topic/Chunk) usato dai retriever vettoriali.
vector_index = "chunk-embeddings"
# Nome del full-text index Neo4j (BM25). Obbligatorio per i retriever "hybrid*".
fulltext_index = "chunk-text"
# Query Cypher di arricchimento eseguita dopo la similarità. Usata dai
# retriever "*_cypher" per arricchire i match con traversal del grafo.
# Variabili in scope: `node` (nodo matchato) e `score` (similarità).
retrieval_query = """
RETURN node.id            AS chunk_id,
       node.text          AS text,
       node.base_name     AS base_name,
       node.file_name     AS file_name,
       node.chunk_index   AS chunk_index,
       score
"""
# Proprietà dei nodi da ritornare inoltre (per i retriever vettoriali puri).
return_properties = ["chunk_id", "text"]

# --- Pipeline di retrieval (Step 8 docs/06-roadmap-fase1.md) ---
# Tre step sequenziali: pre-retrieval -> retrieval -> post-retrieval.
# Ogni step accetta method = "identity" come NO-OP esplicito (i dati passano
# through, senza istanziare LLM/reranker): pipeline sempre omogenea e
# intento dell'utente dichiarato nel TOML (es. legal: nulla viene riassunto).

[pre_retrieval]
# Query rewriting. "identity" = nessuna riscrittura (1:1).
method = "identity"
# params = { n_queries = 3 }  # es. per multi_query

[retrieval]
# Metodo di ricerca: "dense" | "sparse" | "hybrid".
# - dense: similarity search sul vector store (sempre disponibile).
# - sparse: BM25-like. Se il modello embedding espone embed_sparse
#   (es. bge-m3) viene usato nativamente; altrimenti la manager monta
#   automaticamente un BM25 esterno (rank_bm25) sul testo grezzo dei chunk,
#   con un warning di log all'avvio.
# - hybrid: ensemble dense + sparse; la fusione e' controllata da `fusion`.
method = "dense"
fusion = "rrf"   # "rrf" (default, robusto) | "weighted_sum" (richiede pesi)

[post_retrieval]
# Numero di risultati finali passati al LLM generatore.
top_k = 10
# Reranking: riordino dei top-N prima della compression.
# "identity" = nessun rerank (l'ordine del retrieval resta tale).
reranker = "identity"
# reranker_model = "BAAI/bge-reranker-v2-m3"   # solo se reranker != "identity"
# Compression: sintesi/riduzione dei contenuti passati all'LLM.
# "identity" = testo originale as-is (nessun riassunto).
# Utile per il caso legale: passare le leggi non riassunte al LLM.
compressor = "identity"
```

### Esempio di `bases/test_kb1.toml`

```toml
# Configurazione della base test_kb1
# I campi mancanti ereditano da defaults.toml

[chunking]
chunk_size = 500          # override del default del workspace
chunk_overlap = 100

[embedding]
model = "sentence-transformers/all-MiniLM-L6-v2"   # base con modello più leggero

[pre_retrieval]
method = "multi_query"
params = { n_queries = 4 }
```

### Strategie (plugin/strategy pattern)

Ogni componente è identificato da un **nome** + eventuali **parametri**, in modo da poter aggiungere nuove librerie/metodi senza riscrivere il codice:

| Sezione | Campo `library`/`method`/`model` | Esempi |
|---|---|---|
| `[ingestion]` | `library` | `"docling"`, `"pypdf"`, `"unstructured"`, `"markitdown"`, `"PyMuPDF4LLM"`, `"pdfplumber"` |
| `[chunking]` | `method` | `"fixed_size"` (con `chunk_overlap=0` no-overlap, `>0` sliding window), `"recursive"`, `"semantic"`, `"sentence"`, `"markdown"` |
| `[retrieval]` | `expansion` (in pausa, Step 8) | `"none"` (default), `"parent_child"` con `parent_granularity = "section" \| "paragraph"` |
| `[embedding]` | `mode` (in pausa, Step 6) | `"standard"` (default), `"late_chunking"` (richiede modello long-context ≥8192 tok; fallback automatico a `standard` se doc > `max_context_tokens`) |
| `[embedding]` | `model` | qualsiasi modello HuggingFace locale o API (es. OpenAI) registrato |
| `[pre_retrieval]` | `method` | `"identity"` (no-op), `"hyde"`, `"multi_query"` |
| `[retrieval]` | `method` / `fusion` | `"dense"` / `"sparse"` / `"hybrid"` ; `"rrf"` / `"weighted_sum"` (solo se `hybrid`) |
| `[post_retrieval]` | `reranker` / `compressor` | `"identity"` (no-op), `"cross_encoder"`, `"llm"` ; `"identity"`, `"llm_chain_extract"` |
| `[graph]` | `schema`/`resolver`/`on_chunk_edit`/`retriever` | `"manuale"`/`"EXTRACTED"`/`"FREE"`, `"semantic"`/`"exact"`/`"fuzzy"`, `"eager"`/`"lazy"`, `"vector"`/`"vector_cypher"`/`"hybrid"`/`"hybrid_cypher"`/`"text2cypher"`/`"tools"` |

La sezione `[graph]` è descritta in dettaglio in [04-graph.md](04-graph.md). Il campo `retriever` seleziona il metodo di ricerca GraphRAG (tabella dei valori in [04-graph.md §14](04-graph.md)); l'app istanzia solo il retriever specificato dall'utente. Il cambio del modello di `[embedding]` è **bloccato** se la collection Chroma non è vuota (vedi [04-graph.md §9](04-graph.md)). I chunk vivono in `<base>/.chunks/<file_stem>/` (dotfolder, ownership dell'utente, editabili) — vedi la sezione [Filesystem](#filesystem) per la struttura completa.

#### Modelli di embedding supportati

Il sistema supporta **molteplici modelli di embedding** via registry. Ogni modello registra metadati discoverable esposti poi dall'API e dal frontend (vedi [06-roadmap-fase1.md](06-roadmap-fase1.md) Step 6 e [09-roadmap-fase4.md](09-roadmap-fase4.md) Step 15):

| Modello | `languages` | `dim` | `max_context_tokens` | Licenza | Note |
|---|---|---|---|---|---|
| `sentence-transformers/all-mpnet-base-v2` | EN | 768 | 384 | Apache 2.0 | Solo inglese; non adatto a documenti italiani. |
| `sentence-transformers/all-MiniLM-L6-v2` | EN | 384 | 384 | Apache 2.0 | Leggero; solo EN. |
| `Alibaba-NLP/gte-large-en-v1.5` | EN | 1024 | 8192 | Apache 2.0 | Top EN su MTEB (65.39); lungo contesto. |
| `BAAI/bge-large-en-v1.5` | EN | 1024 | 512 | MIT | Buona qualità EN, ctx corto. |
| `BAAI/bge-m3` | multilingua (100+, 🇮🇹) | 1024 | 8192 | MIT | SOTA MIRACL; dense+sparse+colbert; ideale per IT + terminologia tecnica. |
| `intfloat/multilingual-e5-small` | multilingua (100+, 🇮🇹) | 384 | 512 | MIT | Leggero, ~470 MB; buon compromesso per studenti IT. |
| `intfloat/multilingual-e5-large` | multilingua (100+, 🇮🇹) | 1024 | 512 | MIT | Più pesante ma migliore qualità di e5-small. |

> **Avvertenza critica — contesto e lingue**:
> - Ogni modello ha un `max_context_tokens` (es. 384 per `all-mpnet`, 8192 per `gte`/`bge-m3`). Se un chunk supera questo limite, il `KnowledgeBaseManager` deve **lanciare un errore esplicito** (non troncare silenziosamente) — vedi nota in [06-roadmap-fase1.md](06-roadmap-fase1.md) Step 6.
> - I modelli solo-EN (`all-mpnet`, `all-MiniLM`, `gte-large-en`, `bge-large-en`) **non sono adatti a documenti italiani**: il frontend deve mostrarne le lingue supportate per evitare scelte errate (Step 15).

Il programma mantiene un **registro di strategie** per `ingestion`, `chunking`, `embedding`, e istanzia quella giusta in base al nome nel config. Aggiungere una nuova libreria di ingestion = registrare una nuova strategia, senza toccare il codice esistente.

### Regole di modifica

- I file TOML sono pensati per essere **modificati a mano** dall'utente (file aperto in un editor).
- La **CLI non deve poter scrivere** i file TOML: li legge soltanto.
- In futuro l'interfaccia grafica potrà modificarli, ma per ora no.
- Il programma deve **validare** il TOML all'avvio: se un valore non è riconosciuto, loggare un warning e usare il default.

### Come leggere la configurazione

Python 3.11+ include `tomllib` per leggere (non scrivere) TOML:

```python
import tomllib
from pathlib import Path

def load_base_config(base_name: str, workspace_paths) -> BaseConfig:
    # 1. Defaults hardcoded
    config = BaseConfig()
    # 2. Override con defaults.toml del workspace
    defaults_path = workspace_paths.defaults_toml
    if defaults_path.exists():
        with open(defaults_path, "rb") as f:
            config = config.override(BaseConfig.from_toml(tomllib.load(f)))
    # 3. Override con config specifica della base
    base_toml = workspace_paths.base_config_dir / f"{base_name}.toml"
    if base_toml.exists():
        with open(base_toml, "rb") as f:
            config = config.override(BaseConfig.from_toml(tomllib.load(f)))
    return config
```

---

### Pipeline di retrieval

La ricerca è configurabile in tre step sequenziali:

```
query → [pre_retrieval] → [retrieval] → [post_retrieval] → contesto → LLM generatore
```

Ogni step accetta `"identity"` come **no-op esplicito**: i dati passano through senza chiamate a LLM/reranker. La pipeline resta omogenea e il file TOML **dichiara l'intento** dell'utente (utile per es. `legal`: "nessuna riscrittura, nessuna compression").

#### `[pre_retrieval]` — query rewriting

| Campo | Valori | Descrizione |
|---|---|---|
| `method` | `"identity"` \| `"hyde"` \| `"multi_query"` | `identity` = no-op (1:1); `hyde` genera documenti ipotetici; `multi_query` espande in N sub-query via LLM |
| `params` | mappa (opzionale) | es. `{ n_queries = 3, llm = "..." }` per `multi_query` |

Output: lista di query (`list[str]`) passate al retrieval.

#### `[retrieval]` — ricerca

| Campo | Valori | Descrizione |
|---|---|---|
| `method` | `"dense"` \| `"sparse"` \| `"hybrid"` | scelta esplicita utente |
| `fusion` | `"rrf"` \| `"weighted_sum"` | usato solo se `method = "hybrid"`; `rrf` default (robusto, no tuning) |

**Comportamento sparse**:
- Se il modello embedding della base espone `embed_sparse` nativamente (es. `BAAI/bge-m3`), viene riusato.
- **Altrimenti fallback automatico a BM25 esterno** (`rank_bm25` sul testo grezzo dei chunk), con **warning di log all'avviso** all'avvio. L'utente non deve fare nulla; il sistema sceglie la strategia better-available per il modello scelto.

Compatibilità `method` × modello embedding:

| Modello embedding | `dense` | `sparse` | `hybrid` |
|---|---|---|---|
| `BAAI/bge-m3` | ✓ | ✓ nativo | ✓ nativo |
| `gte-large-en-v1.5`, `bge-large-en-v1.5`, `all-mpnet`, `all-MiniLM`, `multilingual-e5-*` | ✓ | ✓ via BM25 fallback | ✓ via BM25 fallback |

#### `[post_retrieval]` — rerank e compress

| Campo | Valori | Descrizione |
|---|---|---|
| `top_k` | intero | numero di risultati finali passati all'LLM (applicato **ultimi**, dopo ogni altra elaborazione) |
| `reranker` | `"identity"` \| `"cross_encoder"` \| `"llm"` | riordino dei top-N; `identity` = no rerank |
| `reranker_model` | stringa (opzionale) | es. `BAAI/bge-reranker-v2-m3`; solo se `reranker != "identity"` |
| `compressor` | `"identity"` \| `"llm_chain_extract"` | compression/sintesi del contesto; `identity` = testo as-is |

**Ordine fisso**: rerank **prima**, compress **dopo**. L'LLM generatore vede solo ciò che esce dal compressor.

#### Esempio: profilo legale (nessuna manipolazione)

```toml
[pre_retrieval]
method = "identity"                # query del legale è già precisa, non va riscritta

[retrieval]
method = "hybrid"
fusion = "rrf"

[post_retrieval]
top_k = 20
reranker = "identity"              # nessun rerank
compressor = "identity"            # testo originale passato as-is, NESSUN riassunto
```

#### Esempio: profilo ricercatore (pipeline avanzata)

```toml
[pre_retrieval]
method = "multi_query"
params = { n_queries = 4 }

[retrieval]
method = "hybrid"
fusion = "rrf"

[post_retrieval]
top_k = 8
reranker = "cross_encoder"
reranker_model = "BAAI/bge-reranker-v2-m3"
compressor = "llm_chain_extract"   # compression contestualizzata del top-8 rerankato
```

---

## Configurazione dell'applicazione: `RuntimePaths` + `AppConfig`

### `RuntimePaths`

Classe Pydantic che racchiude tutti i path necessari, mantenendo lo standard XDG.

### `UserSettings`

Gestisce il file JSON con preferenze e secrets (es. `hf_key`). Separato dalla configurazione delle basi.

### `AppConfig`

Aggrega `RuntimePaths` e `UserSettings`, permettendo override da CLI/env.

```
AppConfig
├── RuntimePaths    # path XDG (config, data, state)
├── UserSettings    # config.json (hf_key, preferenze)
└── EnvSettings     # variabili d'ambiente
```

## Opzioni per passare la configurazione

1. **Fase immediata**: passare `RuntimePaths` esplicitamente ai costruttori di `Workspace` e `KnowledgeBase`.
2. **Fase successiva**: estrarre i repository (`WorkspaceRepository`, `KnowledgeBaseRepository`, `VectorStore`, `ChunkStore`) e creare `WorkspaceService`/`KnowledgeBaseService`.
3. A livello di applicazione (`knowledge-space` e `mcp-server`), usare un `AppContext` che crea una sola istanza di `RuntimePaths` e dei service per processo.

## Variabili d'ambiente

| Variabile | Descrizione |
|-----------|-------------|
| `KS_CONFIG_FILE` | Path del file config.json |
| `KS_DATA_DIR` | Directory base per dati (chunks) |
| `KS_STATE_DIR` | Directory base per stato (TinyDB, Chroma, log) |
| `KS_LOG_LEVEL` | Livello di log |
| `KS_HF_TOKEN` | Token HuggingFace (alternativa a config.json) |

## Note sulla sicurezza

- I secrets (es. `hf_key`) devono rimanere in `config.json` con permessi 600 o in variabili d'ambiente.
- L'endpoint REST `/api/v1/config` non deve mai restituire `hf_key` in chiaro.
- Considerare l'uso di `keyring` per la gestione dei token in futuro.
- I file TOML delle basi **non** contengono secrets: solo parametri di ingestion/chunking/embedding.