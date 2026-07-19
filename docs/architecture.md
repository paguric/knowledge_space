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
│  - graph: KSChunkLoader, GraphPipeline, ChunkWatcher          │
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

Nuovo sotto-modulo previsto dallo Step 8-bis (vedi [graph.md](graph.md) e [roadmap.md](roadmap.md)). Rispetta la regola d'oro sopra: è una libreria che riceve esplicitamente il driver Neo4j, l'embedder, la connessione Chroma e la configurazione (`GraphConfigData` lato workspace + `[graph]` lato base).

Componenti previsti:

- **`KSChunkLoader`**: componente custom `neo4j-graphrag` che legge chunk da `<base>/.chunks/` e embedding da Chroma (skip di data loader/splitter/embedder della `SimpleKGPipeline`).
- **`GraphPipeline`**: assemblaggio di `KSChunkLoader -> schema (caricato da `schema.json`) -> LLMEntityRelationExtractor(create_lexical_graph=True) -> Neo4jWriter -> EntityResolver`.
- **`ChunkWatcher`**: watcher watchdog dedicato a `<base>/.chunks/**/*.md`, con debounce + hash check, che invoca `KSChunkLoader.upsert_chunk` e poi `GraphPipeline` (scope mirato) sul chunk editato (eager cascade).
- **Schema manager**: caricamento `GraphSchema.from_file` se esiste, altrimenti `SchemaBuilder`/`SchemaFromTextExtractor` con materializzazione su `schema.json`.
- **`RetrieverFactory`**: costruisce il retriever di `neo4j-graphrag` corrispondente a `[graph].retriever` (valori ammessi: `vector`, `vector_cypher`, `hybrid`, `hybrid_cypher`, `text2cypher`, `tools`) iniettando driver, embedder, LLM e indici (`vector_index`/`fulltext_index`). Validazione all'avvio (retriever non ammesso → errore; `hybrid*` senza `fulltext_index` → errore). Vedi [graph.md §14](graph.md).

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
- [ ] Creare il sotto-modulo `knowledge_base/graph/` (`KSChunkLoader`, `GraphPipeline`, `ChunkWatcher`, schema manager, `RetrieverFactory`) — vedi [graph.md](graph.md).
- [ ] Spostare i chunk in `<base>/.chunks/` e introduzione ID deterministici (prerequisito F0 del piano GraphRAG).
