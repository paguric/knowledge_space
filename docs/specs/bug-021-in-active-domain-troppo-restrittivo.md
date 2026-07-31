# Bug 021 — `_in_active_domain` esclude basi non in domini e basi standalone

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** alta (metà delle basi escluse dalla ricerca)

## Causa

`_in_active_domain(base_name, domains)` restituisce `False` per basi non esplicitamente in un dominio attivo. Ma:
- Basi standalone (es. `Progetto di Tesi`) non sono in nessun dominio → ingiustamente escluse
- Cartelle padre di domini (es. `Paper Accademici`) possono contenere file propri → escluse
- Basi esistenti su disco ma non ancora registrate in un dominio (`paper3`) → escluse

La logica corretta: se una base NON è in nessun dominio, è sempre searchable. Se è in un dominio, quel dominio deve essere attivo.

File coinvolti:
- `src/knowledge_space/cli/search.py` — `_in_active_domain()`

## Come riprodurre

```bash
# Paper Accademici è un dominio con papers1 e papers2
# Paper Accademici stessa ha 2 file propri
# Progetto di Tesi è standalone

ks search -w ~/ws2 "ciao" --verbose
# → Paper Accademici: saltato (❌ errato)
# → papers1: cercato ✓
# → papers2: cercato ✓
# → paper3: saltato (❌ errato — non è in nessun dominio)
# → Progetto di Tesi: saltato (❌ errato — standalone)
```

## Fix atteso

```python
def _in_active_domain(base_name, domains):
    if not domains:
        return True
    for d in domains:
        if base_name in d.base_names:
            return d.active        # base in un dominio → dipende se attivo
    return True                    # base non in nessun dominio → sempre ok
```

### File da toccare

| File | Modifica |
|------|----------|
| `src/knowledge_space/cli/search.py` | Correggere `_in_active_domain` |
| `packages/knowledge-base/src/knowledge_base/search_service.py` | Stessa correzione in `is_base_searchable` |

### Verifica

```bash
ks search -w ~/ws2 "ciao" --verbose
# → Paper Accademici: cercato ✓
# → Progetto di Tesi: cercato ✓
# → paper3: cercato ✓
```
