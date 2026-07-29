# Bug 012 — La ricerca non esclude chunk/file/basi/domini non attivi

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** alta (risultati di ricerca includono contenuti disattivati)

## Riproduzione

```bash
# 1. Indicizza un file e verifica che appaia nella ricerca
ks file add "Base" paper.pdf
ks search "query"  # → paper.pdf appare

# 2. Disattiva il file
ks file deactivate paper.pdf

# 3. Ricerca di nuovo
ks search "query"  # → paper.pdf appare ANCORA (BUG)
```

Lo stesso per basi (`base deactivate`), domini (`domain deactivate`), chunk (`chunk deactivate`).

## Causa radice

La pipeline di ricerca (`SearchService` + `DenseRetrieval` / `SparseRetrieval` / `HybridRetrieval`) interroga Chroma direttamente e restituisce **tutti** i chunk, senza mai verificare i flag `active`:

- `DenseRetrieval.search()` → `collection.query()` → nessun filtro active (riga 99-110)
- `SparseRetrieval._build_index()` → `collection.get()` → carica TUTTI i documenti (riga 203)
- `SearchService.search()` → unico filtro è dedup per `chunk_id` (riga 185)

Nessuno dei tre controlla:
- Se il **chunk** è attivo (`ChunkRef.active`)
- Se il **file** è attivo (`FileEntry.active`)
- Se la **base** è attiva (`KnowledgeBase.active`)
- Se il **dominio** è attivo (`Domain.active`)

## Fix atteso

### Approccio: filtro post-retrieval nel `SearchService`

Aggiungere un filtro in `SearchService.search()` DOPO il retrieval e PRIMA del post-retrieval, oppure in `_run_retrieval()`, che escluda i risultati provenienti da chunk/file/basi/domini non attivi.

Per farlo, `SearchService` ha bisogno di accedere al modello del workspace (istanza di `Workspace`) per consultare i flag `active`. Questo richiede di **iniettare** il workspace (o una callback per risolvere i metadati) nel `SearchService`.

### Modifiche

1. **`SearchService.__init__`**: aggiungere parametro opzionale `workspace: Optional[Workspace]` o una `metadata_resolver: Callable[[str, str], Optional[dict]]` che, dato `chunk_id`, restituisce i metadati del chunk (file, base, dominio, active).

2. **`SearchService.search()`**: dopo il retrieval e prima/dopo il merge dei risultati, filtrare:
   ```python
   for r in all_results:
       meta = self._resolve_metadata(r.chunk_id)
       if not self._is_active(meta):
           continue
       ...
   ```

3. **`_is_active(meta)`**: controlla che chunk → file → base → dominio siano tutti `active=True`. Se uno qualsiasi è `False`, il chunk è escluso.

### Alternativa più semplice: filtro via metadati Chroma

I metadati dei chunk in Chroma possono includere `active: True/False`. Quando un file/base viene disattivato, aggiornare i metadati in Chroma. Poi la query può filtrare con `where={"active": True}`.

**Raccomandazione:** Approccio via metadati Chroma. È più efficiente (filtro lato database) e non richiede di iniettare il workspace nel SearchService. Richiede però che:
- `KnowledgeBaseManager.add_file()` salvi `active=True` nei metadati Chroma
- `file deactivate` / `base deactivate` aggiorni i metadati Chroma

### File da toccare

- `packages/knowledge-base/src/knowledge_base/strategies/retrieval.py` — aggiungere `where={"active": True}` (o filtro equivalente) nelle query Chroma
- `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` — salvare `active` nei metadati durante `add_file()` e aggiornarlo in `deactivate()`
- `packages/knowledge-base/src/knowledge_base/search_service.py` — se necessario, adattare l'interfaccia

### Verifica

```bash
ks file add "Base" paper.pdf
ks search "test" --json | jq '.[].metadata.active'  # deve essere true
ks file deactivate paper.pdf
ks search "test" --json  # non deve contenere paper.pdf
```

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md` e questo spec
- Lavorare sul branch `dev`
- Usare l'italiano per commenti, docstring e messaggi di commit
- Non modificare/committare file sotto `docs/` o `AGENTS.md`
- Al termine: riportare branch, file cambiati, risultato test, eventuali dubbi
