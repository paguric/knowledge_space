---
title: Server MCP
status: non_iniziato
step: 14
fase: 3
updated: 2026-07-22
---

# Server MCP

## Decisioni chiave

| Aspetto | Scelta |
|---------|--------|
| Trasporto default | stdio (Fase 3), SSE opzionale |
| Dipendenze | `knowledge-base` (non `knowledge-space`) |
| Fase 3 | Processo standalone |
| Fase 4+ | Bridge verso REST backend |

## Protocollo e trasporto

MCP supporta principalmente due modalità:

- **stdio**: il server legge da stdin e scrive su stdout. Default per client come Claude Desktop.
- **SSE (Server-Sent Events)**: il server espone un endpoint HTTP.

### Scelta consigliata

Iniziare con **stdio** tramite SDK ufficiale `mcp`. In un secondo momento aggiungere SSE come opzione.

## Tools MCP da esporre

- `list_workspaces` → restituisce i workspace registrati.
- `add_workspace(path)` → aggiunge un workspace.
- `remove_workspace(name)` → rimuove un workspace.
- `list_bases(workspace)` → elenca le knowledge base di un workspace.
- `add_base(workspace, path)` → aggiunge una knowledge base.
- `search(query, workspace?, base?)` → ricerca semantica.
- `add_file(workspace, base, path)` → indicizza un file.
- `get_config()` → mostra la configurazione attiva (senza secrets).

## Struttura del pacchetto

```
packages/mcp-server/src/mcp_server/
├── __init__.py
├── server.py            # entrypoint MCP
├── config.py            # inizializza AppContext
├── tools.py             # definizione dei tool
└── __main__.py          # python -m mcp_server
```

## Riutilizzo della logica

Il server MCP non deve reimplementare la logica. Deve usare gli stessi **service** di `knowledge-base`:

```python
from knowledge_base.services import WorkspaceService, KnowledgeBaseService
```

In questo modo ogni modifica ai service si riflette automaticamente sia su REST che su MCP.
