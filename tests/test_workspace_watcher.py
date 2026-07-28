"""Test per WorkspaceWatcher: verifica che sync venga chiamato su eventi FS."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

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

    def dispatch_created(self, event=None):
        """Simula un evento on_created invocando il handler registrato."""
        if self.handler:
            self.handler.on_created(event)

    def dispatch_deleted(self, event=None):
        """Simula un evento on_deleted invocando il handler registrato."""
        if self.handler:
            self.handler.on_deleted(event)

    def dispatch_moved(self, event=None):
        """Simula un evento on_moved invocando il handler registrato."""
        if self.handler:
            self.handler.on_moved(event)


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
        """Dispatching un evento on_created chiama sync() sul workspace."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)

        # Crea una cartella PRIMA di avviare il watcher
        (ws_path / "kb_new").mkdir()

        watcher = mgr.start_watching(
            ws, observer_factory=FakeObserver, debounce_seconds=0.0
        )
        fake = watcher._observer
        watcher.start()

        # Simula evento on_created
        fake.dispatch_created(None)
        # Il debounce esegue sync in un thread separato; attendiamo
        time.sleep(0.05)

        # La sync deve aver scoperto kb_new
        assert "kb_new" in ws.bases
        watcher.stop()

    def test_on_deleted_triggers_sync(self, tmp_path):
        """Dispatching un evento on_deleted dopo cancellazione rimuove la base."""
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

        watcher = mgr.start_watching(
            ws, observer_factory=FakeObserver, debounce_seconds=0.0
        )
        fake = watcher._observer
        watcher.start()

        # Simula evento on_deleted
        fake.dispatch_deleted(None)
        # Il debounce esegue sync in un thread separato; attendiamo
        time.sleep(0.05)

        assert "kb_old" not in ws.bases
        watcher.stop()

    def test_on_moved_triggers_sync(self, tmp_path):
        """Dispatching un evento on_moved triggera sync()."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        (ws_path / "kb_src").mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)
        mgr.sync(ws)
        assert "kb_src" in ws.bases

        # Simula uno spostamento rinominando la cartella
        (ws_path / "kb_src").rename(ws_path / "kb_dst")

        watcher = mgr.start_watching(
            ws, observer_factory=FakeObserver, debounce_seconds=0.0
        )
        fake = watcher._observer
        watcher.start()

        # Simula evento on_moved
        fake.dispatch_moved(None)
        # Il debounce esegue sync in un thread separato; attendiamo
        time.sleep(0.05)

        assert "kb_src" not in ws.bases
        assert "kb_dst" in ws.bases
        watcher.stop()

    def test_debounce_does_not_sync_multiple_times(self, tmp_path):
        """Dispatch di eventi rapidi genera UNA sola sync()."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)

        watcher = mgr.start_watching(
            ws, observer_factory=FakeObserver, debounce_seconds=0.1
        )
        fake = watcher._observer
        watcher.start()

        # Patch per contare le chiamate a sync
        original_sync = mgr.sync
        call_count = 0

        def counting_sync(workspace):
            nonlocal call_count
            call_count += 1
            return original_sync(workspace)

        mgr.sync = counting_sync  # type: ignore[assignment]

        # 3 eventi rapidi: il debounce deve collassarli in una sola sync
        fake.dispatch_created(None)
        fake.dispatch_created(None)
        fake.dispatch_created(None)

        # Aspetta che il debounce scada
        time.sleep(0.3)

        assert call_count == 1
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
