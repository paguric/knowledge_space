# Bug 020 — Spostare/copiare base dentro workspace → re-ingestione completa (chunk + embedding ricalcolati)

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** media

## Causa

Quando una base viene spostata o copiata all'interno del workspace, il watcher la scopre come "nuova base" e `sync_and_ingest` re-indicizza tutti i file da zero. I chunk e gli embedding già calcolati nella `.knowledge-space/` originale vengono ignorati.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — `_discover_bases_recursive`, `sync_and_ingest`
- `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` — `_ingest_files_in_base`

## Come riprodurre

```bash
cp -r ~/ws2/Base ~/ws2/Base_backup
# Il watcher scopre Base_backup come nuova base
# → re-ingestisce tutti i PDF (CPU alle stelle)
ks status -w ~/ws2
# → Base_backup: chunk ricalcolati, embedding rifatti
```

## Fix atteso

Quando `_discover_bases_recursive` trova una nuova cartella, deve controllare se contiene già `.knowledge-space/state.json`. Se sì, importare lo stato esistente (basi, file, chunk) invece di re-indicizzare. La collection Chroma è già dentro `.knowledge-space/chroma/` e viene copiata insieme alla directory — va solo referenziata.

Se la cartella è frutto di una COPIA (non spostamento), i chunk su disco sono già presenti. Se è uno SPOSTAMENTO, idem — basta aggiornare i path.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | `_discover_bases_recursive`: rileva `.knowledge-space/` esistente e importa stato |

### Verifica

```bash
cp -r ~/ws2/Base ~/ws2/Base_backup
sleep 10
ks status -w ~/ws2
# → Base_backup deve mostrare stessi file e chunk di Base, senza re-ingestione
grep "Pipeline ingestion" ~/.local/state/KnowledgeSpace/ks.log | grep Base_backup
# → nessuna nuova ingestione
```
