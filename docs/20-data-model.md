# Modello di dominio e persistenza

> **Stato:** implementato | **Step:** 0 | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Panoramica

Definisce la struttura ad albero `Workspace → Domini → Basi → File → Chunk` e la sua persistenza su disco. Il modello di dominio (Pydantic) è separato dalle classi funzionali (manager/service) che implementano la logica operativa.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Modelli | Pydantic (`Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef`) |
| Persistenza | Ibrida: indice globale + state.json per workspace |
| `file_id` | UUID4 stabile per la vita del file |
| `chunk_id` | `base::file_id::i` (disaccoppiato dal nome) |
| Chunk editabili | No — Chroma è fonte di verità |
| `GraphConfigData` | Uno per workspace, in `state.json` |

## Dettagli

### Classi di dominio vs classi funzionali

| Tipo | Ruolo | Esempi | Deve fare I/O? |
|------|-------|--------|----------------|
| **Classe di dominio** | Rappresenta i dati e la loro struttura | `Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef` | No |
| **Classe funzionale / service / manager** | Implementa la logica, le operazioni, la sincronizzazione | `WorkspaceManager`, `KnowledgeBaseManager`, `SearchService` | Sì |

Le classi di dominio sono modelli Pydantic: solo campi, tipi, default e validazione. Le classi funzionali ricevono le istanze di dominio e le manipolano.

### Persistenza ibrida

- **Indice globale**: `~/.local/state/KnowledgeSpace/workspaces.json` — elenco path dei workspace registrati e `last_workspace`.
- **Configurazione per workspace**: `<workspace>/.knowledge-space/state.json` — domini, basi, file, chunk e flag `active`.

Vantaggi: la configurazione segue il workspace se viene spostato; l'indice globale resta piccolo; separa il "catalogo" dell'applicazione dallo stato specifico.

### Schema JSON del singolo workspace

File: `<workspace>/.knowledge-space/state.json`

```json
{
  "version": 1,
  "domains": [
    { "name": "domain1", "active": true, "base_names": ["test_kb1", "test_kb2"] }
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
            { "index": 0, "active": true, "chunk_id": "test_kb1::8f1c2d3e-...::0", "content_hash": "a1b2c3d4..." },
            { "index": 1, "active": true, "chunk_id": "test_kb1::8f1c2d3e-...::1", "content_hash": "e5f6a7b8..." }
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

Campi aggiuntivi per GraphRAG e indicizzazione incrementale: `file_id`, `chunk_id`, `content_hash`, `embedding_model`, `chunking_method`, `ingestion_library`. `graph.retriever` è il default workspace-level (override per-base in `[graph].retriever` TOML). I chunk non sono editabili — Chroma è fonte di verità.

### Schema JSON dell'indice globale

File: `~/.local/state/KnowledgeSpace/workspaces.json`

```json
{
  "version": 1,
  "last_workspace": "/home/lapo225/test_ws2",
  "workspaces": ["/home/lapo225/test_ws2", "/home/lapo225/altro_ws"]
}
```

### Modelli Pydantic

```python
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List, Dict, Optional

class ChunkRef(BaseModel):
    """Riferimento a un chunk. Testo su disco, qui metadati per filtrare e gestire l'indicizzazione incrementale."""
    index: int
    active: bool = True
    chunk_id: str
    content_hash: str

class FileEntry(BaseModel):
    mtime: float
    added: str
    active: bool = True
    file_id: str   # UUID4 stabile, disaccoppia chunk_id dal nome
    chunks: List[ChunkRef] = Field(default_factory=list)

class KnowledgeBase(BaseModel):
    path: Path
    active: bool = True
    files: Dict[str, FileEntry] = Field(default_factory=dict)
    embedding_model: Optional[str] = None
    chunking_method: Optional[str] = None
    ingestion_library: Optional[str] = None

class Domain(BaseModel):
    name: str
    active: bool = True
    base_names: List[str] = Field(default_factory=list)

class GraphConfigData(BaseModel):
    """Stato connessione grafo Neo4j del workspace (uno per workspace)."""
    bolt_uri: str = "bolt://localhost:7687"
    database: str = "neo4j"
    schema_ref: Optional[Path] = None
    embedding_model: Optional[str] = None
    retriever: str = "hybrid_cypher"

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

### Fasi di implementazione

1. Definire i modelli Pydantic in `knowledge_base/models.py`.
2. Creare `WorkspaceConfig` per caricare/salvare `state.json`.
3. Creare `GlobalIndex` per caricare/salvare `workspaces.json`.
4. Implementare `sync_workspace()` per allineare il modello con il filesystem.
5. Aggiornare `last_workspace` quando un workspace viene aperto.
6. Scrivere test di roundtrip JSON e di sincronizzazione.
7. Integrare gradualmente con le classi esistenti senza grande refactor.

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Nessuno (fondamenta) | Step 1 (workspace), Step 2 (domini), Step 7 (KnowledgeBaseManager), Step 8-bis (GraphRAG) |
