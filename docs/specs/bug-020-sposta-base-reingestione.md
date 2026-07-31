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

1. **Importare stato** da `.knowledge-space/state.json` (file, chunk, embedding_model) senza re-indicizzare.
2. **Rinominare collection Chroma**: da `chroma_collection_name(vecchio_nome)` a `chroma_collection_name(nuovo_nome)`.
3. **Aggiornare tutti i `chunk_id` in Chroma**: contengono `"{base_name}::..."` — vanno riscritti col nuovo nome base.
4. **Aggiornare `kb.path`** nello stato importato.
5. **Aggiornare domini**: se il vecchio nome era in `domain.base_names`, sostituirlo col nuovo.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | `_discover_bases_recursive`: rileva `.knowledge-space/`, importa e aggiorna stato |
| `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` | Helper per rinominare collection e aggiornare chunk_id in Chroma |
| `packages/knowledge-base/src/knowledge_base/domain_manager.py` | Aggiornare `base_names` nei domini |

### Verifica

```bash
cp -r ~/ws2/Base ~/ws2/Base_backup
sleep 10
ks status -w ~/ws2
# → Base_backup deve mostrare stessi file e chunk di Base, senza re-ingestione
grep "Pipeline ingestion" ~/.local/state/KnowledgeSpace/ks.log | grep Base_backup
# → nessuna nuova ingestione
```
