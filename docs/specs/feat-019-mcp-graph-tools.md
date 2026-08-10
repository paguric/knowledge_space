# Feature 019 — Tool MCP per il grafo

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** bassa (dopo feat-016/017/018)

## Obiettivo

Esporre il grafo di conoscenza come tool MCP, così gli agenti possono interrogarlo (retrieval su grafo + stato).

## Causa

`packages/mcp-server/src/mcp_server/server.py` espone tool per base/file/ricerca ma nessun tool graph, nonostante la libreria `graph/retriever.py` abbia 6 retriever già testati.

## Fix (KISS)

1. **Tool MCP nuovi** in `server.py`:
   - `graph_status(workspace)` — connessione Neo4j + conteggi (basi, chunk, entità, relazioni).
   - `graph_search(workspace, query, base=None, top_k=5)` — `RetrieverFactory.build(...)` col retriever configurato in `[graph].retriever` (default `hybrid_cypher`); ritorna chunk + contesto grafo (entità collegate).
   - `graph_sync(workspace, base=None)` — delega a `GraphManager.sync_base`.
2. **Gating**: `graph.enabled == false` → errore tool `"Grafo disabilitato"`.
3. **Dipendenze lazy**: `neo4j` importato solo quando il tool viene chiamato.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/mcp-server/src/mcp_server/server.py` | 3 tool graph |

### Verifica

```bash
# Client MCP: chiamare graph_search su ~/ws2
curl -N http://127.0.0.1:8080/sse  # oppure client MCP
# → risposta con chunk + entità collegate
```
