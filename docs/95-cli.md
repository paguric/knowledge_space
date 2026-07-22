# CLI standalone

Il backend deve poter funzionare autonomamente da riga di comando, senza frontend. La CLI è lo strumento principale per le Fase 1–3 (modalità standalone: ogni comando è un processo separato, niente watcher in background). A partire dalla Fase 4, la CLI diventa client del backend process (vedi [11-app-lifecycle.md](11-app-lifecycle.md) per il funzionamento del backend e la distinzione tra modalità standalone e client).

## Convenzioni generali

- **Nome comando**: `knowledge-space` (canonico). Alias breve: `ks`.
- **Cwd-context**: la CLI rileva il workspace corrente walkando l'albero delle directory alla ricerca della cartella `.knowledge-space/` (stile git). Override con flag globale `--workspace <path>`.
- **Flag globali**:
  - `--help` / `-h` — aiuto del comando o sottocomando
  - `--version` / `-V` — versione del pacchetto
  - `--verbose` / `-v` — output dettagliato (log level DEBUG)
  - `--json` — output machine-readable (JSON)
  - `--workspace <path>` — override del workspace corrente

## Inventario comandi

Tutti i comandi seguono la struttura `knowledge-space <noun> <verb> [args] [flags]` (Typer-style).

### Workspace

| Comando | Descrizione |
|---|---|
| `workspace add <path>` | Registra un workspace (crea `<path>/.knowledge-space/`, sync file esistenti) |
| `workspace list` | Elenca workspace registrati nel `GlobalIndex` |
| `workspace remove <path\|name>` | Rimuove dal `GlobalIndex` (mantiene file utente e cartella `.knowledge-space/`) |
| `workspace move <old> <new>` | Aggiorna il path di un workspace nel `GlobalIndex` (sposta `.knowledge-space/` in `new`) |
| `workspace info [<path>]` | Mostra stato del workspace (cwd o specificato): n. domini, n. basi, n. file, embedding attivi, grafo |

### Domain

| Comando | Descrizione |
|---|---|
| `domain new <name>` | Crea un nuovo dominio nel workspace corrente |
| `domain list` | Elenca domini |
| `domain remove <name>` | Rimuove un dominio (non cancella le basi, solo l'associazione) |
| `domain add-base <name> <base>` | Assegna una base al dominio |
| `domain remove-base <name> <base>` | Rimuove base dal dominio |
| `domain auto-generate` | Genera domini dalla struttura cartelle del workspace (lvl1 = domini, foglie = basi) |
| `domain activate <name>` | Attiva dominio (riattiva basi/file/chunk) |
| `domain deactivate <name>` | Disattiva dominio (spegne basi/file/chunk) |

### Base

| Comando | Descrizione |
|---|---|
| `base add <path>` | Aggiunge una base (cartella) al workspace corrente. Assegna un nome dal nome cartella. Se la cartella contiene già una config `base.toml` valida, la mantiene. Avvia indicizzazione automatica. |
| `base list` | Elenca basi del workspace corrente |
| `base remove <name>` | Rimuove base (cancella `.knowledge-space/` della base? no — lascia intatto, solo deregistra da stato) |
| `base info <name>` | Config effettiva (cascata resolved), modello embedding, n. file, n. chunk, stato grafo |
| `base activate <name>` | Attiva |
| `base deactivate <name>` | Disattiva |

### File

| Comando | Descrizione |
|---|---|
| `file add <path>` | Forza ingestion esplicita di un file (watcher auto-rileva, ma `file add` serve per: forzatura immediata, scripting, validazione pre-auto) |
| `file list [--base <name>]` | Elenca file. Filtra per base se `--base` specificato |
| `file remove <path>` | Rimuove file da indice + vector store + grafo (mantiene file su disco) |
| `file info <path>` | mtime, n. chunk, `file_id`, embedding status, stato grafo |
| `file activate <path>` | Attiva |
| `file deactivate <path>` | Disattiva |

### Chunk

| Comando | Descrizione |
|---|---|
| `chunk list --file <path>` | Elenca chunk di un file (index, chunk_id, active, content_hash) |
| `chunk show <id>` | Stampa il testo del chunk (read-only, i chunk non sono editabili) |
| `chunk info <id>` | Metadati: `content_hash`, embedding model/status, nodo grafo Neo4j |
| `chunk activate <id>` | Attiva |
| `chunk deactivate <id>` | Disattiva |

### Tree

| Comando | Descrizione |
|---|---|
| `tree` | Albero gerarchico: workspace → domain → base → file → chunk |
| `tree --base <name>` | Scope a una base |
| `tree --domain <name>` | Scope a un dominio |
| `tree --json` | Albero in formato JSON (per scripting/UI) |

### Search

Retrieval-only (nessuna generazione). Opera sui chunk indicizzati in Chroma.

| Comando | Descrizione |
|---|---|
| `search <query>` | Ricerca vettoriale (dense/sparse/hybrid da config base) sul workspace corrente |
| `search <query> --base <name>` | Restringe a una base |
| `search <query> --domain <name>` | Restringe a un dominio |
| `search <query> --top-k N` | Override del numero di risultati |
| `search <query> --pre-retrieval identity\|hyde\|multi_query` | Override della strategia di query rewriting |
| `search <query> --reranker identity\|cross_encoder\|llm` | Override del reranker |
| `search <query> --json` | Risultati in formato JSON |

### Reindex

Rileva automaticamente il trigger di reindex confrontando la configurazione attuale (`[embedding].model`, `[chunking].method`, `[ingestion].library`) con i valori registrati in `state.json`. Il reindex può anche essere attivato implicitamente da `config set` quando modifica una delle chiavi sensibili.

| Comando | Descrizione |
|---|---|
| `reindex <base>` | Auto-detect del trigger: confronta i valori attuali (dalla cascata TOML) con quelli registrati in `state.json`. Decide il trigger (model-change, chunking-change, ingestion-change) e reindicizza. |
| `reindex --all` | Reindex tutte le basi del workspace |

### Graph

Comandi per la gestione del grafo Neo4j (Fase 1C). Richiedono Neo4j configurato in `graph.json`.

| Comando | Descrizione |
|---|---|
| `graph init` | Crea indici Neo4j (vector index + fulltext index), idempotente |
| `graph sync` | Propaga al grafo i cambiamenti pending (per basi con `on_chunk_change = "lazy"`) |
| `graph re-extract-schema` | Forza re-estrazione dello schema (cancella `graph/schema.json`, esegue `SchemaBuilder` o `SchemaFromTextExtractor`) |
| `graph status` | Stato del grafo: connessione bolt, n. nodi Chunk/Document/Entity, n. relazioni, presenza schema |

### Config

| Comando | Descrizione |
|---|---|
| `config show [<base>]` | Mostra la configurazione effettiva (cascata resolved: hardcoded → `defaults.toml` → `base.toml`). Se base omessa, mostra quella del workspace (`defaults.toml`). |
| `config validate [<base>]` | Valida la sintassi TOML del `base.toml` o del `defaults.toml`. Segnala campi sconosciuti e valori fuori range. |
| `config init` | Genera `<workspace>/.knowledge-space/defaults.toml` come template dai valori hardcoded di KS (one-shot; KS non riscrive TOML a runtime). |
| `config set <base\|defaults> <key> <value>` | Imposta una preferenza nel TOML specificato. `key` è un percorso dotted (es. `chunking.chunk_size`, `embedding.model`, `ingestion.library`). I valori booleani accettano `true`/`false`, i numerici vengono parsati automaticamente, le stringhe richiedono quoting solo se contengono spazi. Se la chiave modifica `embedding.model`, `chunking.method` o `ingestion.library` su una base con collection Chroma non vuota, il comando chiede conferma e avvia automaticamente il reindex appropriato (re-embed, re-chunk, re-ingest). **Autocompletamento**: `<TAB>` sul parametro `key` suggerisce i percorsi dotted validi (es. `chunking.` → `chunking.chunk_size`, `chunking.chunk_overlap`, `chunking.method`); sul parametro `value` suggerisce i valori ammissibili per la chiave corrente (es. `ingestion.library ` → `docling`, `pymupdf4llm`, `markitdown`; `chunking.method ` → `fixed_size`, `recursive`, `semantic`, `sentence`, `markdown`). |
| `config unset <base\|defaults> <key>` | Rimuove una chiave dal TOML (la base tornerà a ereditare da `defaults.toml` o dal valore hardcoded). **Autocompletamento** come per `config set`. |
| `config edit <base\|defaults>` | Apre il file TOML nell'editor predefinito (`$EDITOR` / `$VISUAL`) — utility per la modifica manuale senza uscire dalla CLI. |

### Auth

Opera su `~/.config/KnowledgeSpace/config.json` (secrets, chiavi API). File machine-writable ma anche editabile manualmente dall'utente.

| Comando | Descrizione |
|---|---|
| `auth set <key> <value>` | Scrive una chiave (es. `auth set openai_api_key sk-...`, `auth set hf_token hf_xxxx`) |
| `auth list` | Elenca le chiavi memorizzate (valori mascherati) |
| `auth remove <key>` | Rimuove una chiave |

### Models (discovery)

| Comando | Descrizione |
|---|---|
| `models list` | Elenca tutti i modelli di embedding registrati nel registry, con metadati: `model_name`, `languages`, `dim`, `max_context_tokens`, `license`, `requires_api` |
| `models list --local` | Solo modelli locali (`requires_api = false`) |
| `models list --remote` | Solo modelli remoti (`requires_api = true`) |
| `models info <name>` | Dettaglio completo di un modello (es. `models info "BAAI/bge-m3"`) |

### Status

| Comando | Descrizione |
|---|---|
| `status` | Panoramica: workspace attivo, n. basi/file/chunk, embedding model predefinito, stato grafo (connesso/non configurato/errore). In Fase 4+ mostra anche stato backend e watcher. |

### Server (da implementare in Fase 4)

| Comando | Descrizione |
|---|---|
| `serve` | Avvia il backend process (watcher + REST API + opz. frontend/MCP). Vedi [11-app-lifecycle.md](11-app-lifecycle.md) e [97-rest-api.md](97-rest-api.md). |
| `serve --gui` | Avvia backend + apre finestra webview (pywebview) |
| `serve --host 0.0.0.0 --port 8000` | Override bind |
| `serve --mcp-sse --mcp-port 8001` | Espone MCP SSE |
| `serve --no-watchers` | Backend senza FS monitoring (debug) |
| `stop` | Arresta il backend via REST `/shutdown`. Vedi [11-app-lifecycle.md §3](11-app-lifecycle.md#3-backend-process-lifecycle). |
| `mcp` | Avvia MCP in modalità stdio (bridge verso backend REST). Vedi [11-app-lifecycle.md §8](11-app-lifecycle.md#8-mcp-stdio--rest-bridge) e [96-mcp-server.md](96-mcp-server.md). |

### Profili (da definire in Fase 2)

I comandi relativi ai profili (`profiles list`, `profile apply <name> <base>`, ...) saranno progettati in Fase 2. Vedi [92-roadmap-fase2.md](92-roadmap-fase2.md) per lo stato della discussione.

## Struttura Typer

La CLI è implementata con Typer, usando `AppContext` come dipendenza (vedi [91a-roadmap-fase1-ingestione.md Step 8-ter](91a-roadmap-fase1-ingestione.md) per il wiring). Typer fornisce shell completion nativa (`--install-completion`, `--show-completion`).

### Autocompletamento per `config set` e `config unset`

I parametri `key` e `value` dei comandi `config set`/`unset` implementano shell completion custom:

- **`key`**: suggerisce i percorsi dotted validi ricavati dal registry delle strategie e dallo schema di configurazione. Supporta abbreviazioni: `chunk` → `chunking.`, `ingest` → `ingestion.`, `embed` → `embedding.`, `pre` → `pre_retrieval.`, `post` → `post_retrieval.`. Esempi:
  - `chunking.` → `chunking.chunk_size`, `chunking.chunk_overlap`, `chunking.method`, `chunking.separator`
  - `embedding.` → `embedding.model`, `embedding.device`
  - `ingestion.` → `ingestion.library`
- **`value`**: una volta fornita la `key`, suggerisce i valori ammissibili:
  - `ingestion.library ` → `docling`, `pymupdf4llm`, `markitdown`, `identity`
  - `chunking.method ` → `fixed_size`, `recursive`, `semantic`, `sentence`, `markdown`
  - Valori booleani → `true`, `false`
  - Per campi generici (es. `chunking.chunk_size`) nessun suggerimento (valore numerico libero).

```python
import typer
from knowledge_space.context import AppContext

app = typer.Typer(help="Knowledge Space — CLI per gestione basi di conoscenza")

# Flag globali nascosti nei gruppi, applicati da build_app_context()
_ctx: AppContext | None = None

def get_ctx() -> AppContext:
    global _ctx
    if _ctx is None:
        _ctx = build_app_context()
    return _ctx

# === Workspace ===
workspace_app = typer.Typer(help="Gestione workspace")
app.add_typer(workspace_app, name="workspace")

@workspace_app.command("add")
def workspace_add(path: str = typer.Argument(...)):
    """Registra un nuovo workspace."""
    ctx = get_ctx()
    ctx.workspace_manager.add(path)
    ...

# === Search ===
@app.command()
def search(
    query: str = typer.Argument(...),
    base: str | None = typer.Option(None, "--base"),
    top_k: int = typer.Option(5, "--top-k"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Ricerca vettoriale sui chunk."""
    ctx = get_ctx()
    results = ctx.search_service.search(query=query, ...)
    if json_output:
        typer.echo(json.dumps([r.model_dump() for r in results]))
    else:
        for r in results:
            typer.echo(f"[{r.score:.3f}] {r.chunk_id}: {r.text[:200]}...")
```

---

*Ultimo aggiornamento: 21 luglio 2026*
