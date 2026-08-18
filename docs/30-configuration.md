# Gestione della configurazione

> **Stato:** implementato | **Step:** 3 | **Fase:** 1A | **Aggiornato:** 18 agosto 2026

## Panoramica

Ogni base di conoscenza ha la propria configurazione TOML, con cascata di default: hardcoded → `defaults.toml` (workspace) → `base.toml` (base). Lo stato (domini, basi, file, chunk) vive in JSON separato dalla configurazione (ingestion, chunking, embedding, retrieval).

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Formato stato | JSON (`state.json` per workspace) |
| Formato config | TOML (human-friendly, con commenti) |
| Cascata | hardcoded → `defaults.toml` → `base.toml` |
| Strategy pattern | Registry per ingestion, chunking, embedding, retrieval, LLM |
| Cambio config | Bloccato se collection non vuota |
| Secrets | Mai nei TOML — env var o `UserSettings` |
| Scrittura TOML | Sola lettura (Fase 1), scrittura via CLI `config set` (Fase 3) |

## Dettagli

### Stato vs configurazione

| | Stato | Configurazione |
|---|------|----------------|
| Cosa | domini, basi, file, chunk, flag `active`, mtime, snapshot config registrato per base (per blocco cambio config) | ingestion, chunking, embedding, parametri |
| Cambia spesso? | Sì, a runtime | No, raramente |
| Chi lo scrive | il programma | l'utente (a mano) |
| Formato | JSON | TOML |

### Filesystem

```
<workspace>/
├── paper.pdf                              # file sorgente dell'utente (esempio)
├── <base>/                                # base = cartella foglia dentro il workspace
│   ├── documento.pdf                      # file sorgente dell'utente
│   ├── appunti.md
│   └── .knowledge-space/                  # dotfolder, dati e config della base
│       ├── base.toml                      # configurazione specifica della base
│       ├── documents/                     # Markdown convertito (feat-007, riuso reindex)
│       │   └── <file_id>.md
│       └── chunks/                        # chunk su disco (prodotto derivato)
│           └── <file_id>/                 # file_id = sha256 del percorso (deterministico)
│               ├── <file_id>_chunk_0.md
│               └── <file_id>_chunk_1.md
└── .knowledge-space/                      # dotfolder, stato e config del workspace
    ├── state.json                         # stato (Workspace → Domain → Base → File → Chunk)
    ├── defaults.toml                      # default per tutte le basi
    ├── chroma/                            # collection vettoriali (ChromaDB, fonte di verità)
    │   ├── chroma.sqlite3
    │   └── <collection-uuid>/             # una per base (dense) o coppia (hybrid)
    └── graph/                             # stato grafo workspace (uno per workspace)
        └── graph.json                     # bolt_uri, user, password, database (refactor-001)
```

**Regole:**
- Niente basi fuori da un workspace
- Chunk su disco sono **prodotto derivato**, non editabili dall'utente (Chroma è fonte di verità)
- Ogni base è **autocontenuta** (copiabile/spostabile con la sua config e i suoi chunk)
- Watcher sorgente ignora i path che iniziano con `.`
- `graph/` appartiene al workspace (un grafo per workspace)

### Cascata di configurazione

```
default hardcoded
  ↓ override
<workspace>/.knowledge-space/defaults.toml
  ↓ override
<base>/.knowledge-space/base.toml
```

- Se una base non ha `base.toml`, usa i default del workspace (nessun warning)
- Se `defaults.toml` manca, usa i default hardcoded **con warning** all'avvio
- KS **non ricrea** mai i file TOML eliminati

### Strategie (plugin/strategy pattern)

| Sezione | Campo | Esempi | Specifiche |
|---|---|---|---|
| `[ingestion]` | `library` | `"pymupdf4llm"` (default), `"markitdown"` (hard), `"docling"` (extra) | [50-ingestion.md](50-ingestion.md) |
| `[chunking]` | `method` | `"fixed_size"`, `"recursive"`, `"semantic"`, `"sentence"`, `"paragraph"`, `"markdown"` | [60-chunking.md](60-chunking.md) |
| `[embedding]` | `model` | qualsiasi modello HuggingFace o API | [70-embedding.md](70-embedding.md) |
| `[pre_retrieval]` | `stages[{method, model, params}]` | `"identity"`, `"multi_query"`, `"step_back"`, `"least_to_most"` | [80-retrieval.md](80-retrieval.md), [75-llm.md](75-llm.md) |
| `[retrieval]` | `method` / `fusion` | `"dense"` / `"sparse"` / `"hybrid"`; `"rrf"` / `"weighted_sum"` | [80-retrieval.md](80-retrieval.md) |
| `[post_retrieval]` | `reranker` / `compressor` | `"identity"`, `"cross_encoder"`, `"llm"` | [80-retrieval.md](80-retrieval.md) |
| `[graph]` | `enabled` / `on_chunk_change` / `extraction_model` / `embedding_model` / `top_k` | `"eager"`/`"lazy"`, LLM per l'estrazione entità (None = grafo inattivo) | [40-graph.md](40-graph.md) |

### Regole di modifica

**Fase 1 (sola lettura):** TOML modificati a mano dall'utente. Il programma legge, valida (warning + fallback per valori non riconosciuti), non scrive.

**Fase 2 (scrittura via CLI):** comando `config set` per modificare le preferenze. Rileva automaticamente trigger di reindex e chiede conferma.

### Trigger di reindex

| Trigger | Chiave config | Impatto |
|---|---|---|
| `model-change` | `embedding.model` | Nuova collection Chroma, re-embed da disco |
| `chunking-change` | `chunking.method` | Re-chunk + re-embed + riscrittura chunk su disco |
| `ingestion-change` | `ingestion.library` | Re-ingest + re-chunk + re-embed |

Rilevamento: all'avvio (config TOML vs `state.json`) e in scrittura via CLI (`config set`). Vedi [45-indexing-incrementale.md](45-indexing-incrementale.md) per i 5 trigger completi.

### Configurazione dell'applicazione

La configurazione dell'applicazione (`RuntimePaths`, `UserSettings`, `AppConfig`, variabili d'ambiente) è descritta in [31-configurazione-app.md](31-configurazione-app.md).

### Appendix A — Esempio di `defaults.toml`

```toml
[ingestion]
library = "pymupdf4llm"
# params = {}

[chunking]
method = "fixed_size"
chunk_size = 2048
chunk_overlap = 64
separator = "\n\n"

[embedding]
model = "BAAI/bge-m3"
# device = "cpu"

[pre_retrieval]
# [[pre_retrieval.stages]]
# method = "identity"

[retrieval]
method = "dense"
query_mode = "original"
top_k = 10

[post_retrieval]
method = "identity"

[graph]
enabled = false
on_chunk_change = "lazy"
top_k = 5
# extraction_model = "lm-studio/auto"   # LLM per l'estrazione entità (None = grafo inattivo)
# embedding_model = "BAAI/bge-m3"
```

### Appendix B — Esempio di `base.toml`

```toml
[chunking]
chunk_size = 500
chunk_overlap = 100

[embedding]
model = "sentence-transformers/all-MiniLM-L6-v2"

[pre_retrieval]
stages = [
  { method = "multi_query", model = "openai/gpt-4o-mini", params = { n_queries = 4 } },
]
```

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Nessuno (fondamenta) | Tutti gli altri step |
