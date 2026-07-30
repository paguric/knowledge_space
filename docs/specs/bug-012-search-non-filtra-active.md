# Bug 012 — La ricerca non esclude chunk/file/basi/domini non attivi

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** alta

## Causa

`SearchService.search()` e le strategy di retrieval non filtrano per `active`. Chroma restituisce tutto.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/search_service.py` — orchestratore, nessun filtro active
- `packages/knowledge-base/src/knowledge_base/strategies/retrieval.py` — `DenseRetrieval.search()`, `SparseRetrieval.search()`, `HybridRetrieval` — query diretta a Chroma
- `packages/knowledge-base/src/knowledge_base/models.py` — `KnowledgeBase.active`, `FileEntry.active`, `ChunkRef.active`, `Domain.active`

## Fix (KISS)

Due soli controlli:

1. **Pre-retrieval**: escludi le basi non attive e quelle in domini non attivi. Non chiamare `collection.query()` per loro.
2. **Post-retrieval**: scarta i chunk il cui file è disattivato (`FileEntry.active=False`) o il chunk stesso è disattivato (`ChunkRef.active=False`).

Nessuna modifica a Chroma, nessun nuovo metadato.

### Come

Passare il `Workspace` (o un resolver) al `SearchService`, così da poter consultare `workspace.domains`, `kb.active`, `kb.files[].active`, `file.chunks[].active`.

```python
# In SearchService.search():
for base_name, kb in workspace.bases.items():
    if not kb.active:
        continue
    if not _in_active_domain(base_name, workspace.domains):
        continue
    results = strategy.search(...)  # solo su questa base

# Dopo retrieval:
results = [r for r in results if _chunk_is_active(r, workspace)]
```

### `_in_active_domain(base_name, domains)`

Se non ci sono domini → tutte le basi sono considerate "in un dominio attivo".  
Se ci sono domini → la base deve appartenere ad almeno un dominio con `active=True`.

### `_chunk_is_active(result, workspace)`

1. Parsa il `chunk_id` (formato: `"{base_name}::{file_id}::{i}"`) per estrarre `base_name` e `file_id`.
2. Itera `workspace.bases[base_name].files.values()` per trovare il `FileEntry` con `entry.file_id == file_id`. Se non trovato o `file.active=False` → scarta.
3. Cerca il `ChunkRef` nel file tramite indice `i`: se `chunk.active=False` → scarta.
4. Se il parsing fallisce, scarta per sicurezza.

### File da toccare

- `packages/knowledge-base/src/knowledge_base/search_service.py` — iniettare workspace, aggiungere i due filtri
- `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` — passare workspace al SearchService
- `tests/test_retrieval.py` — test: base disattivata esclusa, file disattivato escluso, chunk disattivato escluso

### Verifica

```bash
ks file deactivate paper.pdf
ks search "query"  # → paper.pdf non appare
ks base deactivate "Base"
ks search "query"  # → nessun risultato da quella base
```
