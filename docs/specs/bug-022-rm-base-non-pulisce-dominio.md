# Bug 022 — Rimuovere base da disco non la toglie dal dominio

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** media

## Causa

`sync()` rimuove la base da `workspace.bases` quando la directory non esiste più, ma non aggiorna `domain.base_names`. La base resta elencata nel dominio come "orfana".

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — `sync()`

## Come riprodurre

```bash
ks domain add-base Paper "Papers/Base1"
rm -rf ~/ws2/Papers/Base1
sleep 5
ks domain list -w ~/ws2
# → Papers: Base1 ancora elencata (❌)
```

## Fix atteso

In `sync()`, dopo aver rimosso una base da `workspace.bases`, iterare `workspace.domains` e rimuovere la base da ogni `domain.base_names` che la contiene.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | `sync()`: pulire `domain.base_names` |

### Verifica

```bash
rm -rf ~/ws2/BaseInDomain
sleep 5
ks domain list
# → la base non deve più apparire in nessun dominio
```
