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
ExecStart=%h/.local/bin/ks serve
Restart=always
RestartSec=5
Environment=XDG_STATE_HOME=%t/KnowledgeSpace

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

> **Nota:** `%h` in ExecStart si espande nella home dell'utente, quindi il path
> `%h/.local/bin/ks` funziona qualunque sia la home. Assicurati che la directory
> `~/.local/bin` sia in `PATH` (lo è di default su quasi tutte le distro moderne).

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
