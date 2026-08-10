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

    def test_start_esegue_sync_iniziale(self, tmp_path):
        """Bug 017: start() scopre basi create mentre il watcher era spento."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)

        # Base creata PRIMA di avviare il watcher (watcher "spento")
        (ws_path / "kb_offline").mkdir()

        watcher = mgr.start_watching(
            ws, observer_factory=FakeObserver, debounce_seconds=0.0
        )
        fake = watcher._observer
        watcher.start()

        # Nessun evento FS: la sync iniziale di start() deve scoprire kb_offline
        time.sleep(0.2)

        assert "kb_offline" in ws.bases
        watcher.stop()

    def test_start_non_duplica_sync_con_eventi_immediati(self, tmp_path):
        """Bug 017: sync iniziale + eventi subito dopo → mai in parallelo."""
        import threading

        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)

        original_sync = mgr.sync
        call_count = 0
        counter_lock = threading.Lock()

        def counting_sync(workspace):
            nonlocal call_count
            with counter_lock:
                call_count += 1
            return original_sync(workspace)

        mgr.sync = counting_sync  # type: ignore[assignment]

        # Debounce realistico: l'evento immediato resetta il timer della
        # sync iniziale → i due si fondono in una sola sync.
        watcher = mgr.start_watching(
            ws, observer_factory=FakeObserver, debounce_seconds=0.1
        )
        fake = watcher._observer
        watcher.start()

        # Evento immediato dopo lo start: si fonde con la sync iniziale
        fake.dispatch_created(None)

        time.sleep(0.4)

        assert call_count == 1, f"attesa 1 sync, trovate {call_count}"
        watcher.stop()

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

    def test_sync_non_sovrapposta(self, tmp_path):
        """Bug 016: sync in corso → chiamate successive accodate, mai parallele."""
        import threading

        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)

        original_sync = mgr.sync
        call_count = 0
        parallel = 0
        max_parallel = 0
        in_progress = threading.Event()
        counter_lock = threading.Lock()

        def slow_sync(workspace):
            nonlocal call_count, parallel, max_parallel
            with counter_lock:
                call_count += 1
                parallel += 1
                max_parallel = max(max_parallel, parallel)
            try:
                in_progress.set()
                time.sleep(0.2)
                return original_sync(workspace)
            finally:
                with counter_lock:
                    parallel -= 1

        mgr.sync = slow_sync  # type: ignore[assignment]

        watcher = mgr.start_watching(
            ws, observer_factory=FakeObserver, debounce_seconds=0.0
        )
        fake = watcher._observer
        watcher.start()

        # Primo evento: parte la sync lenta
        fake.dispatch_created(None)
        assert in_progress.wait(2.0), "la prima sync non è partita"

        # Secondo evento DURANTE la sync: accodato, non eseguito in parallelo
        fake.dispatch_created(None)

        time.sleep(1.0)

        assert max_parallel == 1, f"sync in parallelo: {max_parallel}"
        assert call_count == 2, f"attese 2 sync, trovate {call_count}"
        watcher.stop()

    def test_eventi_durante_sync_generano_una_sola_ripetizione(self, tmp_path):
        """Bug 016: N eventi durante una sync → solo 1 sync aggiuntiva."""
        import threading

        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)
        ws = mgr.load(ws_path)

        original_sync = mgr.sync
        call_count = 0
        in_progress = threading.Event()

        def slow_sync(workspace):
            nonlocal call_count
            call_count += 1
            in_progress.set()
            time.sleep(0.3)
            return original_sync(workspace)

        mgr.sync = slow_sync  # type: ignore[assignment]

        watcher = mgr.start_watching(
            ws, observer_factory=FakeObserver, debounce_seconds=0.0
        )
        fake = watcher._observer
        watcher.start()

        fake.dispatch_created(None)
        assert in_progress.wait(2.0), "la prima sync non è partita"

        # 5 eventi durante la sync: si compattano in una sola ripetizione
        for _ in range(5):
            fake.dispatch_created(None)

        time.sleep(1.5)

        assert call_count == 2, f"attese 2 sync (1 + 1 pendente), trovate {call_count}"
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


# --------------------------------------------------------------------------- #
# Test WorkspacesWatcher (dinamico su workspaces.json)
# --------------------------------------------------------------------------- #

import threading
from unittest.mock import MagicMock

from knowledge_space.cli.serve import WorkspacesWatcher, _WorkspacesFileHandler


class TestWorkspacesFileHandler:
    """Test del handler watchdog su workspaces.json."""

    def test_on_modified_sets_event(self, tmp_path):
        """on_modified segnala l'event se il path corrisponde."""
        event = threading.Event()
        json_path = tmp_path / "workspaces.json"
        handler = _WorkspacesFileHandler(json_path, event)

        mock_event = MagicMock()
        mock_event.src_path = str(json_path)

        handler.on_modified(mock_event)
        assert event.is_set()

    def test_on_modified_ignores_other_file(self, tmp_path):
        """on_modified ignora modifiche ad altri file."""
        event = threading.Event()
        json_path = tmp_path / "workspaces.json"
        handler = _WorkspacesFileHandler(json_path, event)

        mock_event = MagicMock()
        mock_event.src_path = str(tmp_path / "other.json")

        handler.on_modified(mock_event)
        assert not event.is_set()

    def test_on_created_sets_event(self, tmp_path):
        """on_created segnala l'event se il path corrisponde."""
        event = threading.Event()
        json_path = tmp_path / "workspaces.json"
        handler = _WorkspacesFileHandler(json_path, event)

        mock_event = MagicMock()
        mock_event.src_path = str(json_path)

        handler.on_created(mock_event)
        assert event.is_set()


class TestWorkspacesWatcher:
    """Test del watcher dinamico su workspaces.json."""

    def test_sync_adds_new_workspace_watcher(self, tmp_path):
        """_sync_workspaces aggiunge un watcher per un workspace nuovo."""
        mgr = _make_manager(tmp_path)
        ws_existing = tmp_path / "ws_existing"
        ws_existing.mkdir()
        mgr.add(ws_existing)

        # Simula un watcher già attivo per ws_existing
        existing_watcher = MagicMock()
        existing_watcher._workspace = MagicMock()
        existing_watcher._workspace.path = ws_existing

        json_path = tmp_path / "workspaces.json"
        lock = threading.Lock()
        change_event = threading.Event()
        watchers = [existing_watcher]
        started: list = []

        def fake_start(path):
            w = MagicMock()
            w._workspace = MagicMock()
            w._workspace.path = path
            started.append(path)
            return w

        ww = WorkspacesWatcher(
            workspaces_json_path=json_path,
            workspace_manager=mgr,
            start_watcher_fn=fake_start,
            watchers_ref=watchers,
            lock=lock,
            change_event=change_event,
        )

        # Aggiungi un nuovo workspace
        ws_new = tmp_path / "ws_new"
        ws_new.mkdir()
        mgr.add(ws_new)

        ww._sync_workspaces()

        # watchers contiene existing_watcher + il nuovo
        assert len(watchers) == 2
        assert started == [ws_new]

    def test_sync_removes_deleted_workspace_watcher(self, tmp_path):
        """_sync_workspaces rimuove il watcher per un workspace rimosso."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws_to_remove"
        ws_path.mkdir()
        mgr.add(ws_path)

        json_path = tmp_path / "workspaces.json"
        lock = threading.Lock()
        change_event = threading.Event()

        # Crea un watcher fittizio già attivo
        existing_watcher = MagicMock()
        existing_watcher._workspace = MagicMock()
        existing_watcher._workspace.path = ws_path
        watchers = [existing_watcher]

        ww = WorkspacesWatcher(
            workspaces_json_path=json_path,
            workspace_manager=mgr,
            start_watcher_fn=lambda p: MagicMock(),
            watchers_ref=watchers,
            lock=lock,
            change_event=change_event,
        )

        # Rimuovi il workspace
        mgr.remove(ws_path)

        ww._sync_workspaces()

        assert len(watchers) == 0
        existing_watcher.stop.assert_called_once()

    def test_sync_handles_start_error(self, tmp_path):
        """_sync_workspaces gestisce errori nella start del watcher."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws_ok"
        ws_path.mkdir()
        mgr.add(ws_path)

        json_path = tmp_path / "workspaces.json"
        lock = threading.Lock()
        change_event = threading.Event()
        watchers: list = []

        def failing_start(path):
            raise RuntimeError("start failed")

        ww = WorkspacesWatcher(
            workspaces_json_path=json_path,
            workspace_manager=mgr,
            start_watcher_fn=failing_start,
            watchers_ref=watchers,
            lock=lock,
            change_event=change_event,
        )

        ww._sync_workspaces()

        # Il watcher non deve essere aggiunto se start fallisce
        assert len(watchers) == 0

    def test_stop_sets_stop_event(self, tmp_path):
        """stop() imposta lo stop_event."""
        mgr = _make_manager(tmp_path)
        json_path = tmp_path / "workspaces.json"
        lock = threading.Lock()
        change_event = threading.Event()

        ww = WorkspacesWatcher(
            workspaces_json_path=json_path,
            workspace_manager=mgr,
            start_watcher_fn=lambda p: MagicMock(),
            watchers_ref=[],
            lock=lock,
            change_event=change_event,
        )

        assert not ww._stop_event.is_set()
        ww.stop()
        assert ww._stop_event.is_set()

    def test_start_creates_observer_and_thread(self, tmp_path):
        """start() crea l'observer e il thread di polling."""
        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws"
        ws_path.mkdir()
        mgr.add(ws_path)

        json_path = tmp_path / "workspaces.json"
        json_path.write_text("{}")
        lock = threading.Lock()
        change_event = threading.Event()
        watchers: list = []

        ww = WorkspacesWatcher(
            workspaces_json_path=json_path,
            workspace_manager=mgr,
            start_watcher_fn=lambda p: MagicMock(),
            watchers_ref=watchers,
            lock=lock,
            change_event=change_event,
        )

        ww.start()
        assert ww._observer is not None
        assert ww._poll_thread is not None
        assert ww._poll_thread.is_alive()
        ww.stop()

    def test_sync_skips_nonexistent_dir(self, tmp_path):
        """_sync_workspaces salta workspace la cui cartella non esiste."""
        import json

        mgr = _make_manager(tmp_path)
        ws_path = tmp_path / "ws_exists"
        ws_path.mkdir()
        mgr.add(ws_path)

        # Aggiungi manualmente un workspace "fantasma" nel file JSON
        ghost_path = tmp_path / "ws_ghost"
        index_path = tmp_path / "workspaces.json"
        with open(index_path, "r") as f:
            data = json.load(f)
        data["workspaces"].append(str(ghost_path))
        with open(index_path, "w") as f:
            json.dump(data, f)

        json_path = tmp_path / "workspaces.json"
        lock = threading.Lock()
        change_event = threading.Event()
        watchers: list = []
        started: list = []

        def fake_start(path):
            started.append(path)
            return MagicMock()

        ww = WorkspacesWatcher(
            workspaces_json_path=json_path,
            workspace_manager=mgr,
            start_watcher_fn=fake_start,
            watchers_ref=watchers,
            lock=lock,
            change_event=change_event,
        )

        ww._sync_workspaces()

        # Solo ws_exists deve essere avviato, non ws_ghost
        assert len(started) == 1
        assert started[0] == ws_path
