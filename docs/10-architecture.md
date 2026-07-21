# Architettura e organizzazione dei pacchetti

## Stato attuale

La codebase è organizzata come workspace `uv` con tre pacchetti:

- `knowledge-base`: contiene la logica di dominio (workspace, knowledge base, chunking, ingestion, indexing, persistenza) ma ha **variabili globali** per i path (`db_dir`, `files_index`, `chunks_dir`, `domains_index`, `bases_index`) che vengono sovrascritte dall'esterno.
- `knowledge-space`: entrypoint CLI che imposta le variabili globali di `knowledge-base` e avvia i watcher. Dipende sia da `knowledge-base` che da `mcp-server`.
- `mcp-server`: pacchetto scheletro, con una funzione `start()` che non fa nulla.

### Problemi evidenziati

1. **Accoppiamento forte**: `knowledge-space` dipende da `mcp-server`, anche se i due sono entrypoint diversi.
2. **Variabili globali**: `knowledge-base` non è self-contained. I test devono manualmente reimpostare le variabili globali.
3. **Manca il layer REST**.
4. **Manca il vero MCP**.
5. **Configurazione frammentata**.

## Visione architetturale target

```
┌─────────────────────────────────────────────────────────────┐
│                    knowledge-base (library)                  │
│  - domain: Workspace, KnowledgeBase, Chunk, File, Domain      │
│  - services: WorkspaceService, KnowledgeBaseService, Search   │
│  - repositories: TinyDB, Chroma, FileSystem                   │
│  - pipeline: ingestion, chunking, indexing                    │
│  - graph: KSChunkLoader, GraphPipeline, RetrieverFactory      │
│           (Neo4j + neo4j-graphrag)                            │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ dipende da
          ┌───────────────────┴───────────────────┐
          │                                   │
          ▼                                   ▼
┌──────────────────────┐          ┌──────────────────────┐
│   knowledge-space    │          │      mcp-server      │
│  (REST API + CLI)    │          │   (MCP adapter)      │
│                      │          │                      │
│  - FastAPI routers   │          │  - MCP tools         │
│  - Typer CLI         │          │  - stdio/SSE server  │
│  - AppContext / DI   │          │  - AppContext / DI   │
└──────────────────────┘          └──────────────────────┘
```

**Regola d'oro**: `knowledge-base` non deve sapere nulla di HTTP, MCP, CLI o variabili globali. Deve essere una libreria pura che riceve esplicitamente le dipendenze necessarie.

## Modulo `knowledge_base/graph/` (pipeline GraphRAG)

Nuovo sotto-modulo previsto dallo Step 8-bis (vedi [40-graph.md](40-graph.md) e [91c-roadmap-fase1-graphrag.md](91c-roadmap-fase1-graphrag.md)). Rispetta la regola d'oro sopra: è una libreria che riceve esplicitamente il driver Neo4j, l'embedder, la connessione Chroma e la configurazione (`GraphConfigData` lato workspace + `[graph]` lato base).

Componenti previsti:

- **`KSChunkLoader`**: componente custom `neo4j-graphrag` che legge chunk da `<base>/.knowledge-space/chunks/<file_id>/` e embedding da Chroma (skip di data loader/splitter/embedder della `SimpleKGPipeline`). Espone `upsert_chunks(base, file_id, changed_chunks)` per la propagazione incrementale (vedi [45-indexing-incrementale.md](45-indexing-incrementale.md) trigger 1).
- **`GraphPipeline`**: assemblaggio di `KSChunkLoader -> schema (caricato da `schema.json`) -> LLMEntityRelationExtractor(create_lexical_graph=True) -> Neo4jWriter -> EntityResolver`.
- **Schema manager**: caricamento `GraphSchema.from_file` se esiste, altrimenti `SchemaBuilder`/`SchemaFromTextExtractor` con materializzazione su `schema.json`.
- **`RetrieverFactory`**: costruisce il retriever di `neo4j-graphrag` corrispondente a `[graph].retriever` (valori ammessi: `vector`, `vector_cypher`, `hybrid`, `hybrid_cypher`, `text2cypher`, `tools`) iniettando driver, embedder, LLM e indici (`vector_index`/`fulltext_index`). Validazione all'avvio (retriever non ammesso → errore; `hybrid*` senza `fulltext_index` → errore). Vedi [40-graph.md §14](40-graph.md).

> **Nota**: non esiste più un `ChunkWatcher` dedicato. I chunk su disco **non sono editabili dall'utente** (Chroma è la fonte di verità). La propagazione al grafo è orchestrata dal `KnowledgeBaseManager` su eventi sorgente (content change, move/rename) e comandi `ks reindex` (cambio config), secondo [45-indexing-incrementale.md](45-indexing-incrementale.md).

Esempio di flusso dal lato applicazione (`knowledge-space` o `mcp-server`):

```python
graph_store = GraphStore(graph_config)          # driver Neo4j + schema ref
graph_pipeline = GraphPipeline(graph_store, embedder, llm)
await graph_pipeline.run_async(file_path=..., document_metadata={...})
```

Iniezione delle dipendenze: nessuna variabile globale; il `GraphStore` e l'`embedder` sono creati dall'`AppContext` a livello applicazione e passati ai service. Per i test, si iniettano un driver Neo4j di test (o un `KGWriter` custom su JSON) e un LLM mock.

## Organizzazione del monorepo

### Opzione A: Mantenere il workspace uv con tre pacchetti (consigliata)

- `knowledge-base` diventa una **library** riutilizzabile.
- `knowledge-space` diventa l'applicazione **REST + CLI**.
- `mcp-server` diventa l'applicazione **MCP**.

**Pro**: chiara separazione di responsabilità; `knowledge-base` riutilizzabile da entrambi i fronti.
**Contro**: richiede gestione corretta delle dipendenze tra pacchetti.

### Opzioni scartate

- **Unico pacchetto**: perde la separazione tra REST e MCP.
- **Repo separati**: overhead di gestione non necessario con `uv` workspace.

## Scelta consigliata

| Pacchetto | Tipo | Dipende da | Entrypoint |
|-----------|------|-----------|------------|
| `knowledge-base` | library | nessuno | nessuno (rimuovere `knowledge-base` CLI) |
| `knowledge-space` | applicazione | `knowledge-base` | `knowledge-space serve`, `knowledge-space mcp`, ... |
| `mcp-server` | applicazione | `knowledge-base` | `mcp-server` (stdio/SSE) |

## Azioni concrete

- [ ] Rimuovere `mcp-server` dalle dipendenze di `knowledge-space` nel `pyproject.toml` root.
- [ ] Aggiungere `knowledge-base` come dipendenza di `mcp-server`.
- [ ] Rimuovere gli entrypoint CLI da `knowledge-base`.
- [ ] Documentare nel README di ciascun pacchetto il suo ruolo.
- [ ] Aggiungere la dipendenza `neo4j-graphrag` + `neo4j` (extra `[nlp]`) a `knowledge-base`.
- [ ] Creare il sotto-modulo `knowledge_base/graph/` (`KSChunkLoader`, `GraphPipeline`, schema manager, `RetrieverFactory`) — vedi [40-graph.md](40-graph.md).
- [ ] Spostare i chunk in `<base>/.knowledge-space/chunks/<file_id>/` e introduzione ID deterministici `base::file_id::i` (prerequisito F0 del piano GraphRAG + [45-indexing-incrementale.md](45-indexing-incrementale.md)).

## Ciclo di vita dell'app e processo backend

Questa sezione descrive come l'applicazione viene eseguita: entry point, modalità standalone vs backend process, e relazione tra CLI, watcher, REST e MCP. La spec dettagliata è in [11-app-lifecycle.md](11-app-lifecycle.md).

### Entry point (`main.py`)

Il pacchetto `knowledge-space` espone il comando `knowledge-space` (alias `ks`) via Typer. Il vecchio `main.py` legacy (con `setup()` e variabili globali) è stato rimosso nello Step 3; il nuovo entry point (`build_app_context()` in `knowledge_space.bootstrap`) sarà introdotto nello [Step 8-ter](91a-roadmap-fase1-ingestione.md), e la CLI Typer nella Fase 3. Vedi [11-app-lifecycle.md](11-app-lifecycle.md) per la specifica del ciclo di vita.

In tutte le fasi, l'AppContext viene costruito da `build_app_context()` (vedi [91a-roadmap-fase1-ingestione.md Step 8-ter](91a-roadmap-fase1-ingestione.md)).

### Modalità di esecuzione

| Fase | Modalità | CLI | Watcher | REST | MCP |
|---|---|---|---|---|---|
| **Fase 1–3** | CLI standalone | Ogni comando crea un AppContext temporaneo, opera su file JSON/Chroma, termina. | Non attivi (solo `ks reindex` esplicito). | N/A | N/A |
| **Fase 4+** | Backend process | CLI client del backend. Errore se backend non attivo. | Attivi (watchdog per workspace). | uvicorn sulla porta 8000. | stdio ↔ REST; SSE integrato. |

### Fase 1–3: CLI standalone

In sviluppo iniziale la CLI opera senza un processo a lungo termine:

```bash
ks workspace add /path        # carica AppContext → opera → salva → termina
ks search "query" --base foo  # carica AppContext → query Chroma → output → termina
ks reindex foo                # carica AppContext → reindicizza → salva → termina
```

Ogni comando è un processo separato. Lo stato persiste via `state.json` e Chroma su disco. Non ci sono watcher in background: la sincronizzazione col filesystem è esplicita (`ks reindex` o `ks sync`).

### Fase 4+: Backend process

`ks serve` avvia un processo a lungo termine che unisce watcher, REST API, e (opzionalmente) frontend e MCP SSE. Tutti gli altri comandi CLI diventano client che parlano con questo backend via REST.

```bash
ks serve                          # backend + REST, nessuna finestra
ks serve --gui                    # backend + REST + apre webview (pywebview)
ks serve --host 0.0.0.0 --port 8000
ks serve --mcp-sse --mcp-port 8001  # espone anche MCP SSE
```

La CLI rileva il backend tramite PID file (`~/.local/state/KnowledgeSpace/ks.pid`) + ping a `/health`. Se il backend non risponde → errore "backend non attivo, avvia con `ks serve`".

`ks stop` arresta il backend via REST `/shutdown`.

### Packaging (post-Fase 4)

L'architettura è packaging-agnostic. L'AppImage/eseguibile Windows bundle Python + dipendenze + frontend React compilato e invoca internamente `ks serve --gui`. Decisione differita a Fase 4; opzioni documentate in [11-app-lifecycle.md §Packaging](11-app-lifecycle.md#packaging).
