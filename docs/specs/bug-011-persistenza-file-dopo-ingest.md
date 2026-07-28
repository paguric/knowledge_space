# Bug 011 — `sync_and_ingest` non persiste i file dopo l'ingest

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** critica (causa re-ingestioni multiple dello stesso file, CPU al 300% per minuti)

## Causa radice

In `workspace_manager.py`, `sync_and_ingest()`:

```python
def sync_and_ingest(self, workspace):
    self.sync(workspace)        # ← chiama _save() con kb.files VUOTI
    # ...
    for base_name in basi_nuove:
        self._ingest_files_in_base(...)   # add_file() modifica kb.files in RAM
    for base_name in basi_esistenti:
        self._ingest_new_files_in_existing_base(...)  # idem
    return workspace              # ← NON chiama _save()!
```

Risultato: `kb.files` viene popolato in RAM da `add_file()`, ma mai persistito su disco. Al prossimo `sync()`, `_save()` riscrive `state.json` con `files: {}` → il file sembra sempre nuovo → re-ingest infinito.

## Fix

Aggiungere `self._save(workspace)` alla fine di `sync_and_ingest()`, dopo i loop di ingest:

```python
def sync_and_ingest(self, workspace):
    ...
    # 1. Basi nuove
    for base_name in basi_nuove:
        self._ingest_files_in_base(...)
    # 2. Basi esistenti
    for base_name in basi_esistenti:
        self._ingest_new_files_in_existing_base(...)
    
    # 3. Persisti i file indicizzati
    self._save(workspace)
    return workspace
```

## File da toccare

- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — aggiungere `self._save(workspace)` a fine `sync_and_ingest`

## Verifica

```bash
# Aggiungere un PDF, verificare singola ingest
uv run pytest packages/knowledge-base/tests/test_workspace_manager.py -q
```

## Istruzioni

- Leggere `docs/00a-repo-context.md` e questo spec
- Una sola riga da aggiungere: `self._save(workspace)` prima del `return`
- Commit e riporta
