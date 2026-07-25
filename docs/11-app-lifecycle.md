# Ciclo di vita dell'app e processo backend

> **Stato:** non iniziato | **Step:** 8-ter | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Decisioni chiave

| Aspetto | Scelta |
|---------|--------|
| Fase 1-3 | CLI standalone (ogni comando = processo separato) |
| Fase 4+ | Backend process long-running (watcher + REST + MCP) |
| Rilevamento backend | PID file + ping `/health` |
| Thread safety | State mutation dal thread principale, callback via coda thread-safe |
| MCP stdio (Fase 4+) | Bridge verso REST, non standalone |
| Shutdown | SIGINT/SIGTERM → graceful (stop watcher → flush state → remove PID) |
| Packaging | pywebview (consigliato) / Tauri / Electron / browser |

## Obiettivo

Descrivere come Knowledge Space viene eseguito: entry point, modalità di esecuzione (CLI standalone / backend process), lifecycle del processo, e relazione tra i componenti runtime.

## Modalità di esecuzione

| Modalità | Fase | Durata | Watcher | REST | MCP |
|---|---|---|---|---|---|
| **CLI standalone** | 1–3 | Transitoria (un comando) | No | No | No |
| **Backend process** | 4+ | Long-running | Sì | Sì | Sì |

### CLI standalone (Fase 1–3)

Ogni comando è un **processo separato** che:
1. Costruisce un `AppContext` temporaneo
2. Esegue l'operazione
3. Salva lo stato su disco
4. Termina

Non ci sono processi in background. I watcher non sono attivi. La sincronizzazione col filesystem è esplicita (`ks reindex`, `ks sync`).

### Backend process (Fase 4+)

`ks serve` avvia un processo **long-running** che unifica watcher, REST API, MCP SSE e (opzionalmente) frontend.

```
serve()
├── build_app_context()
│   ├── load GlobalIndex
│   ├── for each workspace: load state.json + start WorkspaceWatcher
│   ├── init Chroma
│   └── init Neo4j (se configurato)
├── Scrive PID file
├── Avvia uvicorn (REST + /health + /shutdown)
├── Se --mcp-sse: avvia endpoint MCP SSE
└── wait (bloccante fino a shutdown)
```

## Entry point

```python
# knowledge_space/main.py
import typer
from knowledge_space.cli import build_cli

def main():
    app = build_cli()
    app()
```

## Rilevamento backend (PID file)

Il backend scrive un PID file all'avvio: `~/.local/state/KnowledgeSpace/ks.pid`

La CLI rileva se il backend è attivo:
1. Controllo PID file → processo vivo?
2. Ping REST `GET /health` → risponde 200?

Se attivo → CLI instrada via REST. Se non attivo → errore.

## Backend lifecycle

### Watcher watchdog

Un **WorkspaceWatcher** per ogni workspace attivo:
- Monitora le cartelle dei file sorgente (non `.knowledge-space/`)
- Su `modified`/`created`/`moved`/`deleted` → notifica il `KnowledgeBaseManager`

### Shutdown (`ks stop` o segnale)

```
stop (via REST /shutdown o SIGINT/SIGTERM)
├── Stop accettazione nuove richieste
├── Stop MCP SSE se attivo
├── Stop tutti i watcher
├── Flush stato → state.json
├── Rimuovi PID file
└── Exit
```

### Signal handling

| Segnale | Azione |
|---------|--------|
| `SIGINT` (Ctrl+C) | Shutdown graduale |
| `SIGTERM` | Come SIGINT |
| `SIGUSR1` | Reload config (deferred) |

## Protocollo CLI ↔ backend

| Comando CLI | Endpoint REST | Metodo |
|---|---|---|
| `workspace add <path>` | `/api/v1/workspaces` | POST |
| `workspace list` | `/api/v1/workspaces` | GET |
| `search <query>` | `/api/v1/bases/{id}/search` | GET |
| `reindex <base>` | `/api/v1/bases/{id}/reindex` | POST |

Risposte: `{"ok": true, "result": {...}}` / `{"ok": false, "error": "...", "code": "..."}`

## AppContext lifecycle

### CLI standalone (Fase 1–3)

```python
ctx = build_app_context()  # temporaneo
ctx.workspace_manager.add(Path("/path"))
ctx.workspace_manager.flush()
# ctx esce dallo scope → GC
```

### Backend process (Fase 4+)

```python
ctx = build_app_context()  # unica istanza per tutto il processo
# Condivisa tra: REST handlers, watcher callbacks, MCP handlers
```

## MCP stdio ↔ REST bridge

`ks mcp` (Fase 4+) traduce MCP stdio in chiamate REST:

```
[AI Client] ←stdio→ [mcp-server] ←HTTP→ [Backend: ks serve]
```

## Packaging

| Opzione | Meccanismo | Pro | Contro |
|---------|-----------|-----|--------|
| **pywebview** | Python puro, finestra webview nativa | Minime dipendenze | Window non "moderna" |
| **Tauri** | Rust wrapper + sidecar Python | Finestra moderna | Richiede Rust toolchain |
| **Electron** | Node.js + Chromium | Finestra moderna | Binary pesante (>100MB) |
| **Browser** | `ks serve` + `webbrowser.open()` | Zero dipendenze UI | Nessuna finestra nativa |

## Test

| Test | Cosa verifica |
|------|---------------|
| Start/stop backend | PID file creato/rimosso, `/health` risponde |
| PID file orfano | Kill backend → PID morto rilevato, PID rimosso |
| CLI client mode | Backend attivo → REST; backend fermo → errore |
| Watcher lifecycle | `start_watcher`/`stop_watcher` su workspace |
| Graceful shutdown | SIGINT → watcher fermi, stato flushato, exit 0 |

## Dipendenze

- **Dipende da:** Step 8-ter (AppContext), Step 12 (logging)
- **Usato da:** Step 13 (CLI), Step 14 (MCP), Step 15 (REST)

---

*Ultimo aggiornamento: 22 luglio 2026*
