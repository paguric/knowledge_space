"""Modelli di dominio in Pydantic.

Questi modelli sono *solo dati*: rappresentano la struttura ad albero
``Workspace -> Domain -> KnowledgeBase -> FileEntry -> ChunkRef`` e la
serializzano in JSON. Non contengono logica di I/O, watchers o vector store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ChunkRef(BaseModel):
    """Riferimento a un chunk di un file. Il testo del chunk vive su disco,
    qui teniamo solo metadati per filtrare la ricerca (``content_hash`` è
    usato dal diff incrementale — trigger 1 di
    ``docs/45-indexing-incrementale.md``).

    Lo Stato legacy usava ``edited``/``edited_mtime`` per tracciare
    modifiche; sono stati rimossi a favore del confronto via hash, che
    disaccoppia la detection del cambiamento dal timestamp (un save
    identico non triggera più re-embed, vedi trigger 1 § "Re-save
    identico → skip")."""

    index: int
    active: bool = True
    content_hash: Optional[str] = None


class FileEntry(BaseModel):
    """Un file indicizzato in una base di conoscenza.

    ``file_id`` (UUID4) è assegnato alla prima indicizzazione e **stabile
    per la vita del file**: disaccoppia il ``chunk_id`` dal nome del file
    sorgente, così un rename/move non cambia gli id Chroma/grafo (trigger
    2 di ``docs/45-indexing-incrementale.md``). ``name`` è il nome del file
    (mutabile su rename).
    """

    mtime: float
    added: str  # timestamp ISO 8601, es. "2026-07-13T20:04:44"
    file_id: Optional[str] = None
    name: Optional[str] = None
    # ``content_hash`` a livello di file (markdown intero): usato per
    # short-circuitare il re-index quando il sorgente è invariato.
    content_hash: Optional[str] = None
    # Path relativo alla base del Markdown salvato dopo l'ingestione
    # (feat-007): ``.knowledge-space/documents/{file_id}.md``. ``None``
    # per basi indicizzate prima della feature (fallback: riconversione).
    doc_path: Optional[str] = None
    active: bool = True
    chunks: List[ChunkRef] = Field(default_factory=list)


class KnowledgeBase(BaseModel):
    """Una base di conoscenza: una cartella di file indicizzati.

    ``embedding_model``, ``chunking_method`` e ``ingestion_library``
    registrano l'ultima configurazione usata per popolare Chroma; sono
    confrontati da :func:`check_config_change_blocked` all'avvio per
    bloccare cambi che richiederebbero un reindex esplicito (trigger 3/4/5
    di ``docs/45-indexing-incrementale.md``). ``None`` = base mai
    indicizzata (nessun blocco possibile)."""

    path: Path
    active: bool = True
    embedding_model: Optional[str] = None
    chunking_method: Optional[str] = None
    ingestion_library: Optional[str] = None
    files: Dict[str, FileEntry] = Field(default_factory=dict)


class Domain(BaseModel):
    """Un dominio: raggruppamento logico di basi di conoscenza."""

    name: str
    active: bool = True
    base_names: List[str] = Field(default_factory=list)


class Workspace(BaseModel):
    """Un workspace: cartella radice che contiene basi e domini."""

    path: Path
    domains: List[Domain] = Field(default_factory=list)
    bases: Dict[str, KnowledgeBase] = Field(default_factory=dict)


class GraphConfigData(BaseModel):
    """Configurazione del grafo di conoscenza per un workspace (Fase 1C).

    Definita qui come placeholder con valori di default -utile per la
    migrazione retroattiva dei ``state.json`` esistenti (Step 7 bullet
    migrazione) e per il blocco cambio config. Implementazione concreta
    in Fase 1C (vedi ``docs/40-graph.md``)."""

    enabled: bool = False
    on_chunk_change: str = "lazy"  # "eager" | "lazy"
    retriever: str = "none"        # "none" | "text2cypher" | "hybrid"
    extraction_model: Optional[str] = None
    schema_model: Optional[str] = None


class GlobalIndexData(BaseModel):
    """Payload di ``~/.local/state/KnowledgeSpace/workspaces.json``:
    elenco dei workspace registrati e ultimo workspace usato."""

    version: int = 1
    last_workspace: Optional[Path] = None
    workspaces: List[Path] = Field(default_factory=list)


class WorkspaceConfigData(BaseModel):
    """Payload di ``<workspace>/.knowledge-space/config.json``:
    struttura ad albero di domini e basi di un singolo workspace."""

    version: int = 1
    domains: List[Domain] = Field(default_factory=list)
    bases: Dict[str, KnowledgeBase] = Field(default_factory=dict)
    graph: Optional[GraphConfigData] = None