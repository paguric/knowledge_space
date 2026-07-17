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
    qui teniamo solo metadati per filtrare la ricerca."""

    index: int
    active: bool = True


class FileEntry(BaseModel):
    """Un file indicizzato in una base di conoscenza."""

    mtime: float
    added: str  # timestamp ISO 8601, es. "2026-07-13T20:04:44"
    active: bool = True
    chunks: List[ChunkRef] = Field(default_factory=list)


class KnowledgeBase(BaseModel):
    """Una base di conoscenza: una cartella di file indicizzati."""

    path: Path
    active: bool = True
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