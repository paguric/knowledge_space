"""Persistenza su disco per il modello di dominio.

- ``GlobalIndex``: legge/scrive l'indice globale dei workspace registrati.
- ``WorkspaceConfig``: legge/scrive la configurazione di un singolo workspace.

Entrambi i loader non usano variabili globali: il path del file viene passato
esplicitamente al costruttore. La libreria non conosce il nome dell'applicazione
né le convenzioni XDG: l'applicazione chiamante (``knowledge-space``) calcola
i path e li inietta.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from knowledge_base.models import (
    GlobalIndexData,
    Workspace,
    WorkspaceConfigData,
)


class GlobalIndex:
    """Loader/saver dell'indice globale dei workspace.

    Il path del file indice viene passato esplicitamente; la libreria non
    presume dove possa vivere su disco.
    """

    def __init__(self, path: Path) -> None:
        self.path: Path = Path(path)

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

    def clear_last_workspace(self) -> None:
        """Rimuove il riferimento al workspace attivo (ultimo usato)."""
        data = self._read()
        data.last_workspace = None
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
    """Loader/saver della configurazione di un singolo workspace.

    Il path del file di configurazione viene passato esplicitamente: la
    libreria non presume il nome della sottocartella nÃ© la struttura del
    workspace. L'applicazione chiamante decide dove salvare ``config.json``.
    """

    def __init__(self, config_path: Path, workspace_path: Path) -> None:
        self.config_path: Path = Path(config_path)
        self.workspace_path: Path = Path(workspace_path)

    def exists(self) -> bool:
        """Restituisce ``True`` se il file di configurazione esiste."""
        return self.config_path.exists()

    def load(self) -> WorkspaceConfigData:
        """Carica la configurazione del workspace (vuota se il file non esiste)."""
        if not self.config_path.exists():
            return WorkspaceConfigData()
        with open(self.config_path, "r", encoding="utf-8") as f:
            return WorkspaceConfigData.model_validate_json(f.read())

    def save(self, data: Optional[WorkspaceConfigData] = None) -> None:
        """Scrive la configurazione del workspace su disco."""
        if data is None:
            data = WorkspaceConfigData()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
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