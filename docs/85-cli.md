# CLI standalone

> **Stato:** implementato | **Step:** 13 | **Fase:** 3 | **Aggiornato:** 28 luglio 2026

## Panoramica

Interfaccia a riga di comando (Typer) per gestire workspace, domini, basi, file, chunk, ricerca e configurazione. In Fase 1-3 opera in modalità standalone (ogni comando = processo separato); in Fase 4+ diventa client del backend REST.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Framework | Typer |
| Nome comando | `knowledge-space` (alias `ks`) |
| Modalità (Fase 1-3) | Standalone (ogni comando = processo separato) |
| Modalità (Fase 4+) | Client del backend REST |
| Autocompletamento | Shell completion nativa (Typer) |
| Scrittura TOML | `config set`/`unset` con rilevamento trigger reindex |

## Dettagli

### Convenzioni generali

- **Cwd-context**: rileva il workspace corrente cercando `.knowledge-space/` (stile git). Override con `--workspace <path>`.
- **Flag globali**: `--help`, `--version`, `--verbose`/`-v`, `--json`, `--workspace <path>`
- **Sync implicito**: i comandi di sola lettura (`status`, `tree`, `workspace info`, `domain list`, `base list`, `base info`, `file list`, `chunk list`, `chunk show`) eseguono `sync()` prima di mostrare lo stato: basi/domini orfani rimossi, nuove basi scoperte. I comandi che modificano (add/remove/activate/deactivate) non fanno sync.

### Inventario comandi

**Workspace:**

| Comando | Descrizione |
|---------|-------------|
| `workspace add <path>` | Registra workspace |
| `workspace list` | Elenca workspace |
| `workspace remove <path\|name>` | Rimuove dal GlobalIndex |
| `workspace move <old> <new>` | Aggiorna path |
| `workspace info [<path>]` | Mostra stato |
| `workspace activate [<path>]` | Attiva un workspace (default: ultimo usato); chiede conferma se un altro è attivo |
| `workspace deactivate` | Disattiva il workspace attivo |

**Domain:**

| Comando | Descrizione |
|---------|-------------|
| `domain new <name>` | Crea dominio |
| `domain list` | Elenca domini |
| `domain remove <name>` | Rimuove dominio |
| `domain add-base <name> <base>` | Assegna base al dominio |
| `domain remove-base <name> <base>` | Rimuove base |
| `domain auto-generate` | Genera dalla struttura cartelle |
| `domain activate/deactivate <name>` | Attiva/disattiva |

**Base:**

| Comando | Descrizione |
|---------|-------------|
| `base add <path>` | Aggiunge base |
| `base add <path> --sync` | Aggiunge base e indicizza i file automaticamente |
| `base list` | Elenca basi |
| `base remove <name>` | Rimuove base |
| `base remove <name> -r` | Rimuove base + sotto-basi (foglie prima) |
| `base info <name>` | Config effettiva, modello, n. file/chunk |
| `base activate/deactivate <name>` | Attiva/disattiva |

**File:**

| Comando | Descrizione |
|---------|-------------|
| `file add <base> <path>` | Indicizza un singolo file |
| `file list [--base <name>]` | Elenca file indicizzati |
| `file sync [<base>]` | Scopre e indicizza tutti i nuovi file |
| `file remove <base> <name>` | Rimuove da indice |
| `file info <path>` | mtime, n. chunk, file_id |
| `file activate/deactivate <path>` | Attiva/disattiva |

**Chunk:**

| Comando | Descrizione |
|---------|-------------|
| `chunk list --file <path>` | Elenca chunk |
| `chunk show <id>` | Testo del chunk (read-only) |
| `chunk info <id>` | Metadati |
| `chunk activate/deactivate <id>` | Attiva/disattiva |

**Tree:**

| Comando | Descrizione |
|---------|-------------|
| `tree` | Albero: workspace → domain → base → file → chunk |
| `tree --base/--domain <name>` | Scope a base/dominio |
| `tree --json` | Output JSON |

**Search:**

| Comando | Descrizione |
|---------|-------------|
| `search <query>` | Ricerca vettoriale su tutte le basi attive, ordinato per score |
| `search <query> --json` | Output JSON |

**Reindex:**

| Comando | Descrizione |
|---------|-------------|
| `reindex <base>` | Pipeline completa (conversione se il sorgente è cambiato, Markdown salvato altrimenti) |
| `reindex --all` | Tutte le basi |
| `reindex <base> --chunking-change` | Riusa il Markdown salvato, ri-chunka senza riconvertire |
| `reindex <base> --model-change` | Riusa il Markdown salvato, ri-embedda senza riconvertire |
| `reindex <base> --ingestion-change` | Riconverte tutto dal sorgente |

**Graph:**

| Comando | Descrizione |
|---------|-------------|
| `graph init` | Crea indici Neo4j |
| `graph sync` | Propaga cambiamenti pending |
| `graph re-extract-schema` | Forza re-estrazione schema |
| `graph status` | Stato grafo |

**Config:**

| Comando | Descrizione |
|---------|-------------|
| `config show [<base>]` | Config effettiva (cascata resolved) |
| `config init` | Genera `defaults.toml` template |
| `config set <base\|defaults> <key> <value>` | Imposta preferenza (con autocompletamento) |
| `config unset <base\|defaults> <key>` | Rimuove chiave |
| `config edit <base\|defaults>` | Apre in `$EDITOR` |

**Auth:**

| Comando | Descrizione |
|---------|-------------|
| `auth set <key> <value>` | Scrive chiave API |
| `auth list` | Elenca chiavi (valori mascherati) |
| `auth remove <key>` | Rimuove chiave |

**Models:**

| Comando | Descrizione |
|---------|-------------|
| `models list [--local\|--remote]` | Elenca modelli embedding |
| `models info <name>` | Dettaglio modello |

**Status:**

| Comando | Descrizione |
|---------|-------------|
| `status` | Panoramica: workspace attivo, statistiche, domini con basi associate, basi standalone |
| `status -a`/`--all` | Come sopra + file e chunk nidificati per ogni base |
| `status --json` | Output JSON (statistiche + modelli) |

### Autocompletamento per `config set`

- **`key`**: suggerisce percorsi dotted validi (`chunking.` → `chunking.chunk_size`, ...)
- **`value`**: suggerisce valori ammissibili (`ingestion.library` → `markitdown`, `docling`, `pymupdf4llm`)
