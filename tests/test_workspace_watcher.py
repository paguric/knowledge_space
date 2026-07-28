"""Test per WorkspaceWatcher: verifica che sync venga chiamato su eventi FS."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_base.models import Workspace
from knowledge_base.persistence import GlobalIndex
from knowledge_base.workspace_manager import WorkspaceManager


def _make_manager(tmp_path: Path):
    index_path = tmp_path / "workspaces.json"
    config_root = tmp_path / "configs"

    def config_path_for(ws_path: Path) -> Path:
        return config_root / ws_path.name / "config.json"

    return WorkspaceManager(GlobalIndex(path=index_path), config_path_for)


class FakeObserver:
    """Observer fittizio che non avvia thread reali."""

    def __init__(self):
        self.handler = None
        self.stopped = False
        self.started = False

    def schedule(self, handler, path, recursive=False):
        self.handler = handler
        return object()

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def join(self):
        pass

    def dispatch(self, event=None):
        """Simula un evento FS invocando il handler registrato."""
        if self.handler:
            self.handler.on_any_event(event)


class TestWorkspaceWatcher:
    """Test del watcher con observer fittizio."""

    def test_start_registers_handler(self, tmp_path):
        """start() registra il handler sull'observer."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)

        watcher = mgr.start_watching(ws, observer_factory=FakeObserver)
        fake = watcher._observer
        watcher.start()

        assert fake.started is True
        assert fake.handler is not None
        watcher.stop()
        assert fake.stopped is True

    def test_dispatch_calls_sync(self, tmp_path):
        """Dispatching un evento FS chiama sync() sul workspace."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)

        # Crea una cartella PRIMA di avviare il watcher
        (ws_path / "kb_new").mkdir()

        watcher = mgr.start_watching(ws, observer_factory=FakeObserver)
        fake = watcher._observer
        watcher.start()

        # Simula evento FS
        fake.dispatch(None)

        # La sync deve aver scoperto kb_new
        assert "kb_new" in ws.bases
        watcher.stop()

    def test_dispatch_removes_deleted_base(self, tmp_path):
        """Dispatching un evento dopo cancellazione rimuove la base."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        (ws_path / "kb_old").mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)
        mgr.sync(ws)
        assert "kb_old" in ws.bases

        # Rimuovi la cartella
        import shutil

        shutil.rmtree(ws_path / "kb_old")

        watcher = mgr.start_watching(ws, observer_factory=FakeObserver)
        fake = watcher._observer
        watcher.start()

        # Simula evento FS
        fake.dispatch(None)

        assert "kb_old" not in ws.bases
        watcher.stop()

    def test_stop_stops_observer(self, tmp_path):
        """stop() ferma l'observer."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)

        watcher = mgr.start_watching(ws, observer_factory=FakeObserver)
        fake = watcher._observer
        watcher.start()
        watcher.stop()

        assert fake.stopped is True

    def test_watcher_import_from_watcher_module(self):
        """Il modulo workspace_watcher ri-exporta WorkspaceWatcher."""
        from knowledge_base.workspace_watcher import WorkspaceWatcher as WW

        assert WW is not None
