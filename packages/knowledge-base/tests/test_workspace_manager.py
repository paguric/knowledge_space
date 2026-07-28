"""Test per WorkspaceManager: CRUD e sincronizzazione col filesystem."""

from pathlib import Path

from knowledge_base.models import KnowledgeBase, Workspace
from knowledge_base.persistence import GlobalIndex
from knowledge_base.workspace_manager import WorkspaceManager


def _make_manager(tmp_path):
    index_path = tmp_path / "workspaces.json"
    config_root = tmp_path / "configs"

    def config_path_for(ws_path: Path) -> Path:
        return config_root / ws_path.name / "config.json"

    return WorkspaceManager(GlobalIndex(path=index_path), config_path_for)


def test_add_creates_config_and_registers(tmp_path):
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "my_ws"
    ws_path.mkdir()

    assert mgr.add(ws_path) is True
    # idempotente
    assert mgr.add(ws_path) is False

    # registrato nell'indice globale
    assert mgr.list() == [ws_path]

    # config.json creato con i default
    ws = mgr.load(ws_path)
    assert isinstance(ws, Workspace)
    assert ws.path == ws_path
    assert ws.bases == {}
    assert ws.domains == []


def test_remove_deregisters(tmp_path):
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws1"
    ws_path.mkdir()
    mgr.add(ws_path)

    assert mgr.remove(ws_path) is True
    assert mgr.remove(ws_path) is False
    assert mgr.list() == []


def test_set_and_get_last_workspace(tmp_path):
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws2"
    mgr.set_last_workspace(ws_path)
    assert mgr.get_last_workspace() == ws_path


def test_load_without_config_returns_empty(tmp_path):
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "unregistered"
    ws_path.mkdir()
    ws = mgr.load(ws_path)
    assert ws.bases == {}


def test_sync_discovers_subdirectories_as_bases(tmp_path):
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws_sync"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    # crea due cartelle-figlie
    (ws_path / "kb1").mkdir()
    (ws_path / "kb2").mkdir()
    # le cartelle nascoste NON devono diventare basi
    (ws_path / ".hidden").mkdir()

    mgr.sync(ws)

    assert set(ws.bases) == {"kb1", "kb2"}
    assert isinstance(ws.bases["kb1"], KnowledgeBase)
    assert ws.bases["kb1"].path == ws_path / "kb1"

    # lo stato Ã¨ persistito: reload vede le stesse basi
    ws2 = mgr.load(ws_path)
    assert set(ws2.bases) == {"kb1", "kb2"}


def test_sync_removes_bases_whose_folder_is_gone(tmp_path):
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws_gone"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    kb_dir = ws_path / "kb_old"
    kb_dir.mkdir()
    mgr.sync(ws)
    assert "kb_old" in ws.bases

    # elimina la cartella e risincronizza
    import shutil

    shutil.rmtree(kb_dir)
    mgr.sync(ws)

    assert "kb_old" not in ws.bases


def test_sync_is_idempotent(tmp_path):
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws_idem"
    ws_path.mkdir()
    (ws_path / "kb1").mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    mgr.sync(ws)
    first = dict(ws.bases)
    mgr.sync(ws)
    assert ws.bases == first


def test_start_watching_with_fake_observer(tmp_path):
    """Verifica che il watcher, usando un observer fittizio, chiami sync
    quando dispatcha un evento, senza avviare thread reali."""
    import time

    class FakeObserver:
        def __init__(self):
            self.handler = None
            self.stopped = False

        def schedule(self, handler, path, recursive=False):
            self.handler = handler
            return object()

        def start(self):
            pass

        def stop(self):
            self.stopped = True

        def join(self):
            pass

        def dispatch_created(self, event=None):
            self.handler.on_created(event)

    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws_watch"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)
    (ws_path / "kb_new").mkdir()

    watcher = mgr.start_watching(ws, observer_factory=FakeObserver, debounce_seconds=0.0)
    fake = watcher._observer  # type: ignore[attr-defined]
    watcher.start()
    # simula un evento FS
    fake.dispatch_created(None)
    # attendi che il debounce thread completi
    time.sleep(0.05)
    watcher.stop()

    assert "kb_new" in ws.bases
    assert fake.stopped is True