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

Quando `_discover_bases_recursive` trova una nuova cartella con `.knowledge-space/state.json`:

1. **Importare** lo stato esistente (file, chunk, embedding_model) invece di re-indicizzare.
2. **Rinominare** la collection Chroma dal vecchio nome al nuovo (`chroma_collection_name(vecchio_nome)` → `chroma_collection_name(nuovo_nome)`) oppure tenerla col nome vecchio e aggiornare il riferimento nello stato.
3. **Aggiornare** i path `chunk_id` e `file_id` se necessario (se il chunk_id contiene il nome della base).

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | `_discover_bases_recursive`: rileva `.knowledge-space/` e importa stato + aggiorna collection name |
| `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` | Helper per rinominare/importare collection Chroma |

### Verifica

```bash
cp -r ~/ws2/Base ~/ws2/Base_backup
sleep 10
ks status -w ~/ws2
# → Base_backup deve mostrare stessi file e chunk di Base, senza re-ingestione
grep "Pipeline ingestion" ~/.local/state/KnowledgeSpace/ks.log | grep Base_backup
# → nessuna nuova ingestione
```
