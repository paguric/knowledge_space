# Server MCP

> **Stato:** non iniziato | **Step:** 14 | **Fase:** 3 | **Aggiornato:** 22 luglio 2026

## Panoramica

Server MCP (Model Context Protocol) per interrogare i workspace. In Fase 3 opera come processo standalone; in Fase 4+ diventa bridge verso il backend REST.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Trasporto default | stdio (Fase 3), SSE opzionale |
| SDK | `mcp` (ufficiale) |
| Dipendenze | `knowledge-base` (non `knowledge-space`) |
| Fase 3 | Processo standalone |
| Fase 4+ | Bridge verso REST backend |

## Dettagli

### Protocollo e trasporto

- **stdio**: il server legge da stdin e scrive su stdout. Default per client come Claude Desktop.
- **SSE (Server-Sent Events)**: endpoint HTTP. Opzionale con `--sse --port 8001`.

### Tools MCP da esporre

| Tool | Descrizione |
|------|-------------|
| `list_workspaces` | Workspace registrati |
| `add_workspace(path)` | Aggiunge workspace |
| `remove_workspace(name)` | Rimuove workspace |
| `list_bases(workspace)` | Knowledge base di un workspace |
| `add_base(workspace, path)` | Aggiunge knowledge base |
| `search(query, workspace?, base?)` | Ricerca semantica |
| `add_file(workspace, base, path)` | Indicizza file |
| `get_config()` | Configurazione attiva (senza secrets) |

### Struttura pacchetto

```
packages/mcp-server/src/mcp_server/
├── __init__.py
├── server.py            # entrypoint MCP
├── config.py            # inizializza AppContext
├── tools.py             # definizione dei tool
└── __main__.py          # python -m mcp_server
```

### Riutilizzo della logica

Il server MCP usa gli stessi service di `knowledge-base`:

```python
from knowledge_base.services import WorkspaceService, KnowledgeBaseService
```

### Ciclo di vita

| Fase | Modalità | Funzionamento |
|------|----------|---------------|
| Fase 3 | Standalone | Carica AppContext direttamente, opera su state.json/Chroma |
| Fase 4+ | Bridge | Traduce MCP stdio → chiamate REST al backend |

### Fasi di implementazione

- [ ] Aggiungere `mcp` alle dipendenze
- [ ] Rimuovere `mcp-server` da `knowledge-space`, aggiungere `knowledge-base` come dipendenza
- [ ] Implementare `server.py` con trasporto stdio
- [ ] Implementare tools MCP
- [ ] Aggiungere SSE opzionale
- [ ] Test

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 8-ter (AppContext) | Step 17 (polish) |
