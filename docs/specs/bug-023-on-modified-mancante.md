# Bug 023 — `on_modified` mancante: file modificati su disco non rilevati dal watcher

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** alta

## Causa

Il watcher ha handler solo per `on_created`, `on_deleted`, `on_moved`. Manca `on_modified`. Se un utente modifica un PDF e lo salva sullo stesso path, il watcher non se ne accorge.

La pipeline incrementale (`add_file`) è già pronta: confronta `content_hash`, ricalcola solo i chunk modificati, upsert selettivo su Chroma.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — handler `on_modified`

## Fix atteso

Aggiungere `on_modified` all'handler watchdog, identico a `on_created`:

```python
def on_modified(self_inner, event):
    src = getattr(event, "src_path", "")
    if ".knowledge-space" in src:
        return
    logger.info("Evento FS on_modified: %s", src)
    watcher_ref._schedule_sync()
```

`_schedule_sync()` → `sync_and_ingest()` → `add_file()` va in short-circuit se `content_hash` è identico, altrimenti pipeline incrementale.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | Aggiungere `on_modified` all'handler watchdog |

### Verifica

```bash
# Modifica un PDF nella base monitorata
echo "" >> ~/ws2/Base/file.pdf
sleep 5
ks status -w ~/ws2
# → il file deve mostrare il nuovo numero di chunk (se il contenuto è cambiato)
```
