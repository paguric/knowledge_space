# Refactor 003 — Collassare `info` e `tree` dentro `status` (KISS)

**Autore piano:** agente master · **Tipo:** refactor/CLI · **Stato:** da assegnare
**Priorità:** media · **Nota:** risolve anche il bug-003 originale (multi-workspace display)

## Obiettivo

Semplificare la superficie della CLI eliminando `ks workspace info` e `ks tree`,
e facendo di `ks status` l'unico comando di visualizzazione, capace di mostrare
tutti i workspace.

## Stato attuale

| Comando | Cosa fa | Da fare |
|---|---|---|
| `ks workspace info` | stats di un workspace | **Rimuovere** |
| `ks status` | stats + dettaglio basi di un workspace | **Collassare qui tutto** |
| `ks tree` | albero domini→basi→file di un workspace | **Rimuovere** |

## Comportamento atteso di `ks status`

**Senza argomenti** — mostra l'albero completo di tutti i workspace registrati,
con stato attivo/disattivo per domini, basi e file:

```
📁 /path/to/ws1
├── 📂 [✓] dominio1
│   ├── 📚 [✓] base1 (5 file, 120 chunk)
│   └── 📚 [✗] base2 (2 file, 40 chunk)
├── 📚 [✓] base3 standalone (3 file, 60 chunk)

📁 /path/to/ws2
└── 📂 [✗] dominio2
    └── 📚 [✓] base4 (10 file, 200 chunk)
```

**Con `--workspace <path>`** — mostra solo quel workspace (comportamento attuale di tree/status).

**Con `--base <name>`** — scope a una base (mostra i file dentro la base).

**Con `--json`** — output JSON strutturato, lista di workspace → domini → basi → file.

**Opzioni:**
- `--workspace`, `-w` — filtra a un workspace
- `--base`, `-b` — filtra a una base
- `--json` — output JSON
- `--verbose`, `-v` — DEBUG

## Implementazione

1. **Sposta** la logica di tree (`_build_tree`, `_print_tree`) da `tree.py` a `status.py`
   (o in `common.py` come helper riutilizzabile).
2. **Modifica** `status.py` per iterare su `ctx.workspace_manager.list()` se nessun
   workspace è specificato.
3. **Aggiungi** `--base` option in `status.py` (già presente in `tree.py`).
4. **Rimuovi** `workspace info` da `workspace.py`.
5. **Rimuovi** registrazione di `tree_command` in `__init__.py`.
6. **Rimuovi** `src/knowledge_space/cli/tree.py`.
7. **Aggiorna** i test in `test_cli.py`: rimuovi `TestTree`, rimuovi test `info`,
   aggiorna `TestStatus` per multi-workspace e tree output.

## File da toccare

- `src/knowledge_space/cli/status.py` — logica unificata (stats + tree)
- `src/knowledge_space/cli/workspace.py` — rimuovi `info`
- `src/knowledge_space/cli/tree.py` — **eliminare**
- `src/knowledge_space/cli/__init__.py` — rimuovi registrazione `tree`
- `tests/test_cli.py` — rimuovi test tree/info, estendi test status

## Verifica

- `uv run pytest tests/test_cli.py -q` → verde.
- `uv run pytest -q` → nessun nuovo fallimento.
- CLI: `ks status` senza args mostra tutti i workspace, con tree e stato.
- CLI: `ks status -w /path` mostra un solo workspace.
- CLI: `ks workspace info` → errore "comando non trovato".
- CLI: `ks tree` → errore "comando non trovato".

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Al termine: riportare branch, file creati/modificati/eliminati, risultato test.
