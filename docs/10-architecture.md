# Architettura e organizzazione dei pacchetti

> **Stato:** in progress | **Aggiornato:** 22 luglio 2026

## Panoramica

Organizzazione del monorepo in 3 pacchetti con separazione delle responsabilità: `knowledge-base` (libreria pura), `knowledge-space` (app layer: CLI, REST, bootstrap), `mcp-server` (server MCP). La regola d'oro è che `knowledge-base` non conosce HTTP, MCP, CLI o variabili globali.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Monorepo | Workspace uv con 3 pacchetti |
| `knowledge-base` | Libreria pura (no XDG, no CLI, no API) |
| `knowledge-space` | App layer (CLI, REST, bootstrap) |
| `mcp-server` | Server MCP (stdio/SSE) |
| Regola d'oro | `knowledge-base` non conosce HTTP, MCP, CLI o variabili globali |
| GraphRAG | Modulo `knowledge_base/graph/`, driver iniettato |
| Iniezione dipendenze | `AppContext` a livello di applicazione |

## Dettagli

### Organizzazione del monorepo

```
knowledge_space/
├── packages/
│   ├── knowledge-base/     # libreria pura (no XDG, no CLI, no API)
│   │   ├── src/knowledge_base/
│   │   │   ├── models.py
│   │   │   ├── persistence.py
│   │   │   ├── workspace_manager.py
│   │   │   ├── domain_manager.py
│   │   │   ├── knowledge_base_manager.py
│   │   │   ├── base_config.py
│   │   │   └── strategies/
│   │   │       ├── ingestion.py
│   │   │       ├── chunking.py
│   │   │       ├── embedding.py
│   │   │       └── llm.py
│   │   └── tests/
│   ├── mcp-server/         # server MCP (dipende da knowledge-base)
│   └── knowledge-space/    # app layer (CLI, REST, bootstrap)
│       ├── src/knowledge_space/
│       │   ├── constants.py
│       │   ├── runtime_paths.py
│       │   ├── context.py        # AppContext (Step 8-ter)
│       │   └── bootstrap.py      # build_app_context (Step 8-ter)
│       └── tests/
├── docs/
└── pyproject.toml          # workspace uv
```

### Separazione delle responsabilità

| Pacchetto | Responsabilità | Dipende da |
|-----------|---------------|------------|
| `knowledge-base` | Modelli, persistenza, manager, strategy registry, pipeline retrieval/grafo | Nessun riferimento a XDG, CLI, API |
| `knowledge-space` | `RuntimePaths`, `AppContext`, CLI, REST API, bootstrap | `knowledge-base` |
| `mcp-server` | Server MCP (stdio/SSE) | `knowledge-base` |

### Visione architetturale

```
┌─────────────────────────────────────────────────────────────┐
│                    knowledge-base (library)                  │
│  - domain: Workspace, KnowledgeBase, Chunk, File, Domain      │
│  - services: WorkspaceManager, KnowledgeBaseManager, Search   │
│  - persistence: GlobalIndex, WorkspaceConfig                  │
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

### Modulo `knowledge_base/graph/`

Sotto-modulo per la pipeline GraphRAG (Step 8-bis, Fase 1C). Rispetta la regola d'oro: riceve esplicitamente il driver Neo4j, l'embedder, la connessione Chroma e la configurazione.

**Componenti previsti:**
- **`KSChunkLoader`**: legge chunk da disco + embedding da Chroma. Espone `upsert_chunks()` per propagazione incrementale.
- **`GraphPipeline`**: assemblaggio `KSChunkLoader → schema → LLMEntityRelationExtractor → Neo4jWriter → EntityResolver`.
- **Schema manager**: caricamento `GraphSchema.from_file` se esiste, altrimenti costruzione + materializzazione.
- **`RetrieverFactory`**: costruisce il retriever corrispondente a `[graph].retriever`.

### Pattern architetturali

- **Strategy/plugin pattern** per ingestion, chunking, embedding, retrieval, LLM
- **Registry** discoverable per ogni strategy (nome + parametri + metadati)
- **AppContext** come unico punto di dependency injection
- **Nessuna variabile globale** — tutto passato esplicitamente

### Fasi di implementazione

- [x] Step 0-7: Modelli, persistenza, manager, strategy (Fase 1A)
- [ ] Step 8-ter: AppContext e bootstrap
- [ ] Step 8: Pipeline retrieval (Fase 1B)
- [ ] Step 8-bis: Pipeline GraphRAG (Fase 1C)

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Nessuno (fondamenta) | Tutti gli altri step |
