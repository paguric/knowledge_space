# Knowledge Space

Pipeline di ingestione, indicizzazione e retrieval su documenti. Architettura modulare con strategy pattern per ingestion, chunking, embedding e retrieval.

## Installazione

Il progetto gestisce le dipendenze via `uv`. È necessario installarlo prima di poter procedere con l'installazione:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
# Clona il repo
git clone <repo-url>
cd knowledge_space

# Installazione system-wide via uv
uv sync
uv tool install -e .
```

**Librerie di conversione opzionali** (lazy install, al primo utilizzo):
docling e pymupdf4llm non vengono installate di default (markitdown è la
libreria di default ed è sempre installata). Per abilitarle:

```bash
uv sync --extra docling --extra pymupdf4llm
uv tool install --editable --force --refresh ".[docling,pymupdf4llm]"
```

Se una libreria manca, `ks file add` solleva un errore con il comando
esatto da eseguire.

### GPU con docling (opzionale)

Di default il progetto installa **torch CPU-only** (canale
`download.pytorch.org/whl/cpu`, via `[tool.uv.sources]` in `pyproject.toml`):
~4 GB in meno di librerie CUDA. Per usare la GPU con docling (OCR, layout,
tabelle — serve `use_gpu = true` nel TOML `[ingestion].params`):

1. In `pyproject.toml` commenta la riga `torch = { index = "pytorch-cpu" }`
   e tutta la sezione `[[tool.uv.index]]` (il torch CUDA torna da PyPI).
2. Sincronizza con docling e reinstalla il tool globale:

```bash
uv sync --extra docling
uv tool install --editable --force --refresh ".[docling]"
systemctl --user restart ks-serve
```

> Nota: il canale CPU si applica solo se `torch` è dipendenza **diretta**
> del progetto (per questo sta in `[project.dependencies]` con vincolo
> `>=2.0`): le source uv non si applicano alle dipendenze transitive
> (torch arriva da sentence-transformers).

## Aggiornamento

```bash
cd knowledge_space
git pull
uv sync
uv tool install --editable --force --refresh .

```

Per ricaricare il server MCP, se hai avviato il server a mano con `ks serve`:

```bash
# in foreground: Ctrl+C nella finestra del server
# in background:
pkill -f "ks serve"

# poi rilancia
ks serve
```

Se attivato come **systemd user service** (vedi sotto):

```bash
systemctl --user daemon-reload
systemctl --user restart ks-serve
```

## Database a grafo (opzionale, per il modulo Graph)

Il modulo Graph (grafo della conoscenza, `ks graph`) richiede un'istanza
**Neo4j** (non embedded). L'opzione più semplice è Docker:

```bash
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/tua-password neo4j:5-community
```

**Nota:** la password dev'essere lunga almeno 8 caratteri.

- Porta `7687` = protocollo **Bolt** (usato dal programma) · `7474` = browser
  (http://localhost:7474).
- Alternative: tarball nativo (neo4j.com), Neo4j Desktop (Windows/macOS),
  AuraDB cloud.

**Driver Python** (installazione opzionale, come docling — non incluso di
default):

```bash
uv sync --extra neo4j
uv tool install --editable --force --refresh ".[neo4j]"
systemctl --user restart ks-serve   # se usi il servizio
```

Se il driver manca, `ks graph` solleva un errore con il comando esatto da
eseguire.

La connessione si specifica con variabili d'ambiente (nessuna password nei
file di configurazione):

```bash
export NEO4J_URI="bolt://localhost:7687"   # default
export NEO4J_USER="neo4j"                  # default
export NEO4J_PASSWORD="la-tua-password"
```

Al primo `ks graph init -w <workspace>` la connessione viene registrata in
`<workspace>/.knowledge-space/graph/graph.json` (uri e database; la
password resta solo nelle env var).

## Avvio automatico del server

`ks serve` avvia il server MCP e attiva i watcher filesystem su tutti i workspace
registrati: qualsiasi modifica al filesystem (file aggiunti, spostati, rimossi)
viene rilevata in tempo reale e sincronizzata automaticamente.

Se non si vuole avviare ogni volta manualmente, su Linux il modo più semplice per impostare l'avvio automatico è un **systemd user service**:

```bash
# 1. Abilita il linger per avviare servizi senza login
loginctl enable-linger $USER

# 2. Crea il file di servizio
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/ks-serve.service << 'EOF'
[Unit]
Description=Knowledge Space — MCP server + watcher

[Service]
# Usa --sse perché stdio richiede un terminale (non funziona con systemd).
# Usa 'uv run' dalla directory del progetto così ha tutte le dipendenze.
ExecStart=/usr/bin/bash -c 'cd "$HOME/università/as25-26-sp/progtes/knowledge_space" && uv run ks serve --sse'
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

# 3. Abilita e avvia
systemctl --user daemon-reload
systemctl --user enable --now ks-serve
```

Comandi utili:

```bash
systemctl --user status ks-serve   # stato del servizio
journalctl --user -u ks-serve -f   # log in tempo reale
systemctl --user restart ks-serve  # riavvia
systemctl --user stop ks-serve     # ferma
```

> **Nota:** `$HOME` in ExecStart si espande nella home dell'utente. La directory
> del progetto deve essere allineata con il path indicato (modifica il percorso
> se il repo è altrove).

## Client MCP (es. Claude Code)

Il server MCP è raggiungibile all'endpoint:

```
http://127.0.0.1:8456/knowledge-space/mcp
```

**Tool disponibili:** `base_list`, `domain_list`, `search`.

### Claude Code

```bash
claude mcp add --transport http knowledge-space \
  http://127.0.0.1:8456/knowledge-space/mcp
```

Oppure in `.mcp.json` (progetto) / `~/.claude.json` (globale):

```json
{
  "mcpServers": {
    "knowledge-space": {
      "type": "http",
      "url": "http://127.0.0.1:8456/knowledge-space/mcp"
    }
  }
}
```

**Requisiti:** il servizio `ks-serve` deve essere attivo e un workspace
attivo (`ks workspace activate <path>`). Verifica con:

```bash
ks status          # deve mostrare [attivo]
```

## Utilizzo rapido

```bash
# Mostra tutti i comandi disponibili
ks --help

# 1. Registra un workspace
ks workspace add /path/to/my-workspace

# 2. Aggiungi una base di conoscenza (cartella con documenti)
ks base add /path/to/my-workspace/documents

# 3. Ingestisci un file
ks file add documents /path/to/document.pdf

# 4. Cerca
ks search "qual è la procedura per..."

# 5. Visualizza la struttura
ks tree
```

## Comandi principali

### Workspace

```bash
ks workspace add <path>          # Registra workspace
ks workspace list                # Elenca workspace registrati
ks workspace remove <path>       # Rimuove workspace
ks workspace info                # Mostra workspace attivo
```

### Basi di conoscenza

```bash
ks base add <path>               # Aggiunge base (cartella)
ks base list                     # Elenca basi del workspace
ks base remove <name>            # Rimuove base
ks base info <name>              # Config e statistiche
```

### File

```bash
ks file add <base> <path>        # Ingestisce un file nella base
ks file list                     # Elenca tutti i file
ks file list --base <name>       # File di una base specifica
ks file remove <base> <name>     # Rimuove file dalla base
```

### Ricerca

```bash
ks search "query"                # Ricerca vettoriale
ks search "query" --base <name>  # Filtra per base
ks search "query" --top-k 20     # Più risultati
ks search "query" --json         # Output JSON
```

### Struttura

```bash
ks tree                          # Albero completo
ks tree --base <name>            # Scope a una base
ks tree --json                   # Output JSON
```

### Configurazione

```bash
ks config show                   # Config risolta del workspace
ks config show <base>            # Config di una base
ks config init                   # Genera defaults.toml template
```

### Modelli

```bash
ks models list                   # Elenca modelli embedding
ks models info <name>            # Dettaglio modello
```

## Configurazione LLM

Non esiste una sezione `[llm]` globale: **ogni componente** che usa un LLM
sceglie il proprio modello nel TOML (cascata per-base), nel parametro
`model` del suo stadio. Tutti i provider sono **endpoint compatibili con
il formato OpenAI** (una sola implementazione): cambiano solo URL e chiave.

### Provider supportati

| Prefisso | Endpoint | API key / URL |
|---|---|---|
| `lm-studio/<modello>` | LM Studio locale | `http://localhost:1234/v1` (override: `LM_STUDIO_BASE_URL`), nessuna chiave |
| `openai-compatible/<modello>` | qualsiasi endpoint OpenAI-compatibile | `OPENAI_COMPATIBLE_API_KEY` + `OPENAI_COMPATIBLE_BASE_URL` |

`lm-studio/auto` rileva automaticamente il primo modello caricato nel
server LM Studio. Abbreviazione utile: `local` → `lm-studio/auto`.

### LM Studio (locale)

1. Avvia LM Studio e carica un modello (es. Qwen2.5-7B-Instruct).
2. Nel server LM Studio: `Settings → Developer` e avvia il server locale
   (porta 1234 di default).
3. Configura lo stadio che vuoi nel `defaults.toml` del workspace
   (o `base.toml` della base):

```toml
[pre_retrieval]
stages = [
  { method = "multi_query", params = { model = "lm-studio/auto", n = 3 } },
]
```

### Provider remoto (es. OpenRouter, OpenAI, vLLM)

Ogni endpoint che espone l'API chat completions in formato OpenAI si usa
col prefisso `openai-compatible/` + due env var:

```bash
# Esempio OpenRouter
export OPENAI_COMPATIBLE_BASE_URL="https://openrouter.ai/api/v1"
export OPENAI_COMPATIBLE_API_KEY="sk-or-..."

# Esempio OpenAI
export OPENAI_COMPATIBLE_BASE_URL="https://api.openai.com/v1"
export OPENAI_COMPATIBLE_API_KEY="sk-..."
```

Poi configura lo stadio nel TOML (il modello è quello dell'endpoint, es.
`openrouter/deepseek/deepseek-chat` per OpenRouter):

```toml
[pre_retrieval]
stages = [
  { method = "step_back", params = { model = "openai-compatible/openrouter/auto-beta" } },
]
```

Il model id inviato all'endpoint è tutto ciò che segue `openai-compatible/`
(es. `openrouter/auto-beta` per `https://openrouter.ai/openrouter/auto-beta`).

### Verifica

```bash
ks search -v "la tua query" -w <workspace>   # log: chiamate LLM e stage
# oppure nei log di servizio/CLI:
tail -f ~/.local/state/KnowledgeSpace/ks.log
```

Se la chiave manca, l'errore è esplicito (`MissingAPIKeyError`); se
l'endpoint non risponde, l'errore indica URL e modello (`LLMConnectionError`).
Stadi che usano LLM: pre-retrieval `multi_query`, `step_back`,
`least_to_most`; retrieval con `query_mode = "hyde"`; post-retrieval
`relevance`/`cross_encoder` (dove configurato).

## Flag globali

| Flag | Descrizione |
|------|-------------|
| `--verbose`, `-v` | Output dettagliato (DEBUG) |
| `--json` | Output JSON (dove applicabile) |
| `--workspace <path>` | Override workspace corrente |
| `--help` | Mostra aiuto |
| `--version` | Mostra versione |

## Lista completa dei comandi

```bash
# Help generale
ks --help

# Help per ogni comando
ks workspace --help
ks domain --help
ks base --help
ks file --help
ks chunk --help
ks tree --help
ks search --help
ks reindex --help
ks config --help
ks models --help
ks status --help
```

## Domini

I domini raggruppano basi di conoscenza correlate:

```bash
ks domain new diritto             # Crea dominio
ks domain add-base diritto base1  # Assegna base al dominio
ks domain auto-generate           # Genera da struttura cartelle
```

## Configurazione

Knowledge Space usa una cascata di configurazione TOML:

```
default hardcoded
  ↓ override
<workspace>/.knowledge-space/defaults.toml
  ↓ override
<base>/.knowledge-space/base.toml
```

Ogni file contiene le sezioni sotto; un campo assente eredita dalla
cascata. `ks config set <chiave> <valore>` scrive nel file giusto
(defaults o base) con autocompletamento dei valori ammessi.

### `[ingestion]` — conversione dei file in Markdown

| Chiave | Valori ammessi | Default |
|---|---|---|---|
| `library` | `markitdown` · `docling` · `pymupdf4llm` | `markitdown` |
| `params` | dict libero (dipende dalla libreria) | `{}` |

`docling` e `pymupdf4llm` non sono installate di default (vedi sezione
Installazione — lazy install).

### `[chunking]` — divisione del Markdown in chunk

| Chiave | Valori ammessi | Default |
|---|---|---|---|
| `method` | `recursive` · `semantic` · `sliding` | `recursive` |
| `chunk_size` | intero (caratteri) | `800` |
| `chunk_overlap` | intero (caratteri) | `120` |
| `separator` | stringa (es. `"\n\n"`, `"\n"`, `" "`) | `"\n\n"` |
| `params` | dict libero | `{}` |

### `[embedding]` — modello di embedding

| Chiave | Valori ammessi | Default |
|---|---|---|---|
| `model` | nome dal registry (`ks models list`) | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (118MB, multilingua) |
| `device` | `cpu` · `cuda` · `mps` (default: auto) | — |
| `api_base` | URL endpoint remoto (solo modelli API) | — |
| `params` | dict libero | `{}` |

### `[pre_retrieval]` — espansione delle query (in cascata)

| Chiave | Valori ammessi | Default |
|---|---|---|---|
| `stages[].method` | `identity` · `multi_query` · `step_back` · `least_to_most` | `identity` |
| `stages[].params` | dict libero (es. `model` per gli stadi che usano LLM) | `{}` |

In TOML gli stadi si dichiarano con `[[pre_retrieval.stages]]` ripetuto.

### `[retrieval]` — recupero dei chunk

| Chiave | Valori ammessi | Default |
|---|---|---|---|
| `method` | `dense` · `sparse` · `hybrid` | `dense` |
| `query_mode` | `original` · `hyde` | `original` |
| `top_k` | intero | `10` |
| `params` | dict libero (es. `fusion`, `dense_weight`, `rrf_k` per hybrid) | `{}` |

### `[post_retrieval]` — reranking/compression dei risultati

| Chiave | Valori ammessi | Default |
|---|---|---|---|
| `method` | `identity` · `relevance` · `mmr` · `cross_encoder` · `llm` · `llm_chain_extract` · `selective_context` | `identity` |
| `params` | dict libero (es. `threshold`, `model`) | `{}` |

### `[graph]` — grafo di conoscenza (Neo4j)

| Chiave | Valori ammessi | Default |
|---|---|---|---|
| `enabled` | `true` · `false` | `false` |
| `on_chunk_change` | `eager` · `lazy` | `lazy` |
| `top_k` | intero | `5` |
| `extraction_model` | `None` · `lm-studio/<modello>` · `openai-compatible/<modello>` (pattern sezione LLM) | `None` (grafo inattivo: l'estrazione richiede un LLM) |
| `embedding_model` | nome dal registry (`ks models list`) | lo stesso delle basi (riciclo embedding sempre attivo) |

Esempio `defaults.toml` completo:

```toml
[ingestion]
library = "markitdown"

[chunking]
method = "recursive"
chunk_size = 1200
chunk_overlap = 200
separator = "\n\n"

[embedding]
model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
device = "cpu"

[[pre_retrieval.stages]]
method = "identity"

[retrieval]
method = "dense"
query_mode = "original"
top_k = 10

[post_retrieval]
method = "identity"

[graph]
enabled = true
on_chunk_change = "lazy"
top_k = 5
extraction_model = "openai-compatible/openrouter/free"
```

## Architettura

```
knowledge_space/
├── packages/
│   ├── knowledge-base/     # Libreria pura (modelli, manager, strategy)
│   └── mcp-server/         # Server MCP (futuro)
├── src/knowledge_space/    # App layer (CLI, bootstrap, logging)
└── tests/
```

## Sviluppo

```bash
# Esegui tutti i test
uv run pytest

# Esegui test specifici
uv run pytest tests/test_cli.py -v
uv run pytest packages/knowledge-base/tests/ -v
```
