# Bug 015 — `_discover_bases_recursive` crea basi da sottocartelle di basi esistenti

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** media

## Causa

`_discover_bases_recursive` usa `rglob("*")` che scopre TUTTE le sottocartelle come basi, incluse quelle dentro una base già registrata. Esempio: `DemoBase/RAG` e `DemoBase/Appunti` vengono registrate come basi separate.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — `_discover_bases_recursive()`

## Come riprodurre

```bash
mkdir -p ws/Base/sotto
ks workspace add ws
sleep 5
ks status -w ws
# → mostra Base e Base/sotto come due basi separate
```

## Fix atteso

`_discover_bases_recursive` deve fermarsi al primo livello di sottocartella che non è già figlia di una base esistente. In alternativa, non scoprire ricorsivamente: solo le cartelle di primo livello diventano basi.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | Modifica `_discover_bases_recursive` — solo primo livello |

### Verifica

```bash
mkdir -p ws/Base/sotto
ks workspace add ws && sleep 5
ks status -w ws
# → solo "Base", non "Base/sotto"
```
