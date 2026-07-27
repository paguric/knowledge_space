"""conftest di livello repository.

Isola lo stato XDG (config/data/state) per i test che usano la CLI in-process
via CliRunner, impedendo scritture nell'indice globale reale
(~/.local/state/KnowledgeSpace/workspaces.json)."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "xdg-home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(root / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(root / "state"))
