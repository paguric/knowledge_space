# Feature 012 — `ks base remove --recursive` per rimuovere anche sotto-basi

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** bassa

## Obiettivo

`ks base remove Paper\ Accademici --recursive` rimuove la base e tutte le sue sotto-basi (`Paper Accademici/papers1`, `Paper Accademici/papers2`, ...).

## Causa

Oggi `base remove` rimuove solo la base specificata. Le sotto-basi restano orfane. Per pulire una gerarchia bisogna rimuoverle una a una.

File coinvolti:
- `src/knowledge_space/cli/base.py` — aggiungere flag `--recursive`
- `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` — `remove()` già singola; va estesa o wrappata

## Fix (KISS)

1. **Flag `--recursive`/`-r`** su `ks base remove`.
2. **Logica**: raccogli tutte le basi in `ws.bases` il cui nome inizia con `base_name + "/"`. Rimuovi prima le foglie, poi la radice.

```python
if recursive:
    sub_bases = [n for n in ws.bases if n.startswith(base_name + "/")]
    for sub in sorted(sub_bases, reverse=True):  # foglie prima
        manager.remove(sub)
manager.remove(base_name)
```

### File da toccare

| File | Modifica |
|------|----------|
| `src/knowledge_space/cli/base.py` | Flag `--recursive`, logica rimozione sotto-basi |

### Verifica

```bash
ks base remove "Paper Accademici" --recursive -w ~/ws2
# → rimuove Paper Accademici, Paper Accademici/papers1, Paper Accademici/papers2
ks status -w ~/ws2
# → nessuna traccia di Paper Accademici
```
