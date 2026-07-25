# Indicizzazione incrementale e ciclo di vita dell'indice

> **Stato:** implementato (trigger 1-2) | **Step:** 7 | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Decisioni chiave

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

Questo documento descrive **quando e come** l'indice vettoriale (Chroma) e i chunk su disco vengono ricalcolati, e **cosa NON va ricalcolato** quando possibile. È la documentazione di riferimento per il ciclo di vita dell'indice: eventi watcher, cambi di configurazione, blocco/abilitazione dei reindex.

> **Fonte di verità**: Chroma. I chunk su disco (`<base>/.knowledge-space/chunks/...`) sono un prodotto derivato dal documento originale via ingestion + chunking, **non editabili dall'utente**. Se un `.md` su disco diverge da Chroma, Chroma vince. L'utente che vuole modificare il contenuto deve editare il **documento sorgente** (es. `preventivo.docx`) e lasciare che KS re-indicizzi.

## 5 trigger di reindex

| # | Trigger | Frequenza | Cosa ricalcolare | Grave? |
|---|---|---|---|---|
| 1 | **Content change** (file sorgente modificato) | comune | diff per `content_hash`, re-embed solo chunk cambiati | basso |
| 2 | **Move / rename** del file sorgente | occasionale | **nessun recompute** (solo update path/nome) | nullo |
| 3 | **Cambio modello di embedding** | raro | full re-embed, chunk su disco intatti | medio |
| 4 | **Cambio strategia/parametri di chunking** | raro | full re-chunk + re-embed + riscrittura `.md` + grafo | alto |
| 5 | **Cambio libreria/parametri di ingestion** | raro | full re-ingest + re-chunk + re-embed + riscrittura `.md` + grafo | alto |

I trigger 3, 4, 5 sono **config-change** (richiedono `ks reindex <base> --<reason>` esplicito). I trigger 1, 2 sono **watcher events** (gestiti automaticamente).

---

## Prerequisito: `file_id` stabile (disaccoppiare da `file_stem`)

Per supportare il **trigger 2 (move/rename)** senza ricalcolare, il `chunk_id` non può dipendere dal nome del file. Se `chunk_id = f"{base_name}::{file_stem}::{i}"` e l'utente rinomina `preventivo.docx` → `contratto.docx`, tutti i `chunk_id` cambiano anche se il contenuto è identico → Chroma keys + Neo4j node ids cambiati → niente riuso, rewrite totale.

**Scelta**: il modello `FileEntry` guadagna un `file_id: str` (UUID4) assegnato alla creazione del File, stabile per tutta la vita del file. `chunk_id = f"{base_name}::{file_id}::{i}"`. `file_stem` diventa metadato mutabile.

- Rename = update `FileEntry.path` + `FileEntry.name` nello stato + metadati Chroma + property Neo4j. Zero tocchi a chunk/embedding/grafo.
- Move (stesso file, altra cartella della stessa base) = update path. Zero recompute.
- Move cross-base = delete + add (la base fa parte del `chunk_id`).

Impatto sul filesystem: i chunk su disco passano da `<file_stem>/_chunk_<i>.md` a `<file_id>/_chunk_<i>.md`. Meno human-editabile, ma **i chunk non sono più editabili** per decisione sopra, quindi il trade-off è accettabile. In caso di debug ispettabile, l'utente può consultare `state.json` per mappare `file_id` → `file_name`.

Vedi anche [20-data-model.md](20-data-model.md) per l'estensione del modello `FileEntry`.

---

## Trigger 1 — Content change (incrementale via hash diff)

**Sorgente evento**: watcher sul file sorgente (es. `preventivo.docx` modificato).

**Flusso** (source file modificato → KS):

1. **Re-ingest** del file intero → markdown. Le librerie di ingestion (Docling, PyMuPDF4LLM, markitdown) **non sono incrementali** — producono sempre l'intero documento. Nessun problema: l'output è un markdown intermedio in memoria, non persistente.
2. Se `hash(markdown) == hash_stored` su `FileEntry` → **skip tutto** (false trigger, solo mtime cambiato).
3. **Re-chunk** del markdown intero → `new_chunks`.
4. Leggi `old_chunks` da Chroma (testo + `content_hash` dai metadata).
5. **Diff** per `chunk_id` (chiave stabile perché `file_id` immutato):
   - hash uguale → **skip embedding** (il vettore è già valido).
   - hash diverso → **re-embed + `upsert` Chroma**.
   - indice `i` nuovo (file cresciuto) → embed + insert.
   - indice `i` mancante (file rimosso/raccorciato) → delete da Chroma + disco + grafo.
6. **Riscrivi su disco solo i chunk cambiati** (aggiornati o nuovi). Cancella i `.md` degli indici scomparsi.
7. **Propaga al grafo**: solo i chunk "changed" o "new" triggerano re-estrazione LLM se `on_chunk_change = "eager"` (vedi [40-graph.md §5](40-graph.md)).

### Con `chunk_overlap > 0` (sliding window)

Una singola riga modificata appare in 2-3 chunk sovrapposti → re-embeddi 2-3 chunk, non 1. Accettabile: comunque << documento intero.

### Caso critico — inserimento in mezzo al documento

Gli indici shiftano e i `chunk_id` posizionali dopo l'inserimento "cambiano" anche se il contenuto è identico. Due opzioni:

| Approccio | Come | Pro/Contro |
|---|---|---|
| **A — allineamento via hash** | confronta vecchio/nuovo per `content_hash` (non per indice) usando `difflib.SequenceMatcher`, poi riassegna gli ID posizionali | ottimale (re-embed solo 1-2 chunk), ma complesso |
| **B — accetta lo shift** | re-embedda tutti i chunk dall'inserimento in poi | semplice, ok se file corti (preventivi .docx), pessimo su libri di 500 pagine |

**Scelta fase 1**: approccio **B** (semplice, copre bene i .docx del profilo consulente). **Fase 2**: valutare **A** se i benchmark su paper/libri lunghi mostrano re-embed eccessivi.

### Test

| Test | Cosa verifica |
|------|---------------|
| Edit riga singola → re-embed mirato | solo 1-2 chunk upsertati in Chroma, resto invariato |
| Re-save identico → skip | `hash(markdown)` invariato → nessuna scrittura |
| Troncamento file → cleanup | chunk oltre la nuova lunghezza cancellati da Chroma + disco |
| `chunk_overlap > 0` → re-embed finestra | 2-3 chunk re-embeddati, non 1 |
| Insert in mezzo (approccio B) | chunk dopo l'inserimento re-embeddati |

---

## Trigger 2 — Move / rename del file sorgente

**Sorgente evento**: watcher (move/rename evento).

**Flusso**:

1. KS rileva il move/rename via watcher (evento su stesso `file_id` — vedi prerequisito sopra).
2. **Update `FileEntry.path` + `FileEntry.name`** in `state.json`.
3. **Update metadata Chroma** dei chunk del file: `file_name` campo. `chunk_id` immutato (contiene `file_id`, non `file_name`).
4. **Update property Neo4j** sui nodi `Chunk` e `Document`: `file_name`, `path`. Niente re-estrazione entità, niente re-embed.
5. **Chunk su disco**: la cartella `<file_id>/` non si sposta (contiene `file_id`, non `file_name`). Nessuna scrittura.

**Casi speciali**:

- **Move cross-base**: il `chunk_id` contiene `base_name`, quindi cambio base = cambio id → trattato come delete + add. KS logga un warning ("move cross-base rilevato, re-index richiesto") e esegue il delete + add automatico.
- **Move cross-workspace**: KS non ha visibilità → il file sparisce dal vecchio workspace (delete) e ricompare nel nuovo (add indipendente, nuovi `file_id`/`chunk_id`).

### Test

| Test | Cosa verifica |
|------|---------------|
| Rename file → chunk_id immutato | stessi `chunk_id` prima e dopo |
| Rename file → Chroma metadati aggiornati | `file_name` cambiato, embedding invariato |
| Move cross-base → delete + add | nuovi `chunk_id`, vecchi cancellati |
| Move intra-base → zero re-embed | nessun `upsert` embedding |

---

## Trigger 3 — Cambio modello di embedding

**Sorgente evento**: cambio `[embedding].model` nel TOML della base.

**Problema**: `dim` del nuovo modello può differire → collection Chroma incompatibile, non si possono mescolare vettori.

**Gestione**:

- **Bloccato** se la collection Chroma non è vuota: KS lancia errore all'avvio suggerendo il comando esplicito.
- `ks reindex <base> --model-change`:
  1. Crea una nuova collection Chroma (nome: `<base>__<timestamp>` o `_new` temporaneo).
  2. Legge i chunk da disco (testo, NON embedding vecchi).
  3. Re-embed con il nuovo modello.
  4. Swap atomico: rinomina la collection nuova → nome definitivo, cancella la vecchia.
  5. Aggiorna `KnowledgeBase.embedding_model` in `state.json`.
  6. **Grafo**: il `embedding` property dei nodi `Chunk` in Neo4j va riscritto. KS propaga i nuovi vettori via `KSChunkLoader.upsert_chunk` + Cypher `SET chunk.embedding = $emb` (no re-estrazione entità).

**Chunk su disco**: intatti (il testo non cambia).

**Costo**: O(n_chunk) chiamate embedding. Per modelli locali = tempo + RAM; per API = costo $.

Vedi anche [40-graph.md §9](40-graph.md) (blocco + comando CLI).

### Test

| Test | Cosa verifica |
|------|---------------|
| Cambio model con collection vuota | permesso, nessun errore |
| Cambio model con collection non vuota | errore esplicito, suggerisce `--model-change` |
| `ks reindex --model-change` | nuova collection con `dim` nuova, vecchia cancellata, `embedding_model` aggiornato |
| Re-embed dopo cambio | vettori hanno `dim` del nuovo modello |

---

## Trigger 4 — Cambio strategia/parametri di chunking

**Sorgente evento**: cambio `[chunking].method` o parametri (`chunk_size`, `chunk_overlap`, `separator`, ...) nel TOML della base.

**Problema**: i confini dei chunk cambiano → il chunk 0 di prima non è il chunk 0 di dopo. `content_hash` per stesso `chunk_id` non combacia. **Tutto va ricalcolato**.

**Gestione**:

- **Bloccato** se la collection Chroma non è vuota: KS lancia errore all'avvio suggerendo:
  ```
  ks reindex <base> --chunking-change
  ```
- `ks reindex <base> --chunking-change`:
  1. Re-ingest del file (o riusa markdown cached se sorgente invariato).
  2. Re-chunk con la nuova strategia/parametri → `new_chunks`.
  3. **Backup opzionale** dei chunk vecchi in `<base>/.knowledge-space/chunks/<file_id>__<timestamp>/` (preserve per audit).
  4. Riscrivi `<file_id>/_chunk_<i>.md` con i nuovi contenuti.
  5. **Delete + insert** in Chroma: i `chunk_id` vecchi (se il numero di chunk cambia) o lo stesso id con testo diverso → `upsert`. In pratica, cancella tutti i chunk del `file_id` e re-inserisci (più semplice del diff, e giustificato dalla natura globale del cambio).
  6. Re-embed di tutti i nuovi chunk.
  7. **Grafo**: re-estrazione LLM completa del file (entità/relazioni potenzialmente diverse con chunk diversi). KS cancella i vecchi nodi `Chunk`/`Document`/`MENTIONS`/`FROM_DOCUMENT` del file e re-inserisce.

**Costo**: O(n_chunk) embedding + O(n_chunk) chiamate LLM per re-estrazione. Operazione costosa ma rara.

Vedi anche [40-graph.md](40-graph.md) per la propagazione al grafo.

### Test

| Test | Cosa verifica |
|------|---------------|
| Cambio method con collection non vuota | errore esplicito |
| `ks reindex --chunking-change` | nuovi chunk su disco, nuovi `chunk_id`/testo, embedding ricalcolati |
| Backup opzionale | vecchi chunk preservati in `__<timestamp>/` |
| Grafo re-indicizzato | vecchi nodi `Chunk` cancellati, nuovi con entità aggiornate |

---

## Trigger 5 — Cambio libreria/parametri di ingestion

**Sorgente evento**: cambio `[ingestion].library` o parametri (`use_gpu`, `do_ocr`, `page_chunks`, ...) nel TOML della base.

**Problema**: la conversione sorgente → markdown può produrre testo diverso (es. Docling con OCR vs PyMuPDF4LLM senza OCR sullo stesso PDF scanned). Tutto downstream va ricalcolato.

**Gestione**:

- **Bloccato** se la collection Chroma non è vuota: KS lancia errore all'avvio suggerendo:
  ```
  ks reindex <base> --ingestion-change
  ```
- `ks reindex <base> --ingestion-change`:
  1. Re-ingest con la nuova libreria/parametri → nuovo markdown.
  2. Se `hash(new_markdown) == hash(old_markdown)` → downgrade a no-op + warning ("configurazione cambiata ma output identico, nessun re-index necessario"). In pratica capita se l'utente cambia solo `use_gpu` (output deterministico).
  3. Altrimenti: re-chunk + re-embed + riscrittura `.md` + re-estrazione grafo (come trigger 4).

**Costo**: uguale al trigger 4 + costo ingestion (che può includere OCR, parsing PDF, ...).

### Test

| Test | Cosa verifica |
|------|---------------|
| Cambio library con collection non vuota | errore esplicito |
| `ks reindex --ingestion-change` | markdown nuovo, chunk/embedding/grafo ricalcolati |
| Output identico (es. `use_gpu` toggle) | no-op + warning |

---

## Tabella riassuntiva: comandi CLI

| Comando | Trigger | Costo tipico |
|---|---|---|
| (auto, via watcher) | 1 — content change | basso (diff) |
| (auto, via watcher) | 2 — move/rename | nullo |
| `ks reindex <base> --model-change` | 3 — embedding model | medio (re-embed tutti) |
| `ks reindex <base> --chunking-change` | 4 — chunking strategy/params | alto (re-chunk + re-embed + grafo) |
| `ks reindex <base> --ingestion-change` | 5 — ingestion library/params | alto (re-ingest + tutto downstream) |

> Tutti i comandi `ks reindex` sono **bloccanti e atomici**: KS non serve query durante il re-index (o serve dalla vecchia collection fino a swap completato). Per il primo sviluppo va bene bloccare; in futuro si può valutare zero-downtime con doppia collection.

---

## Integrazione con il grafo

Tutti i trigger 1, 3, 4, 5 propagano al grafo secondo `[graph].on_chunk_change` (rinominato da `on_chunk_edit` — vedi [40-graph.md §5](40-graph.md)):

- `"eager"` (default): KS lancia re-estrazione LLM sui chunk cambiati subito dopo l'aggiornamento Chroma.
- `"lazy"`: KS aggiorna solo Chroma; il grafo si riallinea al prossimo `ks graph sync <workspace>` esplicito.

Il trigger 2 (move/rename) non propaga al grafo come re-estrazione: solo update delle property `file_name`/`path` sui nodi esistenti.

## Fasi di implementazione

- **I0 — `file_id` prerequisito**: estensione `FileEntry` con `file_id: str` (UUID), `chunk_id` basato su `file_id`, path chunk su disco `<file_id>/_chunk_<i>.md`. Impatta Step 7 e 8-bis della Fase 1.
- **I1 — Content change (trigger 1)**: diff via `content_hash`, re-embed mirato, approccio B per insert. Prerequisito: `content_hash` su `ChunkRef` e metadata Chroma (già pianificato).
- **I2 — Move/rename (trigger 2)**: handler watcher per eventi move, update `FileEntry` + metadata Chroma + property Neo4j. Prerequisito: `file_id`.
- **I3 — Blocco cambio config (trigger 3, 4, 5)**: check all'avvio `BaseConfigLoader` vs `KnowledgeBase.embedding_model`/`chunking_method`/`ingestion_library` registrati in stato. Errore esplicito + suggerimento comando.
- **I4 — Comandi `ks reindex`**: implementazione dei 3 subcomandi (`--model-change`, `--chunking-change`, `--ingestion-change`). Fase 3 (CLI).
- **I5 — Propagazione grafo**: integrazione con `on_chunk_change` eager/lazy, scope mirato per trigger 1, full re-estrazione per trigger 4/5, property-only per trigger 2.
- **I6 — Test end-to-end**: 5 trigger × scenari tipici.

## Dipendenze

- **Dipende da:** Step 7 (KnowledgeBaseManager, file_id, content_hash)
- **Usato da:** Step 8-bis (propagazione grafo), Step 13 (CLI `reindex`)

## Test

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
| Backup chunk vecchi | opzione `--keep-old` preserva |

---

*Ultimo aggiornamento: 21 luglio 2026*
