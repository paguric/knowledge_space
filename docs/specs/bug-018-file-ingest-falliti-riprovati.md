# Bug 018 — File che falliscono l'ingestione vengono riprovati a ogni sync

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** media

## Causa

Quando un file fallisce l'ingestione (formato non supportato, PDF corrotto, errore docling), nessun `FileEntry` viene registrato in `state.json`. A ogni `sync_and_ingest` successivo, il file viene ri-scoperto come "nuovo" e riprovato, spammando il log e consumando CPU.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — `_ingest_files_in_base`, `_ingest_new_files_in_existing_base`

## Come riprodurre

```bash
echo "test" > ~/ws2/Base/file.txt
sleep 10
# Il watcher prova a ingestire, fallisce (formato non supportato)
sleep 30
# Il watcher esegue un altro sync_and_ingest (es. per altri eventi)
# file.txt viene riprovato → nuovo warning
grep "file.txt" ~/.local/state/KnowledgeSpace/ks.log
# → più occorrenze invece di una
```

## Fix atteso

Registrare un `FileEntry` con `active=False` (o `active=True` ma senza chunk) anche quando l'ingestione fallisce. Così i sync successivi vedono il file già presente e non lo riprocessano.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | Registrare FileEntry anche in caso di errore |

### Verifica

```bash
echo "test" > ~/ws2/Base/fail.txt
sleep 60
# Aspetta 2+ sync_and_ingest
grep -c "fail.txt" ~/.local/state/KnowledgeSpace/ks.log
# → 1 (non 2+)
```
