# Bug 017 — Watcher non esegue sync iniziale all'avvio → directory esistenti non scoperte

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** alta

## Causa

`WorkspaceWatcher.start()` avvia l'observer watchdog ma NON chiama `sync_and_ingest()`. Se cartelle/file vengono creati mentre il watcher è spento (es. crash, restart), non vengono mai scoperti finché non arriva un nuovo evento FS.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — `WorkspaceWatcher.start()`

## Come riprodurre

```bash
# Ferma il servizio
systemctl --user stop ks-serve
# Crea una nuova base mentre il watcher è giù
mkdir -p ~/ws2/NuovaBase
echo "test" > ~/ws2/NuovaBase/doc.txt
# Riavvia
systemctl --user start ks-serve
sleep 10
ks status -w ~/ws2
# → NuovaBase non appare
```

## Fix atteso

`WorkspaceWatcher.start()` deve chiamare `_schedule_sync()` (o `_do_sync()` direttamente) dopo aver avviato l'observer, così da scoprire directory/file creati mentre il watcher era spento.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | Aggiungere `_schedule_sync()` in `start()` |

### Verifica

```bash
systemctl --user stop ks-serve
mkdir -p ~/ws2/NuovaBase
systemctl --user start ks-serve
sleep 5
ks status -w ~/ws2 | grep NuovaBase
# → deve apparire
```
