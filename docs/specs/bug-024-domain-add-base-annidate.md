# Bug 024 — `domain add-base`/`remove-base` falliscono con basi annidate

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** media

## Causa

`resolve_base_name`/`normalize_base_name` (`src/knowledge_space/cli/common.py`) riducono il nome a `Path.name` (ultimo componente): `"Papers/Base1"` → `"Base1"`. Ma le basi annidate sono registrate con chiave = path relativo completo (`"Papers/Base1"` in `ws.bases`). Quindi la ricerca per chiave fallisce e `domain add-base`/`remove-base` rispondono "base inesistente".

## Fix (KISS)

In `add_base`/`remove_base` di `src/knowledge_space/cli/domain.py`: se la risoluzione normale fallisce, ritentare con il **nome raw** (stringa esatta) come chiave in `ws.bases` prima di dichiarare la base inesistente.

```python
base_name = resolve_base_name(base_name, workspace=ws)
if base_name not in ws.bases and raw_name in ws.bases:
    base_name = raw_name
```

### File da toccare

| File | Modifica |
|------|----------|
| `src/knowledge_space/cli/domain.py` | Fallback al nome raw in `add_base`/`remove_base` |

### Verifica

```bash
ks domain add-base Paper "Papers/Base1" -w <ws>
# → "Base 'Papers/Base1' aggiunta al dominio 'Paper'"
ks domain remove-base Paper "Papers/Base1" -w <ws>
# → rimossa
```
