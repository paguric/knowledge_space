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

Vedi [32-defaults-toml.md](32-defaults-toml.md).

### Esempio di `<base>/.knowledge-space/base.toml`

Vedi [33-base-toml.md](33-base-toml.md).

### Strategie (plugin/strategy pattern)

Ogni componente è identificato da un **nome** + eventuali **parametri**, in modo da poter aggiungere nuove librerie/metodi senza riscrivere il codice:

| Sezione | Campo `library`/`method`/`model` | Esempi | Specifiche |
|---|---|---|---|
| `[ingestion]` | `library` | `"docling"`, `"pymupdf4llm"`, `"markitdown"` | [50-ingestion.md](50-ingestion.md) |
| `[chunking]` | `method` | `"fixed_size"`, `"recursive"`, `"semantic"`, `"sentence"`, `"markdown"` | [60-chunking.md](60-chunking.md) |
| `[embedding]` | `model` | qualsiasi modello HuggingFace locale o API | [70-embedding.md](70-embedding.md) |
| `[pre_retrieval]` | `stages[{method, model, params}]` | `"identity"`, `"multi_query"`, `"step_back"`, `"least_to_most"` | [80-retrieval.md](80-retrieval.md), [75-llm.md](75-llm.md) |
| `[retrieval]` | `method` / `fusion` | `"dense"` / `"sparse"` / `"hybrid"`; `"rrf"` / `"weighted_sum"` | 80 |
| `[post_retrieval]` | `reranker` / `compressor` | `"identity"`, `"cross_encoder"`, `"llm"` | 80 |
| `[graph]` | `schema`/`resolver`/`on_chunk_change`/`retriever` | `"manuale"`/`"EXTRACTED"`/`"FREE"`, `"semantic"`/`"exact"`/`"fuzzy"`, `"eager"`/`"lazy"` | [40-graph.md](40-graph.md) |

Il programma mantiene un **registro di strategie** per `ingestion`, `chunking`, `embedding`, e istanzia quella giusta in base al nome nel config. Aggiungere una nuova libreria di ingestion = registrare una nuova strategia, senza toccare il codice esistente.

Il cambio di `[embedding].model`, `[chunking].method` o `[ingestion].library` su una base con collection Chroma non vuota è **bloccato** (serve `ks reindex <base> --<reason>` esplicito, vedi [45-indexing-incrementale.md](45-indexing-incrementale.md) trigger 3/4/5). I chunk vivono in `<base>/.knowledge-space/chunks/<file_id>/` (dotfolder, prodotto derivato del sorgente, non editabili) — vedi la sezione [Filesystem](#filesystem) per la struttura completa.

### Regole di modifica

L'accesso in scrittura alla configurazione TOML è diviso in due fasi:

**Fase 1 (Step 3, Fase 1A) — sola lettura:**
- I file TOML sono pensati per essere **modificati a mano** dall'utente (file aperto in un editor).
- Il programma **legge** ma non scrive i file TOML.
- Il programma **valida** il TOML all'avvio: se un valore non è riconosciuto, logga un warning e usa il default.

**Fase 2 (Step 13, Fase 3) — scrittura via CLI:**
- La CLI ottiene il comando `config set` per modificare le preferenze nei TOML.
- Il programma scrive solo i file TOML delle basi e `defaults.toml`, mai il config dell'app (`config.json` gestito da `auth set`).
- Il comando rileva automaticamente se la chiave modificata impatta l'indice esistente (`embedding.model` → re-embed, `chunking.method` → re-chunk, `ingestion.library` → re-ingest) e chiede conferma prima di procedere.

### Trigger di reindex

Il cambio di alcune chiavi di configurazione su una base con collection Chroma non vuota attiva un trigger di reindex. I trigger sono rilevati automaticamente:

| Trigger | Chiave config | Impatto |
|---|---|---|
| `model-change` | `embedding.model` | Nuova collection Chroma con `dim` del nuovo modello, re-embed da disco. |
| `chunking-change` | `chunking.method` | Re-chunk + re-embed + riscrittura chunk su disco. Delete+insert in Chroma. |
| `ingestion-change` | `ingestion.library` | Re-ingest + re-chunk + re-embed. Come chunking-change ma parte da ingestion. |

Il rilevamento avviene in due punti:
- **All'avvio**: se la configurazione TOML differisce da quella registrata in `state.json` e la collection non è vuota, il caricamento fallisce con un messaggio che invita a usare `ks reindex`.
- **In scrittura via CLI** (`config set`): il comando rileva il trigger dalla chiave modificata, chiede conferma, e avvia automaticamente il reindex appropriato.

Vedi [45-indexing-incrementale.md](45-indexing-incrementale.md) per la specifica completa dei 5 trigger (inclusi content-change e move/rename, che non dipendono dalla configurazione).

---

## Configurazione dell'applicazione

La configurazione dell'applicazione (`RuntimePaths`, `UserSettings`, `AppConfig`, variabili d'ambiente, sicurezza) è descritta in [31-configurazione-app.md](31-configurazione-app.md).