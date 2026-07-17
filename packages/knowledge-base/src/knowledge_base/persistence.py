"""Persistenza ibrida su disco.

- ``GlobalIndex``: legge/scrive l'indice globale dei workspace registrati
  (``~/.local/state/KnowledgeSpace/workspaces.json``).
- ``WorkspaceConfig``: legge/scrive la configurazione di un singolo workspace
  (``<workspace>/.knowledge-space/config.json``).

Entrambi i loader non usano variabili globali: il path del file viene passato
al costruttore (con default XDG), così i test possono iniettare un path temporaneo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from knowledge_base.models import (
    GlobalIndexData,
    Workspace,
    WorkspaceConfigData,
)

APP_NAME = "KnowledgeSpace"


def _default_global_index_path() -> Path:
    """Restituisce il path XDG di default per l'indice globale."""
    xdg_state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(xdg_state) / APP_NAME / "workspaces.json"


class GlobalIndex:
    """Loader/saver dell'indice globale dei workspace."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path: Path = Path(path) if path is not None else _default_global_index_path()

    def _read(self) -> GlobalIndexData:
        if not self.path.exists():
            return GlobalIndexData()
        with open(self.path, "r", encoding="utf-8") as f:
            return GlobalIndexData.model_validate_json(f.read())

    def _write(self, data: GlobalIndexData) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=2))

    def load(self) -> GlobalIndexData:
        """Restituisce l'indice globale (vuoto se il file non esiste)."""
        return self._read()

    def save(self, data: GlobalIndexData) -> None:
        """Scrive l'indice globale su disco."""
        self._write(data)

    def list_workspaces(self) -> List[Path]:
        """Restituisce i path dei workspace registrati."""
        return self._read().workspaces

    def get_last_workspace(self) -> Optional[Path]:
        """Restituisce l'ultimo workspace usato, se presente."""
        return self._read().last_workspace

    def set_last_workspace(self, workspace_path: Path) -> None:
        """Imposta l'ultimo workspace usato."""
        data = self._read()
        data.last_workspace = Path(workspace_path)
        self._write(data)

    def add_workspace(self, workspace_path: Path) -> bool:
        """Registra un workspace. Restituisce ``True`` se era nuovo."""
        data = self._read()
        ws = Path(workspace_path)
        if ws in data.workspaces:
            return False
        data.workspaces.append(ws)
        self._write(data)
        return True

    def remove_workspace(self, workspace_path: Path) -> bool:
        """Deregistra un workspace. Restituisce ``True`` se era presente."""
        data = self._read()
        ws = Path(workspace_path)
        if ws not in data.workspaces:
            return False
        data.workspaces = [w for w in data.workspaces if w != ws]
        if data.last_workspace == ws:
            data.last_workspace = None
        self._write(data)
        return True


class WorkspaceConfig:
    """Loader/saver della configurazione di un singolo workspace."""

    def __init__(self, workspace_path: Path) -> None:
        self.workspace_path: Path = Path(workspace_path)
        self.dir: Path = self.workspace_path / ".knowledge-space"
        self.path: Path = self.dir / "config.json"

    def exists(self) -> bool:
        """Restituisce ``True`` se il file di configurazione esiste."""
        return self.path.exists()

    def load(self) -> WorkspaceConfigData:
        """Carica la configurazione del workspace (vuota se il file non esiste)."""
        if not self.path.exists():
            return WorkspaceConfigData()
        with open(self.path, "r", encoding="utf-8") as f:
            return WorkspaceConfigData.model_validate_json(f.read())

    def save(self, data: Optional[WorkspaceConfigData] = None) -> None:
        """Scrive la configurazione del workspace su disco."""
        if data is None:
            data = WorkspaceConfigData()
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=2))

    def init_default(self) -> None:
        """Crea il file di configurazione con i default se non esiste."""
        if not self.exists():
            self.save(WorkspaceConfigData())

    def to_workspace(self) -> Workspace:
        """Restituisce il modello :class:`Workspace` costruito dalla configurazione."""
        data = self.load()
        return Workspace(
            path=self.workspace_path,
            domains=data.domains,
            bases=data.bases,
        )