# Bug 025 — file_id uuid4 genera orfani nei retry falliti

- **Autore:** master
- **Tipo:** bug
- **Stato:** da implementare
- **Priorità:** media

## Causa

`file_id = uuid.uuid4().hex` a ogni prima indicizzazione
(`knowledge_base_manager.py` riga ~787): ogni tentativo fallito (es. EIO)
ha già scritto `documents/<uuid>.md` e `chunks/<uuid>/` con un uuid
nuovo; il retry genera un altro uuid → orfani accumulati (visto in VM:
2 PDF → 6 md + 6 dir chunk dopo i fallimenti EIO).

## Fix

1. `file_id` deterministico: `sha256(f"{base_name}/{file_name}")`
   — helper `_file_id_for(base_name, file_name)`.
   - retry falliti → stesso id → zero orfani, idempotenza
   - file modificato → stesso id (l'entry è trovata per `src.name`,
     il `content_hash` cambia) → incrementale invariato
   - rename → id nuovo → file nuovo (come oggi)
2. Pulizia orfani esistenti: metodo
   `KnowledgeBaseManager.cleanup_orphan_artifacts(base_name)` —
   rimuove `documents/<id>.md` e `chunks/<id>/` il cui id non è tra i
   `FileEntry.file_id` della base. Chiamato in `sync_and_ingest` dopo il
   loop di ingest di ogni base (sync completa e incrementale).

## File da toccare

| File | Modifica |
| --- | --- |
| `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` | helper `_file_id_for`; sostituisce uuid4 (2 punti); metodo cleanup; rimuovere import uuid se inutilizzato |
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | chiamata cleanup dopo ingest di ogni base (2 punti) |
| `packages/knowledge-base/tests/test_knowledge_base_manager.py` | test: id deterministico (atteso = sha256), retry → stesso id, cleanup orfani |
| `packages/knowledge-base/tests/test_workspace_manager.py` | test: sync rimuove orfani |

## Verifica

```bash
uv run pytest packages/knowledge-base/tests/test_knowledge_base_manager.py -v
uv run pytest packages/knowledge-base/tests/test_workspace_manager.py -v
uv run pytest -q
```
