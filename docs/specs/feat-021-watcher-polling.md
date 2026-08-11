# Feature 021 — Polling periodico come fallback del watcher

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media (richiesta per Windows/Docker Desktop)

## Obiettivo

Sync periodica di fallback per filesystem dove inotify è inaffidabile: Docker Desktop (WSL2, bind mount da `C:\`), WSL2 su `/mnt/c` (drvfs), NFS. Con il polling, le modifiche a container/servizio attivo vengono comunque rilevate entro N secondi.

## Causa

Il watcher dipende interamente da eventi inotify (`on_created/deleted/moved/modified`). Su quei filesystem gli eventi possono non arrivare (in particolare `mkdir` e `move`). La sync iniziale (bug-017) copre solo le modifiche a servizio fermo.

## Fix (KISS)

1. **`WorkspaceWatcher`**: nuovo parametro `poll_interval: float = 0` (0 = disattivato). In `start()`, se > 0, avviare un timer ricorsivo che ogni N secondi chiama `_schedule_sync()`.
2. **Sicurezza**: il polling passa dal debounce esistente → la protezione anti-sovrapposizione (bug-016) resta attiva (mai sync parallele, pending se in corso). Il costo è basso: `sync_and_ingest` è idempotente (mtime/content_hash → no-op se nulla è cambiato).
3. **Configurazione**: opzione CLI `ks serve --poll-interval <secondi>` (default 0). Passata a ogni `WorkspaceWatcher` creato da `serve.py`.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | Timer di polling in `WorkspaceWatcher` |
| `src/knowledge_space/cli/serve.py` | Opzione `--poll-interval` |

### Verifica

```bash
ks serve --sse --poll-interval 5 &
# Copia un file nella base SENZA generare eventi affidabili (es. su /mnt/c)
cp doc.pdf /mnt/c/ws/Base/
sleep 12
ks status -w /mnt/c/ws
# → il file compare entro ~2 intervalli di polling
```
