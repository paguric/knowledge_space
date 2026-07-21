"""RuntimePaths — path XDG e convenzioni .knowledge-space/ del workspace.

Questa classe racchiude tutti i path necessari all'applicazione, mantenendo
lo standard XDG Base Directory Specification. I path sono calcolati una
sola volta e passati esplicitamente ai manager; nessuna variabile globale.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from knowledge_space.constants import APP_NAME


class RuntimePaths(BaseModel):
    """Path dell'applicazione, conformi a XDG.

    - ``config_home``: ``~/.config/KnowledgeSpace/`` (UserSettings, secrets)
    - ``data_home``: ``~/.local/share/KnowledgeSpace/`` (chunk, dati grandi)
    - ``state_home``: ``~/.local/state/KnowledgeSpace/`` (indici, log, DB)
    """

    model_config = {"frozen": True}

    config_home: Path
    data_home: Path
    state_home: Path
    dot_folder_name: str = ".knowledge-space"

    @classmethod
    def default(cls, app_name: Optional[str] = None) -> "RuntimePaths":
        """Costruisce i path standard XDG per l'applicazione.

        Rispetta le variabili d'ambiente ``XDG_CONFIG_HOME``, ``XDG_DATA_HOME``
        e ``XDG_STATE_HOME``; in loro assenza usa i default freedesktop.
        """
        name = app_name or APP_NAME
        xdg_config = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        xdg_data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        xdg_state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
        return cls(
            config_home=Path(xdg_config) / name,
            data_home=Path(xdg_data) / name,
            state_home=Path(xdg_state) / name,
        )

    # .................................................................... #
    # Path derivati (applicazione)
    # .................................................................... #

    @property
    def user_settings_file(self) -> Path:
        """``~/.config/KnowledgeSpace/config.json`` (secrets, preferenze)."""
        return self.config_home / "config.json"

    @property
    def workspaces_index(self) -> Path:
        """``~/.local/state/KnowledgeSpace/workspaces.json``."""
        return self.state_home / "workspaces.json"

    @property
    def log_file(self) -> Path:
        """``~/.local/state/KnowledgeSpace/log``."""
        return self.state_home / "log"

    # .................................................................... #
    # Path derivati (workspace)
    # .................................................................... #

    def workspace_dot_dir(self, workspace_path: Path) -> Path:
        """``<workspace>/.knowledge-space/``."""
        return workspace_path / self.dot_folder_name

    def workspace_state_file(self, workspace_path: Path) -> Path:
        """``<workspace>/.knowledge-space/state.json``."""
        return self.workspace_dot_dir(workspace_path) / "state.json"

    def workspace_defaults_toml(self, workspace_path: Path) -> Path:
        """``<workspace>/.knowledge-space/defaults.toml``."""
        return self.workspace_dot_dir(workspace_path) / "defaults.toml"

    def workspace_graph_dir(self, workspace_path: Path) -> Path:
        """``<workspace>/.knowledge-space/graph/``."""
        return self.workspace_dot_dir(workspace_path) / "graph"

    def base_dot_dir(self, workspace_path: Path, base_name: str) -> Path:
        """``<workspace>/<base>/.knowledge-space/``."""
        return workspace_path / base_name / self.dot_folder_name

    def base_toml(self, workspace_path: Path, base_name: str) -> Path:
        """``<workspace>/<base>/.knowledge-space/base.toml``."""
        return self.base_dot_dir(workspace_path, base_name) / "base.toml"

    def base_chunks_dir(self, workspace_path: Path, base_name: str) -> Path:
        """``<workspace>/<base>/.knowledge-space/chunks/``."""
        return self.base_dot_dir(workspace_path, base_name) / "chunks"

    # .................................................................... #
    # Setup
    # .................................................................... #

    def ensure_dirs(self) -> None:
        """Crea le directory XDG se non esistono."""
        self.config_home.mkdir(parents=True, exist_ok=True)
        self.data_home.mkdir(parents=True, exist_ok=True)
        self.state_home.mkdir(parents=True, exist_ok=True)
