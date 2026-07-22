# Gestione della configurazione

## Stato vs configurazione

Conviene tenere separati due concetti distinti:

| | Stato | Configurazione |
|---|------|----------------|
| Cosa | domini, basi, file, chunk, flag `active`, mtime | ingestion, chunking, embedding, parametri |
| Cambia spesso? | Sì, a runtime | No, raramente |
| Chi lo scrive | il programma | l'utente (a mano) |
| Formato | JSON (machine-friendly) | TOML (human-friendly, con commenti) |

- Lo **stato** del workspace vive in `<workspace>/.knowledge-space/state.json` (vedi [20-data-model.md](20-data-model.md)).
- La **configurazione** di ogni base vive in **TOML**, un file per base.

---

## Configurazione delle basi di conoscenza

### Filesystem

La struttura completa del filesystem (workspace, basi, chunk, graph) vive qui. La pipeline GraphRAG fa riferimento a questo layout — vedi anche [40-graph.md](40-graph.md) per le convenzioni specifiche del grafo.

```
<workspace>/
├── paper.pdf                              # file sorgente dell'utente (esempio)
├── <base>/                                # base = cartella foglia dentro il workspace
│   ├── documento.pdf                      # file sorgente dell'utente (appartenenti alla base)
│   ├── appunti.md
│   └── .knowledge-space/                  # dotfolder, dati e config di proprietà della base
│       ├── base.toml                      # configurazione specifica della base
│       └── chunks/                       # chunk su disco (prodotto derivato del sorgente)
│           └── <file_id>/                # file_id = UUID stabile del FileEntry
│               ├── <file_id>_chunk_0.md
│               ├── <file_id>_chunk_1.md
│               └── ...
└── .knowledge-space/                      # dotfolder, stato e config di proprietà del workspace
    ├── state.json                        # stato (albero Workspace -> Domain -> Base -> File -> Chunk)
    ├── defaults.toml                     # default per tutte le basi del workspace
    └── graph/                            # stato e connessione del grafo workspace (uno per workspace)
        ├── graph.json                    # bolt_uri, database, embedding_model, schema_ref
        └── schema.json                   # schema del grafo (caricato, vedi 40-graph.md §6-bis)
```

Regole:
- **Niente basi fuori da un workspace**: una base è sempre una sottocartella di un workspace.
- I chunk su disco sono un **prodotto derivato** del documento sorgente via ingestion + chunking. **Non sono editabili dall'utente**: Chroma è la fonte di verità. L'utente che vuole modificare il contenuto deve editare il **documento sorgente** e lasciare che KS re-indicizzi (vedi [45-indexing-incrementale.md](45-indexing-incrementale.md)).
- Ogni base ha il proprio `.knowledge-space/` (chunk + `base.toml`): la base è **autocontenuta**, copiabile/spostabile con la sua config e i suoi chunk.
- Il watcher sorgente della base ignora i path che iniziano con `.` (`.knowledge-space/`).
- `graph/` appartiene al workspace (un grafo per workspace), ma la **configurazione del comportamento** (schema, `on_chunk_change`, `resolver`) è in `[graph]` del `BaseConfig` per-base — vedi [40-graph.md](40-graph.md).
- Cascata di configurazione: default hardcoded → `<workspace>/.knowledge-space/defaults.toml` → `<base>/.knowledge-space/base.toml`.
- Se una base non ha `base.toml`, usa i default del workspace (comportamento legittimo, **nessun warning**).
- Se `defaults.toml` manca, KS usa i default hardcoded del programma **con un warning all'avvio** (segnala intenzione/config persa); KS non riscrive mai il TOML.
- KS **non ricrea** i file TOML eliminati (regola: TOML è human-written).
- I path dei chunk su disco usano `file_id` (UUID) invece di `file_stem`, così il rename del file sorgente non sposta la cartella chunk né cambia i `chunk_id` (vedi [45-indexing-incrementale.md](45-indexing-incrementale.md) trigger 2).

### Esempio di `defaults.toml`

```toml
# Default per tutte le basi del workspace

[ingestion]
library = "docling"
params.use_gpu = false       # true per accelerare con GPU (docling, embedding)

[chunking]
method = "fixed_size"
chunk_size = 1000
chunk_overlap = 200
separator = "\n\n"

[embedding]
model = "sentence-transformers/all-mpnet-base-v2"
# device = "cpu"

[graph]
# Configurazione del grafo della conoscenza (vedi docs/40-graph.md).
# I parametri di connessione al DB (bolt_uri, credenziali) sono a livello
# workspace in <workspace>/.knowledge-space/graph/graph.json, perché il
# grafo è uno per workspace; qui restano solo i comportamenti per-base.
schema = "manuale"          # "manuale" | "EXTRACTED" | "FREE"
resolver = "semantic"      # "semantic" (default, extra [nlp]) | "exact" | "fuzzy" (extra [fuzzy-matching]) | "none"
on_chunk_change = "eager"  # "eager" (default, ri-estrazione LLM sui chunk cambiati) | "lazy" (solo Chroma update)
chunk_embedding_property = "embedding"   # nome della proprietà vettore nel nodo Chunk

# Node/relationship types + patterns. Ignorati se schema = "EXTRACTED" o "FREE".
# Si possono anche materializzare in <workspace>/.knowledge-space/schema.json
# (vedi docs/40-graph.md §6-bis: caricato, non ricreato).
node_types = ["Person", "Organization", "Concept"]
relationship_types = ["WORKS_FOR", "RELATED_TO"]
patterns = [
    ["Person", "WORKS_FOR", "Organization"],
    ["Concept", "RELATED_TO", "Concept"],
]

# --- Retrieval (fase di ricerca, vedi docs/40-graph.md §14) ---
# Metodo di ricerca GraphRAG usato dall'app per le query su questa base.
# L'utente può specificare uno qualsiasi tra quelli supportati da
# neo4j-graphrag; l'app istanzia il retriever corrispondente.
retriever = "hybrid_cypher"   # vedi tabella in docs/40-graph.md §14
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

# --- Pipeline di retrieval (Step 8 — docs/91b-roadmap-fase1-ricerca.md) ---
# Tre step sequenziali: pre-retrieval -> retrieval -> post-retrieval.
# Ogni step accetta method = "identity" come NO-OP esplicito (i dati passano
# through, senza istanziare LLM/reranker): pipeline sempre omogenea e
# intento dell'utente dichiarato nel TOML (es. consulente: nulla viene riassunto).

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
# Utile per il profilo consulente: passare i documenti non riassunti al LLM.
compressor = "identity"
```

### Esempio di `<base>/.knowledge-space/base.toml`

```toml
# Configurazione della base (es. test_kb1)
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

| Sezione | Campo `library`/`method`/`model` | Esempi | Specifiche |
|---|---|---|---|
| `[ingestion]` | `library` | `"docling"`, `"pymupdf4llm"`, `"markitdown"` | [50-ingestion.md](50-ingestion.md) |
| `[chunking]` | `method` | `"fixed_size"`, `"recursive"`, `"semantic"`, `"sentence"`, `"markdown"` | [60-chunking.md](60-chunking.md) |
| `[embedding]` | `model` | qualsiasi modello HuggingFace locale o API | [70-embedding.md](70-embedding.md) |
| `[pre_retrieval]` | `method` | `"identity"`, `"hyde"`, `"multi_query"` | [80-retrieval.md](80-retrieval.md) |
| `[retrieval]` | `method` / `fusion` | `"dense"` / `"sparse"` / `"hybrid"`; `"rrf"` / `"weighted_sum"` | 80 |
| `[post_retrieval]` | `reranker` / `compressor` | `"identity"`, `"cross_encoder"`, `"llm"` | 80 |
| `[graph]` | `schema`/`resolver`/`on_chunk_change`/`retriever` | `"manuale"`/`"EXTRACTED"`/`"FREE"`, `"semantic"`/`"exact"`/`"fuzzy"`, `"eager"`/`"lazy"` | [40-graph.md](40-graph.md) |

Il programma mantiene un **registro di strategie** per `ingestion`, `chunking`, `embedding`, e istanzia quella giusta in base al nome nel config. Aggiungere una nuova libreria di ingestion = registrare una nuova strategia, senza toccare il codice esistente.

Il cambio di `[embedding].model`, `[chunking].method` o `[ingestion].library` su una base con collection Chroma non vuota è **bloccato** (serve `ks reindex <base> --<reason>` esplicito, vedi [45-indexing-incrementale.md](45-indexing-incrementale.md) trigger 3/4/5). I chunk vivono in `<base>/.knowledge-space/chunks/<file_id>/` (dotfolder, prodotto derivato del sorgente, non editabili) — vedi la sezione [Filesystem](#filesystem) per la struttura completa.

### Regole di modifica

- I file TOML sono pensati per essere **modificati a mano** dall'utente (file aperto in un editor).
- La **CLI non deve poter scrivere** i file TOML: li legge soltanto.
- In futuro l'interfaccia grafica potrà modificarli, ma per ora no.
- Il programma deve **validare** il TOML all'avvio: se un valore non è riconosciuto, loggare un warning e usare il default.

---

## Configurazione dell'applicazione: `RuntimePaths` + `AppConfig`

### `RuntimePaths`

Classe Pydantic che racchiude tutti i path necessari, mantenendo lo standard XDG.

### `UserSettings`

Gestisce il file `~/.config/KnowledgeSpace/config.json` con secrets e preferenze utente (es. `hf_token`, chiavi API remote embedding). Separato dalla configurazione delle basi (TOML) e dallo stato del workspace (`state.json`). Machine-writable via `config set`, ma anche editabile manualmente dall'utente.

### `AppConfig`

Aggrega `RuntimePaths` e `UserSettings`, permettendo override da CLI/env.

```
AppConfig
├── RuntimePaths    # path XDG (config, data, state)
├── UserSettings    # ~/.config/KnowledgeSpace/config.json (secrets, preferenze)
└── EnvSettings     # variabili d'ambiente
```

## Opzioni per passare la configurazione

1. **Fase immediata**: passare `RuntimePaths` esplicitamente ai costruttori di `Workspace` e `KnowledgeBase`.
2. **Fase successiva**: estrarre i repository (`WorkspaceRepository`, `KnowledgeBaseRepository`, `VectorStore`, `ChunkStore`) e creare `WorkspaceService`/`KnowledgeBaseService`.
3. A livello di applicazione (`knowledge-space` e `mcp-server`), usare un `AppContext` che crea una sola istanza di `RuntimePaths` e dei service per processo.

## Variabili d'ambiente

| Variabile | Descrizione |
|-----------|-------------|
| `KS_CONFIG_FILE` | Path del file UserSettings `config.json` (`~/.config/KnowledgeSpace/config.json` di default) |
| `KS_DATA_DIR` | Directory base per dati (chunks) |
| `KS_STATE_DIR` | Directory base per stato (TinyDB, Chroma, log) |
| `KS_LOG_LEVEL` | Livello di log |
| `KS_HF_TOKEN` | Token HuggingFace (alternativa a config.json) |
| `OPENAI_API_KEY` | Chiave API OpenAI (embedding remoto `openai/*`) |
| `COHERE_API_KEY` | Chiave API Cohere (embedding remoto `cohere/*`) |
| `VOYAGE_API_KEY` | Chiave API Voyage AI (embedding remoto `voyage/*`) |

I modelli remoti leggono la chiave da `~/.config/KnowledgeSpace/config.json` (UserSettings) o da env var. Vedi [70-embedding.md §Modelli remoti](70-embedding.md#modelli-remoti-con-chiave-api) per i dettagli.

## Note sulla sicurezza

- I secrets (es. `hf_token`, chiavi API remote) devono rimanere in `~/.config/KnowledgeSpace/config.json` con permessi 600 o in variabili d'ambiente.
- L'endpoint REST `/api/v1/config` non deve mai restituire `hf_key` in chiaro.
- Considerare l'uso di `keyring` per la gestione dei token in futuro.
- I file TOML delle basi **non** contengono secrets: solo parametri di ingestion/chunking/embedding.