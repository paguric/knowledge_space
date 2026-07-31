# Bug 019 — `ks status` mostra basi spostate/cancellate se watcher è spento

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** media

## Causa

Il CLI carica lo stato da `state.json` senza verificare che le directory esistano su disco. Se una base viene spostata o cancellata mentre il watcher è spento, `ks status` la mostra ancora come presente.

File coinvolti:
- `src/knowledge_space/cli/status.py` — carica workspace senza sync
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — `load()` non valida il filesystem

## Come riprodurre

```bash
systemctl --user stop ks-serve
mv ~/ws2/Base ~/
ks status -w ~/ws2
# → Base ancora presente (errato)
```

## Fix atteso

`ks status` (e comandi simili) devono chiamare `workspace_manager.sync()` prima di mostrare i dati, così da rimuovere le basi non più esistenti.

### File da toccare

| File | Modifica |
|------|----------|
| `src/knowledge_space/cli/status.py` | Chiamare `sync()` prima di caricare |
| `src/knowledge_space/cli/workspace.py` | Idem per `workspace info` |

### Verifica

```bash
systemctl --user stop ks-serve
mv ~/ws2/Base ~/
ks status -w ~/ws2
# → Base NON presente
```
