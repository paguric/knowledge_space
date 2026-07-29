# Bug 009 — `.knowledge-space` non escluso dalla scoperta ricorsiva delle basi

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare
**Priorità:** alta (basi spam con cartelle interne a .knowledge-space)

## Riproduzione

```bash
mkdir -p /path/to/ws/NewBase
# sync_and_ingest() gira
# → .knowledge-space NON escluso
# → vengono registrate basi come:
#   .knowledge-space/chroma/uuid
#   .knowledge-space/chunks/uuid
#   NewBase/.knowledge-space/chroma/uuid
#   ecc.
```

## Causa radice

In `workspace_manager.py`, `_discover_bases_recursive()` usa `rglob('*')` ma non esclude `.knowledge-space`:

```python
for entry in ws_path.rglob("*"):
    if not entry.is_dir() or entry.name.startswith("."):
        continue
```

Il filtro `entry.name.startswith(".")` esclude solo le cartelle che iniziano con `.` **nella loro directory corrente**. Ma `.knowledge-space` è una cartella il cui nome inizia con `.` — quindi dovrebbe essere esclusa. Vediamo...

Aspetta — `.knowledge-space` inizia con `.`. Allora `entry.name.startswith(".")` dovrebbe escluderla. Vediamo se il problema è un altro: le cartelle **dentro** `.knowledge-space/` hanno nomi che non iniziano con `.` (es. `chroma/`, `chunks/`).

Quindi il filtro corretto è: escludere qualsiasi cartella che abbia `.knowledge-space` nel suo percorso (path), non solo quelle il cui nome inizia con `.`.

## Fix atteso

In `_discover_bases_recursive()`, cambiare il filtro da:

```python
if entry.name.startswith("."):
    continue
```

a:

```python
# Esclude .knowledge-space e tutto il suo contenuto
dot_ks_name = ".knowledge-space"
if dot_ks_name in entry.parts:
    continue
```

Questo esclude la cartella stessa e tutto ciò che contiene (cartelle con UUID, file, ecc.).

## File da toccare

- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — modifica filtro in `_discover_bases_recursive()`

## Verifica

```bash
mkdir -p /path/to/ws/TestBase
ls /path/to/workspace/.knowledge-space/
# Nessuna base .knowledge-space/* deve comparire in ks status
ks status --workspace /path/to/workspace
# Output non deve contenere ".knowledge-space"
```

- `uv run pytest packages/knowledge-base/tests/test_workspace_manager.py -q` → verde.

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Al termine: riportare branch, file cambiati, risultato test, eventuali dubbi.
