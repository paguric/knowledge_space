# Knowledge Space

Pipeline di ingestione, indicizzazione e retrieval su documenti. Architettura modulare con strategy pattern per ingestion, chunking, embedding e retrieval.

## Installazione

```bash
# Clona il repo
git clone <repo-url>
cd knowledge_space

# Installa con uv (consigliato per sviluppo)
uv sync
```

> **Nota:** dopo `uv sync`, il comando `ks` è disponibile via `uv run ks` (consigliato),
oppure attivando il venv con `source .venv/bin/activate`.

Per un'installazione **system-wide** permanente (senza bisogno di `uv run` o attivazione):

```bash
# Con uv tool install — installa come tool nella directory bin di uv
# (tipicamente ~/.local/bin/), disponibile da qualsiasi terminale
uv tool install -e .

# Con pip (installa globalmente, richiede che la variabile d'ambiente PATH
# includa la directory degli script di pip)
pip install -e .

# Oppure con uv, installando il pacchetto nell'ambiente Python di sistema
uv pip install -e . --system
```

## Avvio automatico del server

`ks serve` avvia il server MCP e attiva i watcher filesystem su tutti i workspace
registrati: qualsiasi modifica al filesystem (file aggiunti, spostati, rimossi)
viene rilevata in tempo reale e sincronizzata automaticamente.

Su Linux il modo più semplice è un **systemd user service**:

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

## Utilizzo rapido

> Se hai usato `uv sync` senza attivare il venv, anteponi `uv run` a ogni comando:
> `uv run ks --help`, `uv run ks workspace add ...`, ecc.

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

## LLM (modelli linguistici)

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

### Status

```bash
ks status                        # Panoramica workspace attivo
```

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

Esempio `base.toml`:

```toml
[ingestion]
library = "docling"

[chunking]
method = "recursive"
chunk_size = 1200
chunk_overlap = 200

[embedding]
model = "bge-m3"

[retrieval]
method = "dense"
top_k = 10

[post_retrieval]
method = "identity"
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
