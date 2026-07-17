# Modello di dominio e persistenza

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
- **Configurazione per workspace**: `<workspace>/.knowledge-space/config.json` contiene domini, basi, file, chunk e flag `active`.

**Vantaggi**:
- La configurazione segue il workspace se viene spostato.
- L'indice globale resta piccolo e semplice.
- Si separa il "catalogo" dell'applicazione dallo stato specifico di ogni workspace.

## Schema JSON del singolo workspace

File: `<workspace>/.knowledge-space/config.json`

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
      "files": {
        "descrizione_progtes.pdf": {
          "mtime": 1783699858.842,
          "added": "2026-07-13T20:04:44",
          "active": true,
          "chunks": [
            { "index": 0, "active": true },
            { "index": 1, "active": true }
          ]
        }
      }
    }
  }
}
```

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
from typing import List, Dict

class ChunkRef(BaseModel):
    index: int
    active: bool = True

class FileEntry(BaseModel):
    mtime: float
    added: str
    active: bool = True
    chunks: List[ChunkRef] = Field(default_factory=list)

class KnowledgeBase(BaseModel):
    path: Path
    active: bool = True
    files: Dict[str, FileEntry] = Field(default_factory=dict)

class Domain(BaseModel):
    name: str
    active: bool = True
    base_names: List[str] = Field(default_factory=list)

class Workspace(BaseModel):
    path: Path
    domains: List[Domain] = Field(default_factory=list)
    bases: Dict[str, KnowledgeBase] = Field(default_factory=dict)
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
2. Creare `WorkspaceConfig` per caricare/salvare `<workspace>/.knowledge-space/config.json`.
3. Creare `GlobalIndex` per caricare/salvare `~/.local/state/KnowledgeSpace/workspaces.json`, includendo `last_workspace`.
4. Implementare `sync_workspace()` per allineare il modello con il filesystem.
5. Aggiornare `last_workspace` quando un workspace viene aperto/usato.
6. Scrivere test di roundtrip JSON e di sincronizzazione.
7. Integrare gradualmente con le classi esistenti **senza** fare il grande refactor.
