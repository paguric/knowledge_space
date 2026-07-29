# Bug 008 — `sync_and_ingest` non indicizza file creati DOPO la base

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare
**Priorità:** alta (file aggiunti a basi esistenti non vengono indicizzati)

## Riproduzione

```bash
# 1. Watcher rileva la cartella → crea la base vuota
mkdir -p /path/to/ws/NewBase
# sync_and_ingest() gira → NewBase è nuova → skip (nessun file dentro ancora)

# 2. File aggiunto DOPO
echo "doc.txt" > /path/to/ws/NewBase/doc.txt
# sync() gira ma NewBase non è più "nuova" → skip ingest
# → doc.txt NON viene indicizzato
```

## Causa radice

In `sync_and_ingest()` (`workspace_manager.py`), la logica è:

```python
for base_name in basi_nuove:  # basi scoperte da sync()
    base_manager.add_file(...)
```

Viene indicizzato solo quando la base è **appena scoperta**. Se un file viene creato in una base che esiste già, `basi_nuove` è vuota → skip ingest.

Il watcher triggera `sync_and_ingest()` su `on_created` di un file, ma la base è già in `workspace.bases` → non è "nuova" → skip.

## Fix atteso

Modificare `sync_and_ingest()` per indicizzare anche i **file nuovi** nelle basi esistenti, non solo le basi nuove.

Approach: dopo aver fatto `sync()`, verificare per OGNI base (non solo quelle nuove) se ci sono file nuovi (check mtime o hash). Ispirarsi a come funziona in `KnowledgeBaseManager` per il sync file-level.

Opzioni:
1. **Check mtime**: se `kb.path` ha file con mtime > ultima sync → indicizza.
2. **Check esplicito**: il watcher triggera un "re-scan" completo ogni tot eventi.
3. **Due metodi**: `sync_and_ingest()` per basi nuove + `rescan_files()` per basi esistenti.

**Raccomandazione:** Option 1 (mtime) è più semplice e copre il caso d'uso. Salvare il timestamp dell'ultima sync sul workspace e confrontarlo con gli mtime dei file.

## File da toccare

- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — modifica `sync_and_ingest()`
- `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` — se serve aggiungere un metodo per indicizzazione seletiva
- `tests/test_workspace_manager.py` — test per file creato dopo la base

## Verifica

```bash
mkdir -p /tmp/ws_test/NewBase
# sync gira → NewBase creata
echo "doc.txt" > /tmp/ws_test/NewBase/doc.txt
# sync gira → doc.txt DEVE essere indicizzato
ks status --workspace /tmp/ws_test
# NewBase deve avere 1 file
```

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Al termine: riportare branch, file cambiati, risultato test, eventuali dubbi.
