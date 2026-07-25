# Indicizzazione incrementale e ciclo di vita dell'indice

> **Stato:** implementato (trigger 1-2) | **Step:** 7 | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Panoramica

Descrive **quando e come** l'indice vettoriale (Chroma) e i chunk su disco vengono ricalcolati, e cosa NON va ricalcolato quando possibile. Chroma è la fonte di verità; i chunk su disco sono prodotto derivato, non editabili dall'utente.

## Scelte

| Trigger | Impatto | Grave? |
|---------|---------|--------|
| 1 — content change | Diff per `content_hash`, re-embed solo chunk cambiati | basso |
| 2 — move/rename | Nessun recompute, solo update path/nome | nullo |
| 3 — cambio modello embedding | Full re-embed, chunk su disco intatti | medio |
| 4 — cambio chunking | Full re-chunk + re-embed + riscrittura + grafo | alto |
| 5 — cambio ingestion | Full re-ingest + tutto downstream | alto |

| Aspetto | Scelta |
|---------|--------|
| `file_id` | UUID4 stabile, disaccoppiato dal nome |
| Insert in mezzo | Approccio B (shift accettato, re-embed da quel punto) |
| Blocco config | Errore se model/method/library diverso + collection non vuota |
| Chunk editabili | No — Chroma fonte di verità |

## Dettagli

### Prerequisito: `file_id` stabile

Per supportare il trigger 2 senza ricalcolare, `chunk_id` non può dipendere dal nome del file. `FileEntry` guadagna un `file_id: str` (UUID4) stabile per tutta la vita del file. `chunk_id = f"{base_name}::{file_id}::{i}"`.

- Rename = update `FileEntry.path` + `FileEntry.name` + metadati Chroma + property Neo4j. Zero tocchi a chunk/embedding/grafo.
- Move (stessa base) = update path. Zero recompute.
- Move cross-base = delete + add (la base fa parte del `chunk_id`).

### Trigger 1 — Content change (incrementale via hash diff)

1. Re-ingest del file intero → markdown.
2. Se `hash(markdown) == hash_stored` → skip tutto.
3. Re-chunk → `new_chunks`.
4. Leggi `old_chunks` da Chroma (testo + `content_hash`).
5. Diff per `chunk_id`: hash uguale → skip; hash diverso → re-embed + upsert; indice nuovo → embed + insert; indice mancante → delete.
6. Riscrivi su disco solo i chunk cambiati.
7. Propaga al grafo: solo chunk "changed"/"new" se `on_chunk_change = "eager"`.

**Insert in mezzo (approccio B):** re-embedda tutti i chunk dall'inserimento in poi. Semplice, ok per file corti. Fase 2: valutare approccio A (allineamento via hash) per file lunghi.

### Trigger 2 — Move / rename

1. Update `FileEntry.path` + `FileEntry.name` in `state.json`.
2. Update metadata Chroma: campo `file_name`. `chunk_id` immutato.
3. Update property Neo4j su nodi `Chunk`/`Document`.
4. Chunk su disco: cartella `<file_id>/` non si sposta.

**Move cross-base:** delete + add automatico (il `chunk_id` contiene `base_name`).

### Trigger 3 — Cambio modello di embedding

**Bloccato** se collection non vuota. `ks reindex <base> --model-change`:
1. Crea nuova collection con `dim` del nuovo modello.
2. Legge chunk da disco (testo, NON embedding vecchi).
3. Re-embed con il nuovo modello.
4. Swap atomico collection.
5. Aggiorna `embedding_model` in `state.json`.
6. Propaga nuovi vettori al grafo (property-only, no re-estrazione).

### Trigger 4 — Cambio strategia/parametri di chunking

**Bloccato** se collection non vuota. `ks reindex <base> --chunking-change`:
1. Re-ingest (o riusa markdown cached).
2. Re-chunk con nuova strategia/parametri.
3. Riscrivi chunk su disco.
4. Delete + insert in Chroma.
5. Re-embed tutti i nuovi chunk.
6. Re-estrazione LLM completa del file sul grafo.

### Trigger 5 — Cambio libreria/parametri di ingestion

**Bloccato** se collection non vuota. `ks reindex <base> --ingestion-change`:
1. Re-ingest con nuova libreria/parametri.
2. Se `hash(new_markdown) == hash(old_markdown)` → no-op + warning.
3. Altrimenti: re-chunk + re-embed + riscrittura + grafo (come trigger 4).

### Tabella riassuntiva comandi CLI

| Comando | Trigger | Costo tipico |
|---|---|---|
| (auto, via watcher) | 1 — content change | basso (diff) |
| (auto, via watcher) | 2 — move/rename | nullo |
| `ks reindex <base> --model-change` | 3 — embedding model | medio (re-embed tutti) |
| `ks reindex <base> --chunking-change` | 4 — chunking strategy/params | alto |
| `ks reindex <base> --ingestion-change` | 5 — ingestion library/params | alto |

### Integrazione con il grafo

| Trigger | Propagazione al grafo |
|---|---|
| 1 — content change | eager: re-estrazione LLM mirata su chunk cambiati |
| 2 — move/rename | property-only: update `file_name`/`path` su Neo4j |
| 3 — cambio modello | property-only: update `embedding` su nodi Chunk |
| 4 — cambio chunking | full: delete + re-estrazione LLM |
| 5 — cambio ingestion | full: come trigger 4 |

### Test

| Test | Cosa verifica |
|------|---------------|
| `file_id` stabile su rename | `chunk_id` immutato, Chroma intatto |
| Diff hash su content change | solo chunk cambiati re-embeddati |
| Re-save identico | skip totale |
| Move cross-base | delete + add |
| Blocco cambio config | errore esplicito per trigger 3/4/5 |
| `ks reindex --model-change` | nuova collection, `dim` nuova |
| `ks reindex --chunking-change` | nuovi `chunk_id`/testo, grafo re-indicizzato |
| `ks reindex --ingestion-change` | nuovo markdown, tutto downstream |

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 7 (KnowledgeBaseManager, file_id, content_hash) | Step 8-bis (propagazione grafo), Step 13 (CLI `reindex`) |
