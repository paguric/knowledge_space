# CLI standalone

> **Stato:** parziale (config set/unset/edit implementati) | **Step:** 13 | **Fase:** 3 | **Aggiornato:** 28 luglio 2026

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

### Inventario comandi

**Workspace:**

| Comando | Descrizione |
|---------|-------------|
| `workspace add <path>` | Registra workspace |
| `workspace list` | Elenca workspace |
| `workspace remove <path\|name>` | Rimuove dal GlobalIndex |
| `workspace move <old> <new>` | Aggiorna path |
| `workspace info [<path>]` | Mostra stato |

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

> **Considerazioni sulla ricerca:**
>
> - Il comando `search` richiede che almeno una base abbia un embedding model configurato (in `base.toml` o `defaults.toml`). Senza modello, la ricerca non produce risultati.
> - La ricerca opera su **tutte le basi attive** del workspace. Non sono previsti flag `--base` o `--domain`: la ricerca unificata su più basi è il comportamento di default.
> - Il numero di risultati (`top_k`) è determinato dalla configurazione della base (`retrieval.top_k`) e non è esposto come flag CLI. L'override è possibile solo via `config set`.
> - La ricerca restituisce chunk con metadati (file sorgente, base, score, content_hash). Usando `--json` si ottiene l'output strutturato per pipeline/script.
> - La ricerca è **solo vettoriale** (dense retrieval via Chroma) quando usata dal CLI. Le strategie sparse (BM25 via `rank_bm25`) e ibrida (rrf/weighted_sum) sono già implementate nel codice (`strategies/retrieval.py`) e si attivano configurando `[retrieval].method = "sparse"` o `"hybrid"` nel TOML.
> - Le basi disattivate (`base deactivate`) sono escluse dalla ricerca.
> - Il comando non supporta streaming: tutti i risultati sono restituiti in blocco.

**Reindex:**

| Comando | Descrizione |
|---------|-------------|
| `reindex <base>` | Auto-detect trigger + reindicizza |
| `reindex --all` | Tutte le basi |

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
| `config validate [<base>]` | Valida TOML |
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

**Profiles:**

| Comando | Descrizione |
|---------|-------------|
| `profiles list` | Elenca profili |
| `profiles show <name>` | Mostra TOML |
| `profiles apply <name> [--base <base>]` | Applica profilo (con rilevamento trigger) |
| `profiles save <name> [--base <base>]` | Salva config come profilo |
| `profiles diff <name> [--base <base>]` | Differenze |
| `profiles edit/remove <name>` | Modifica/elimina |

**Status:**

| Comando | Descrizione |
|---------|-------------|
| `status` | Panoramica workspace attivo, basi, file, chunk, grafo |

**Server (Fase 4):**

| Comando | Descrizione |
|---------|-------------|
| `serve` | Avvia backend (watcher + REST) |
| `serve --gui` | Backend + webview |
| `stop` | Arresta backend via REST `/shutdown` |
| `mcp` | MCP stdio bridge verso backend |

### Autocompletamento per `config set`

- **`key`**: suggerisce percorsi dotted validi (`chunking.` → `chunking.chunk_size`, ...)
- **`value`**: suggerisce valori ammissibili (`ingestion.library` → `docling`, `pymupdf4llm`, `markitdown`)

### Fasi di implementazione

- [x] Aggiungere `typer` alle dipendenze
- [x] Creare `knowledge_space/cli.py`
- [x] Implementare comandi per workspace, domini, basi, file, chunk
- [x] Implementare config show/init/set/unset/edit
- [ ] Implementare search, reindex, graph, auth, models
- [ ] Implementare profili
- [ ] Autocompletamento shell
- [ ] Test di integrazione (standalone mode)

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 8-ter (AppContext), Step 12 (logging) | Step 15 (REST), Step 18 (packaging) |
