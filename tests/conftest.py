"""conftest di livello repository.

Isola lo stato XDG (config/data/state) per i test che usano la CLI in-process
via CliRunner, impedendo scritture nell'indice globale reale
(~/.local/state/KnowledgeSpace/workspaces.json).

Resetta inoltre lo stato del logging per evitare che il flag ``_configured``
persista tra test consecutivi e che gli handler ``ks_*`` restino attivi.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture(autouse=True)
def _isolate_xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "xdg-home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(root / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(root / "state"))


def _cleanup_ks_handlers() -> None:
    """Rimuove e chiude tutti gli handler ``ks_*`` dal root logger."""
    root = logging.getLogger()
    for h in root.handlers[:]:
        if (h.name or "").startswith("ks_"):
            root.removeHandler(h)
            h.close()


@pytest.fixture(autouse=True)
def _reset_logging_state() -> Generator[None, None, None]:
    """Resetta il flag ``_configured`` e pulisce gli handler ``ks_*
    prima e dopo ogni test."""
    import knowledge_space.logging as log_mod

    old_configured = log_mod._configured
    log_mod._configured = False
    _cleanup_ks_handlers()
    yield
    _cleanup_ks_handlers()
    log_mod._configured = old_configured
