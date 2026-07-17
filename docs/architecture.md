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
