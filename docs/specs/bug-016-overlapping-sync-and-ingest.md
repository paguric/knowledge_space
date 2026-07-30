# Bug 016 — `sync_and_ingest` chiamato più volte mentre precedente ancora in esecuzione → file indicizzati N volte

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** alta (CPU alle stelle, ingest duplicata)

## Causa

Il watcher chiama `sync_and_ingest` a ogni scadenza debounce. Se il primo `sync_and_ingest` è ancora in esecuzione (es. sta processando PDF da 3 minuti), il secondo parte comunque e re-ingestisce gli stessi file.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — `sync_and_ingest`, debounce handler
- `packages/knowledge-base/src/knowledge_base/workspace_watcher.py` — `_WorkspaceWatcher`

## Come riprodurre

```bash
# Copia 4+ PDF pesanti in una base
cp *.pdf /tmp/ws/Base/
# Il watcher fa partire sync_and_ingest (batch 1)
# Dopo 500ms debounce, parte sync_and_ingest (batch 2) mentre batch 1 ancora gira
# I PDF vengono processati 2+ volte in parallelo
grep "Pipeline ingestion" ~/.local/state/KnowledgeSpace/ks.log | grep -c "$FILENAME"
# → 2 o più
```

## Fix atteso

`sync_and_ingest` deve essere protetto da lock per workspace: se una chiamata è in corso, le successive vengono droppate o accodate (non eseguite in parallelo).

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_watcher.py` | Lock per workspace nel debounce handler |
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | Opzionale: rendere `sync_and_ingest` idempotente |

### Verifica

```bash
# Dopo fix: stesso test, ogni file deve comparire 1 sola volta
grep "Pipeline ingestion" ~/.local/state/KnowledgeSpace/ks.log | grep "$FILENAME" | wc -l
# → 1
```
