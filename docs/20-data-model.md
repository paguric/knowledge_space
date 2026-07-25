# Modello di dominio e persistenza

> **Stato:** implementato | **Step:** 0 | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Decisioni chiave

| Aspetto | Scelta |
|---------|--------|
| Modelli | Pydantic (`Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef`) |
| Persistenza | Ibrida: indice globale + state.json per workspace |
| `file_id` | UUID4 stabile per la vita del file |
| `chunk_id` | `base::file_id::i` (disaccoppiato dal nome) |
| Chunk editabili | No — Chroma è fonte di verità |
| `GraphConfigData` | Uno per workspace, in `state.json` |

## Nota preliminare

Prima di avviare il refactor architetturale completo (REST, MCP, CLI, DI) conviene consolidare il **modello di dominio** — la struttura ad albero `Workspace → Domini → Basi → File → Chunk` — e la sua **persistenza su disco**. Avere il formato dati stabile *prima* del refactor evita di dover riscivere pezzi di architettura quando emergono nuovi requisiti sulla struttura JSON.

## Classi di dominio vs classi funzionali

| Tipo | Ruolo | Esempi | Deve fare I/O? |
|------|-------|--------|----------------|
| **Classe di dominio** | Rappresenta i dati e la loro struttura | `Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef` | No |
| **Classe funzionale / service / manager** | Implementa la logica, le operazioni, la sincronizzazione | `WorkspaceManager`, `KnowledgeBaseManager`, `SearchService` | Sì |

Le classi di dominio sono **modelli Pydantic**: contengono solo campi, tipi, default e validazione. Non caricano file, non avviano watcher, non calcolano embedding. Servono a rappresentare la struttura ad albero e a serializzarla in JSON.

Le classi funzionali ricevono le istanze di dominio e le manipolano: caricano, salvano, sincronizzano col filesystem, avviano `watchdog`, interagiscono con Chroma.

> **Esempio concreto**: la vecchia classe `KnowledgeBase` (che ora contiene dati, vector store, watcher e chunking) verrà separata in `KnowledgeBase` (modello Pydantic) e `KnowledgeBaseManager` (logica operativa).

## Persistenza ibrida

Scelta concordata: **indice globale + file di configurazione per workspace**.

- **Indice globale**: `~/.local/state/KnowledgeSpace/workspaces.json` contiene l'elenco dei path dei workspace registrati e metadati dell'applicazione, come l'ultimo workspace utilizzato (`last_workspace`).
- **Configurazione per workspace**: `<workspace>/.knowledge-space/state.json` contiene domini, basi, file, chunk e flag `active`.

**Vantaggi**:
- La configurazione segue il workspace se viene spostato.
- L'indice globale resta piccolo e semplice.
- Si separa il "catalogo" dell'applicazione dallo stato specifico di ogni workspace.

## Schema JSON del singolo workspace

File: `<workspace>/.knowledge-space/state.json`

```json
{
  "version": 1,
  "domains": [
    {
      "name": "domain1",
      "active": true,
      "base_names": ["test_kb1", "test_kb2"]
    }
  ],
  "bases": {
    "test_kb1": {
      "path": "/home/lapo225/test_ws2/test_kb1",
      "active": true,
      "embedding_model": "sentence-transformers/all-mpnet-base-v2",
      "files": {
        "descrizione_progtes.pdf": {
          "file_id": "8f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f",
          "mtime": 1783699858.842,
          "added": "2026-07-13T20:04:44",
          "active": true,
          "chunks": [
            {
              "index": 0,
              "active": true,
              "chunk_id": "test_kb1::8f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f::0",
              "content_hash": "a1b2c3d4..."
            },
            {
              "index": 1,
              "active": true,
              "chunk_id": "test_kb1::8f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f::1",
              "content_hash": "e5f6a7b8..."
            }
          ]
        }
      }
    }
  },
  "graph": {
    "bolt_uri": "bolt://localhost:7687",
    "database": "neo4j",
    "schema_ref": ".knowledge-space/schema.json",
    "embedding_model": "sentence-transformers/all-mpnet-base-v2",
    "retriever": "hybrid_cypher"
  }
}
```

I nuovi campi (`file_id`, `chunk_id`, `content_hash`, `embedding_model`, `chunking_method`, `ingestion_library`, `graph`) supportano la pipeline GraphRAG e l'indicizzazione incrementale. Il `graph.retriever` è il **valore di default workspace-level** per il metodo di ricerca (può essere sovrascritto per-base da `[graph].retriever` nel TOML della base — vedi [40-graph.md §14](40-graph.md)). `file_id` (UUID stabile) disaccoppia il `chunk_id` dal nome del file, abilitando move/rename senza recompute (vedi [45-indexing-incrementale.md](45-indexing-incrementale.md) trigger 2). I chunk non sono editabili dall'utente — Chroma è la fonte di verità.

## Schema JSON dell'indice globale

File: `~/.local/state/KnowledgeSpace/workspaces.json`

```json
{
  "version": 1,
  "last_workspace": "/home/lapo225/test_ws2",
  "workspaces": [
    "/home/lapo225/test_ws2",
    "/home/lapo225/altro_ws"
  ]
}
```

## Modelli Pydantic

```python
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List, Dict, Optional

class ChunkRef(BaseModel):
    """Riferimento a un chunk di un file. Il testo del chunk vive su disco
    (``<base>/.knowledge-space/chunks/<file_id>/<file_id>_chunk_<i>.md``), qui
    teniamo metadati per filtrare la ricerca e gestire l'indicizzazione
    incrementale. ``chunk_id`` è deterministico (``base::file_id::i``) e
    usato come chiave in Chroma e come ``Neo4jNode.id`` nel grafo
    (idempotenza del writer). ``content_hash`` rileva cambiamenti effettivi
    del testo (skip re-embed su re-ingest identica, vedi
    [45-indexing-incrementale.md](45-indexing-incrementale.md) trigger 1).
    I chunk **non** sono editabili dall'utente: Chroma è la fonte di
    verità, i file ``.md`` su disco sono un prodotto derivato del
    documento sorgente."""

    index: int
    active: bool = True
    chunk_id: str
    content_hash: str


class FileEntry(BaseModel):
    mtime: float
    added: str
    active: bool = True
    file_id: str   # UUID4 stabile per la vita del file; disaccoppia chunk_id
                   # dal nome del file (abilita move/rename senza recompute,
                   # vedi 45-indexing-incrementale.md trigger 2)
    chunks: List[ChunkRef] = Field(default_factory=list)


class KnowledgeBase(BaseModel):
    path: Path
    active: bool = True
    files: Dict[str, FileEntry] = Field(default_factory=dict)
    # Modello usato per indicizzare la collection Chroma. Serve a bloccare
    # il cambio modello embedding su collection non vuota (vedi
    # docs/45-indexing-incrementale.md trigger 3 e docs/40-graph.md §9).
    embedding_model: Optional[str] = None
    # Strategia di chunking e libreria di ingestion usate per indicizzare
    # la collection. Servono a bloccare il cambio config su collection non
    # vuota (vedi docs/45-indexing-incrementale.md trigger 4/5).
    chunking_method: Optional[str] = None
    ingestion_library: Optional[str] = None


class Domain(BaseModel):
    name: str
    active: bool = True
    base_names: List[str] = Field(default_factory=list)


class GraphConfigData(BaseModel):
    """Stato di connessione al grafo Neo4j del workspace (un grafo per
    workspace). I parametri comportamentali per-base vivono in ``[graph]``
    del ``BaseConfig`` (TOML); qui vive solo ciò che è condiviso da tutte
    le basi del workspace (connessione al DB, schema ref, modello emb.,
    retriever di default)."""

    bolt_uri: str = "bolt://localhost:7687"
    database: str = "neo4j"
    schema_ref: Optional[Path] = None
    embedding_model: Optional[str] = None
    retriever: str = "hybrid_cypher"   # default workspace; override per-base in [graph].retriever (TOML)


class Workspace(BaseModel):
    path: Path
    domains: List[Domain] = Field(default_factory=list)
    bases: Dict[str, KnowledgeBase] = Field(default_factory=dict)
    graph: Optional[GraphConfigData] = None
```

Serializzazione:

```python
ws = Workspace(path=Path("/home/lapo225/test_ws2"))
json_text = ws.model_dump_json(indent=2)
ws2 = Workspace.model_validate_json(json_text)
```

Rispetto a `to_dict()`/`from_dict()` manuali, Pydantic offre validazione automatica, gestione di tipi complessi (`Path`, `datetime`, liste, dizionari) e meno boilerplate.

## Piano preliminare

1. Definire i modelli Pydantic in `knowledge_base/models.py`.
2. Creare `WorkspaceConfig` per caricare/salvare `<workspace>/.knowledge-space/state.json`.
3. Creare `GlobalIndex` per caricare/salvare `~/.local/state/KnowledgeSpace/workspaces.json`, includendo `last_workspace`.
4. Implementare `sync_workspace()` per allineare il modello con il filesystem.
5. Aggiornare `last_workspace` quando un workspace viene aperto/usato.
6. Scrivere test di roundtrip JSON e di sincronizzazione.
7. Integrare gradualmente con le classi esistenti **senza** fare il grande refactor.

## Dipendenze

- **Dipende da:** nessuno (fondamenta)
- **Usato da:** Step 1 (workspace), Step 2 (domini), Step 7 (KnowledgeBaseManager), Step 8-bis (GraphRAG)

---

*Ultimo aggiornamento: 22 luglio 2026*
