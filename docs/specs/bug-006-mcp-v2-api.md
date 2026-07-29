# Bug 006 — Server MCP crasca: `on_list_tools` non esiste in MCP 2.0.0

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare
**Priorità:** alta (bloccante per `ks serve`)

## Sintomo

```
'Server' object has no attribute 'on_list_tools'
```

`ks serve` esce con errore prima di poter accettare connessioni MCP.

## Causa radice

In `packages/mcp-server/src/mcp_server/server.py`:

```python
@server.on_list_tools  # type: ignore[attr-defined]
async def _list_tools(...):
    ...

@server.on_call_tool  # type: ignore[attr-defined]
async def _call_tool(...):
    ...
```

I decoratori `on_list_tools` e `on_call_tool` sono API di **MCP 1.x**.
L'ambiente ha installato **MCP 2.0.0** (`uv pip show mcp` → `Version: 2.0.0`).
In MCP 2.0 i metodi `on_list_tools`/`on_call_tool` **non esistono** più.

In MCP 2.0 l'API è:
```python
from mcp.server import Server
from mcp import ListToolsRequest, ListToolsResult, CallToolRequest, CallToolResult

server.add_request_handler(ListToolsRequest, async handler)
server.add_request_handler(CallToolRequest, async handler)
```

(Se esiste `FastMCP` in 2.0, potrebbe semplificare. Altrimenti usare `add_request_handler`.)

## Fix atteso

1. Riscrivere `_make_server()` in `server.py` per usare l'API MCP 2.0:
   - `ListToolsRequest` → `_list_tools`
   - `CallToolRequest` → `_call_tool`
2. Aggiornare gli import da `mcp.types` se necessario.
3. Verificare che SSE e stdio funzionino entrambi.

## Verifica

- `uv run pytest packages/mcp-server/tests/ -q` → verde.
- `ks serve --help` → funziona senza errore.
- `ks serve &` → resta attivo e non esce con errore.
- Log mostra "Server MCP in avvio" senza stacktrace.

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Al termine: riportare branch, file cambiati, risultato test.
