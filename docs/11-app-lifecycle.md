# Ciclo di vita dell'app e processo backend

Questo documento descrive come Knowledge Space viene eseguito: entry point, modalità di esecuzione (CLI standalone / backend process), lifecycle del processo, e relazione tra i componenti runtime. Per l'architettura dei pacchetti: vedi [10-architecture.md](10-architecture.md).

---

## 1. Modalità di esecuzione

L'applicazione ha due modalità, che corrispondono a fasi di sviluppo diverse:

| Modalità | Fase | Durata | Watcher | REST | MCP | Stato |
|---|---|---|---|---|---|---|
| **CLI standalone** | Fase 1–3 | Transitoria (un comando) | No (solo `reindex` esplicito) | No | No | Ogni comando è un processo separato |
| **Backend process** | Fase 4+ | Long-running (finché l'utente non chiude l'app) | Sì (watchdog per workspace) | Sì (uvicorn) | Sì (SSE o bridge stdio) | Unico processo, AppContext in memoria |

### CLI standalone (Fase 1–3)

Ogni comando CLI (`ks workspace add`, `ks search`, `ks reindex`, ...) è un **processo separato** che:

1. Costruisce un `AppContext` temporaneo (carica `GlobalIndex`, workspace `state.json`, `BaseConfig` dei TOML).
2. Esegue l'operazione (modifica stato, query Chroma, reindex).
3. Salva lo stato su disco (`state.json`, Chroma).
4. Termina.

Non ci sono processi in background. I watcher watchdog **non sono attivi**. La sincronizzazione col filesystem è esplicita:
- `ks reindex <base>` — reindicizza (auto-detect del trigger: model-change, chunking-change, ingestion-change).
- `ks sync <base>` — allinea `state.json` col filesystem (mtime check).

**Limiti**:
- Le modifiche ai file sorgente non vengono rilevate automaticamente. L'utente deve lanciare `ks sync` o `ks reindex` manualmente.
- Non è possibile servire REST API o MCP.

### Backend process (Fase 4+)

`ks serve` avvia un processo **long-running** che unifica watcher, REST API, MCP SSE e (opzionalmente) frontend. L'AppContext è creato una sola volta e vive in memoria per tutta la durata del processo.

Tutti gli altri comandi CLI (`ks workspace add`, `ks search`, ...) diventano **client** che parlano con il backend via REST API. Se il backend non è attivo, la CLI restituisce errore:

```
$ ks workspace add /path
Error: backend non attivo. Avvia con `ks serve`
```

---

## 2. Entry point

L'entry point è in `knowledge_space/main.py`:

```python
# knowledge_space/main.py

import typer
from knowledge_space.cli import build_cli

def main():
    app = build_cli()
    app()

if __name__ == "__main__":
    main()
```

`build_cli()` costruisce l'albero Typer dei comandi. I comandi si dividono in due categorie:

### Comandi standalone (Fase 1–4)

Funzionano in entrambe le modalità (standalone o, se backend attivo, come client):

| Gruppo | Comandi |
|---|---|
| `workspace` | `add`, `list`, `remove`, `move`, `info` |
| `domain` | `new`, `list`, `remove`, `add-base`, `remove-base`, `auto-generate`, `activate`, `deactivate` |
| `base` | `add`, `list`, `remove`, `info`, `activate`, `deactivate` |
| `file` | `add`, `list`, `remove`, `info`, `activate`, `deactivate` |
| `chunk` | `list`, `show`, `info`, `activate`, `deactivate` |
| `tree` | (no sub) |
| `search` | (no sub) |
| `reindex` | (no sub) |
| `graph` | `init`, `sync`, `re-extract-schema`, `status` |
| `config` | `show`, `validate`, `init` |
| `auth` | `set`, `list`, `remove` |
| `models` | `list`, `info` |
| `status` | (no sub) |

In Fase 1–3 questi comandi operano sempre in modalità standalone. In Fase 4+ verificano se il backend è attivo:
- **Se attivo**: inviano la richiesta via REST (il backend ha i watcher attivi e lo stato in memoria).
- **Se non attivo**: errore (Q1=A: non esiste modalità standalone fallback).

> **Nota implementativa**: in Fase 4+, per semplicità, tutti i comandi possono continuare a operare standalone (leggendo direttamente `state.json` e Chroma come in Fase 1–3), **purché il backend non sia in esecuzione**. Se il backend è attivo, la CLI deve usare REST per evitare race condition su `state.json` (scritture concorrenti). Il rilevamento avviene via PID file + ping `/health` (vedi §4).

### Comandi backend (solo Fase 4+)

| Comando | Azione |
|---|---|
| `serve` | Avvia il backend process (watcher + REST + opz. frontend/MCP) |
| `stop` | Arresta il backend via REST `/shutdown` |

Questi comandi sono disponibili solo a partire dalla Fase 4. In Fase 1–3 non esistono (la CLI è puramente standalone).

---

## 3. Backend process lifecycle

### Avvio (`ks serve`)

```
serve()
├── Leggi PID file (se esiste, controlla se il processo è vivo)
├── build_app_context()          ← AppContext unico per tutto il processo
│   ├── load GlobalIndex
│   ├── for each workspace:
│   │   ├── load state.json
│   │   └── start WorkspaceWatcher (watchdog observer)
│   ├── init Chroma (collection per base)
│   └── init Neo4j (se configurato, skip se non raggiungibile)
├── Scrive PID file
├── Avvia uvicorn:
│   ├── REST API (/api/v1/*)
│   ├── /health endpoint
│   ├── /shutdown endpoint
│   └── Static frontend (/* → React build, opzionale)
├── Se --mcp-sse: avvia endpoint MCP SSE su porta separata o stesso server
├── Se --gui: apre webview (pywebview) o browser a localhost:8000
└── wait (bloccante fino a shutdown)
```

### Watcher watchdog

Il backend avvia un **WorkspaceWatcher** per ogni workspace attivo. Ogni watcher:

- Monitora le cartelle dei file sorgente (non `.knowledge-space/`, non `chunks/`).
- Su `modified` / `created` / `moved` / `deleted` → notifica il `KnowledgeBaseManager` che gestisce il trigger appropriato (content change, move/rename, delete — vedi [45-indexing-incrementale.md](45-indexing-incrementale.md)).
- I watcher sono thread watchdog separati per workspace.

### AppContext nel backend

Singola istanza, condivisa tra:
- Gestori REST (via `fastapi.Depends`)
- Watcher callback (riferimento thread-safe)
- MCP SSE handler

Lo stato in memoria (`AppContext.workspace_manager.current_state` / `AppContext.domain_manager.current_state`) viene flushato su `state.json`:
- **Ad ogni modifica significativa** (add/remove file, reindex, move/rename).
- **Allo shutdown** (garantito dal signal handler, vedi §6).

### Shutdown (`ks stop` o segnale)

```
stop (via REST /shutdown o segnale SIGINT/SIGTERM)
├── Stop accettazione nuove richieste (graceful)
├── Stop MCP SSE se attivo
├── Stop tutti i watcher watchdog
├── Flush stato → state.json (tutti i workspace)
├── Rimuovi PID file
└── Exit
```

`ks stop` invia una richiesta HTTP a `http://localhost:PORT/shutdown`. Il backend esegue lo shutdown graduale.

Se l'utente chiude la finestra (Fase 4, `--gui`), la webview invia `/shutdown` al backend prima di chiudersi.

### Stati del processo

```
         ┌────────────┐
         │   idle     │
         └─────┬──────┘
               │ ks serve
               ▼
         ┌────────────┐
         │  starting   │  ← build_app_context(), start watcher, start uvicorn
         └─────┬──────┘
               │ tutto OK
               ▼
         ┌────────────┐
         │  running   │  ← watchers attivi, REST/MCP in ascolto
         └─────┬──────┘
               │ SIGINT/SIGTERM o /shutdown
               ▼
         ┌────────────┐
         │  stopping  │  ← stop watchers, flush state, remove PID file
         └─────┬──────┘
               │
               ▼
         ┌────────────┐
         │   idle     │
         └────────────┘
```

---

## 4. Rilevamento backend (PID file + health check)

Il backend scrive un PID file all'avvio:

```
~/.local/state/KnowledgeSpace/ks.pid
```

Contenuto: JSON con `pid`, `port`, `host`.

La CLI rileva se il backend è attivo in due passaggi:

1. **Controllo PID file**: se il file esiste, legge PID e controlla se il processo è vivo (`os.kill(pid, 0)`). Se il processo non è vivo → PID file orfano, lo rimuove.
2. **Ping REST**: se il PID è vivo, fa una richiesta GET a `http://localhost:PORT/health`. Se risponde 200 → backend attivo. Se non risponde dopo timeout 2s → backend non attivo (processo in avvio o morto).

Se il backend è attivo, la CLI instrada i comandi via REST. Se non è attivo → errore.

```python
def detect_backend() -> bool:
    pid_path = Path("~/.local/state/KnowledgeSpace/ks.pid").expanduser()
    if not pid_path.exists():
        return False
    data = json.loads(pid_path.read_text())
    try:
        os.kill(data["pid"], 0)  # check if process is alive
    except OSError:
        pid_path.unlink(missing_ok=True)
        return False
    try:
        resp = requests.get(f"http://localhost:{data['port']}/health", timeout=2)
        return resp.status_code == 200
    except requests.RequestException:
        return False
```

---

## 5. Protocollo CLI ↔ backend

La CLI comunica con il backend tramite REST API nello stesso formato usato dal frontend (vedi [97-rest-api.md](97-rest-api.md)). Ogni comando CLI mappa a un endpoint REST:

| Comando CLI | Endpoint REST | Metodo |
|---|---|---|
| `workspace add <path>` | `/api/v1/workspaces` | POST |
| `workspace list` | `/api/v1/workspaces` | GET |
| `workspace remove <path>` | `/api/v1/workspaces/{id}` | DELETE |
| ... | ... | ... |
| `search <query>` | `/api/v1/bases/{base_id}/search` | GET |
| `reindex <base>` | `/api/v1/bases/{base_id}/reindex` | POST |
| ... | ... | ... |

Risposte standard:

```json
{
  "ok": true,
  "result": { ... }
}
```

Errori:

```json
{
  "ok": false,
  "error": "messaggio leggibile",
  "code": "ERROR_CODE"
}
```

---

## 6. Signal handling

Il backend gestisce i segnali Unix per shutdown graduale:

| Segnale | Azione |
|---|---|
| `SIGINT` (Ctrl+C) | Shutdown graduale (stop watcher → flush state → remove PID → exit) |
| `SIGTERM` | Come SIGINT |
| `SIGUSR1` | Reload configurazione (ricarica `defaults.toml`/`base.toml` senza riavviare) — deferred, non implementato in prima release |

Su Windows, equivalenti via `win32api.SetConsoleCtrlHandler` o tramite REST `/shutdown`.

---

## 7. AppContext lifecycle

### CLI standalone (Fase 1–3)

```python
# Per ogni comando CLI:
ctx = build_app_context(runtime_paths=RuntimePaths.load())
# ctx è un'istanza temporanea: carica stato, opera, salva, scade
ctx.workspace_manager.add(Path("/path"))
ctx.workspace_manager.flush()
# ctx esce dallo scope → GC
```

Non c'è condivisione tra comandi successivi. Lo stato persiste su disco (`state.json`, Chroma).

### Backend process (Fase 4+)

```python
ctx = build_app_context(runtime_paths=RuntimePaths.load())
# ctx è l'unica istanza per tutto il processo. Condivisa tra:
#   - REST handlers (via fastapi.Depends)
#   - Watcher callbacks
#   - MCP handlers

# Il contesto non esce mai dallo scope fino a shutdown.
# Le modifiche vengono flushati su state.json periodicamente e su shutdown.
```

### Thread safety

L'`AppContext` è usato da più thread:
- **Thread principale**: uvicorn (REST handlers)
- **Thread watchdog** (uno per workspace): callback su eventi FS
- **Thread MCP SSE**: handler event-stream

L'accesso all'`AppContext` e ai suoi manager è **single-thread asincrono** (uvicorn è async, i callback watchdog sono thread separati). Strategia:

- **State mutation**: solo dal thread principale o tramite `asyncio.run_coroutine_threadsafe()` per sincronizzare con il loop di uvicorn.
- **Watcher callback**: accumula eventi in una coda thread-safe (`queue.Queue`). Il loop principale processa la coda periodicamente (o tramite un scheduler `asyncio`).
- **Chroma**: `PersistentClient` è thread-safe per uso single-process.
- **Neo4j**: il driver `neo4j` è thread-safe.

---

## 8. MCP stdio ↔ REST bridge

`ks mcp` (Fase 4+) è un processo leggero che traduce il protocollo MCP stdio in chiamate REST al backend:

```
[AI Client] ←stdio→ [mcp-server:ks mcp] ←HTTP→ [Backend:ks serve]
```

```python
# mcp_server/server.py (Fase 4+)
# Riceve tool MCP su stdio, traduce in REST API call al backend, restituisce risultato

server = Server("knowledge-space")

@server.list_tools()
async def list_tools():
    return [
        Tool(name="search", description="Cerca chunk", inputSchema={...}),
        Tool(name="list_workspaces", ...),
        ...
    ]

@server.call_tool()
async def call_tool(name, args):
    # Chiama REST API del backend
    resp = requests.post(f"{backend_url}/api/v1/mcp/{name}", json=args)
    return resp.json()
```

L'MCP SSE è invece servito direttamente dal backend (nessun bridge necessario).

---

## 9. Watcher lifecycle

I watcher watchdog sono gestiti dal `WorkspaceManager`:

```python
class WorkspaceManager:
    _watchers: dict[str, WorkspaceWatcher]  # workspace path → watcher

    def start_watcher(self, workspace: Workspace):
        """Avvia un watcher per il workspace. Se già attivo, no-op."""
        ...

    def stop_watcher(self, workspace_path: str):
        """Ferma il watcher per un workspace."""
        ...

    def start_all_watchers(self):
        """Avvia watcher per tutti i workspace attivi."""
        for ws in self.list_active():
            self.start_watcher(ws)

    def stop_all_watchers(self):
        """Ferma tutti i watcher."""
        for path in list(self._watchers.keys()):
            self.stop_watcher(path)
```

Ogni watcher è un thread `watchdog.observer` separato, conosciuto da `WorkspaceManager` per start/stop controllato.

---

## 10. Test

| Test | Cosa verifica |
|---|---|
| Start/stop backend | `ks serve` → PID file creato, `/health` risponde; `ks stop` → PID file rimosso, `/health` non risponde |
| PID file orfano | Kill backend → `ks status` rileva PID morto, rimuove PID file |
| CLI client mode | Backend attivo → CLI instrada via REST; backend fermo → errore |
| Watcher lifecycle | `start_watcher` / `stop_watcher` su workspace, callback verificati con mock |
| State flush | Modifica via REST → `state.json` aggiornato |
| Graceful shutdown | SIGINT → watcher fermati, stato flushato, exit code 0 |
| Signale doppio | SIGINT × 2 → force exit (non bloccato su shutdown) |

---

## 11. Packaging

Decisione differita a Fase 4. L'architettura è compatibile con tutte le opzioni:

| Opzione | Meccanismo | Pro | Contro |
|---|---|---|---|
| **pywebview** (consigliato per tesi) | Python puro, apre una finestra webview nativa (WebKit/WebView2) | Minime dipendenze, bundle unico | Window non "moderna" (no menu nativo, no tray icon) |
| **Tauri** | Rust wrapper + sidecar Python | Finestra moderna, piccolo binary | Richiede Rust toolchain, sidecar Python complesso |
| **Electron** | Node.js + Chromium + child process Python | Finestra moderna, vasto ecosistema | Binary pesante (>100MB), Node.js non necessario |
| **Browser** | `ks serve` + `webbrowser.open()` | Zero dipendenze UI | Nessuna finestra nativa, l'utente vede il browser |

L'entry point dell'eseguibile bundle (AppImage/exe) è:

1. Avvia `ks serve --gui --port 8000` (sottoprocesso Python o processo principale).
2. Apre la finestra (webview o browser) a `http://localhost:8000`.
3. Alla chiusura della finestra, invia `/shutdown` e attende la terminazione.

Il frontend React è compilato come static files e servito dal backend (stessa porta, percorso `/*`).

---

*Ultimo aggiornamento: 21 luglio 2026*
