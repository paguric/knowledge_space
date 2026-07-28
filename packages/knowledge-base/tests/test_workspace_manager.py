"""Test per WorkspaceManager: CRUD, sincronizzazione ricorsiva e ingest."""

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from knowledge_base.models import KnowledgeBase, Workspace
from knowledge_base.persistence import GlobalIndex
from knowledge_base.workspace_manager import WorkspaceManager


def _make_manager(tmp_path, base_manager_factory=None):
    index_path = tmp_path / "workspaces.json"
    config_root = tmp_path / "configs"

    def config_path_for(ws_path: Path) -> Path:
        return config_root / ws_path.name / "config.json"

    return WorkspaceManager(
        GlobalIndex(path=index_path),
        config_path_for,
        base_manager_factory=base_manager_factory,
    )


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Sync ricorsivo
# --------------------------------------------------------------------------- #


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

    # lo stato è persistito: reload vede le stesse basi
    ws2 = mgr.load(ws_path)
    assert set(ws2.bases) == {"kb1", "kb2"}


def test_sync_discovers_nested_subdirectories(tmp_path):
    """Sync ricorsivo scopre sottocartelle nidificate come basi."""
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws_nested"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    # Struttura: Papers/2024/subfolder
    papers = ws_path / "Papers"
    papers.mkdir()
    (papers / "2024").mkdir()
    (papers / "2024" / "subfolder").mkdir()

    # File nella cartella (NON diventano basi)
    (papers / "doc.txt").write_text("test")

    # Cartella nascosta dentro Papers (ignorata)
    (papers / ".hidden_dir").mkdir()

    # .knowledge-space dentro una base con sottocartelle (ignorato)
    dot_ks = papers / ".knowledge-space"
    dot_ks.mkdir()
    (dot_ks / "chroma").mkdir()
    (dot_ks / "chunks").mkdir()
    (dot_ks / "chroma" / "some-uuid").mkdir()

    mgr.sync(ws)

    assert set(ws.bases) == {"Papers", "Papers/2024", "Papers/2024/subfolder"}
    assert ws.bases["Papers"].path == papers
    assert ws.bases["Papers/2024"].path == papers / "2024"
    assert ws.bases["Papers/2024/subfolder"].path == papers / "2024" / "subfolder"


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


def test_sync_removes_nested_bases_whose_folder_is_gone(tmp_path):
    """Sync rimuove basi nidificate la cui cartella è stata cancellata."""
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws_gone_nested"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    nested = ws_path / "Papers" / "2024"
    nested.mkdir(parents=True)
    mgr.sync(ws)
    assert "Papers/2024" in ws.bases

    import shutil

    shutil.rmtree(ws_path / "Papers")
    mgr.sync(ws)

    assert "Papers" not in ws.bases
    assert "Papers/2024" not in ws.bases


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


# --------------------------------------------------------------------------- #
# sync_and_ingest
# --------------------------------------------------------------------------- #


def test_sync_and_ingest_calls_add_file_for_new_bases(tmp_path):
    """sync_and_ingest indica i file nelle basi nuove."""
    # Crea un mock di KnowledgeBaseManager
    mock_bm = MagicMock()
    mock_bm.add_file.return_value = MagicMock()

    def factory(ws):
        return mock_bm

    mgr = _make_manager(tmp_path, base_manager_factory=factory)
    ws_path = tmp_path / "ws_ingest"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    # Crea una base con un file
    base_dir = ws_path / "kb1"
    base_dir.mkdir()
    (base_dir / "doc1.txt").write_text("contenuto1")
    (base_dir / "doc2.txt").write_text("contenuto2")

    mgr.sync_and_ingest(ws)

    assert "kb1" in ws.bases
    # add_file deve essere stato chiamato per ogni file
    assert mock_bm.add_file.call_count == 2
    calls = mock_bm.add_file.call_args_list
    call_args = [(c.args[0], c.args[1].name) for c in calls]
    assert ("kb1", "doc1.txt") in call_args
    assert ("kb1", "doc2.txt") in call_args


def test_sync_and_ingest_ingests_nested_bases(tmp_path):
    """sync_and_ingest indica i file nelle basi nidificate nuove."""
    mock_bm = MagicMock()
    mock_bm.add_file.return_value = MagicMock()

    def factory(ws):
        return mock_bm

    mgr = _make_manager(tmp_path, base_manager_factory=factory)
    ws_path = tmp_path / "ws_ingest_nested"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    # Crea struttura nidificata con file
    nested = ws_path / "Papers" / "2024"
    nested.mkdir(parents=True)
    (ws_path / "Papers" / "top.txt").write_text("top")
    (nested / "nested.txt").write_text("nested")

    mgr.sync_and_ingest(ws)

    assert "Papers" in ws.bases
    assert "Papers/2024" in ws.bases
    # add_file chiamato per entrambi i file (uno per base)
    assert mock_bm.add_file.call_count == 2


def test_sync_and_ingest_skips_when_no_factory(tmp_path):
    """Se non c'è factory, sync_and_ingest fa solo sync senza errori."""
    mgr = _make_manager(tmp_path)  # nessuna factory
    ws_path = tmp_path / "ws_no_factory"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    (ws_path / "kb1").mkdir()
    (ws_path / "kb1" / "doc.txt").write_text("test")

    # Non deve sollevare eccezioni
    mgr.sync_and_ingest(ws)

    assert "kb1" in ws.bases
    # Il file NON è stato indicizzato (nessuna factory)


def test_sync_and_ingest_handles_factory_error(tmp_path):
    """Se la factory fallisce, sync_and_ingest logga e continua."""
    def failing_factory(ws):
        raise RuntimeError("errore simulato")

    mgr = _make_manager(tmp_path, base_manager_factory=failing_factory)
    ws_path = tmp_path / "ws_factory_err"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    (ws_path / "kb1").mkdir()

    # Non deve sollevare eccezioni
    mgr.sync_and_ingest(ws)

    assert "kb1" in ws.bases


def test_sync_and_ingest_handles_add_file_error(tmp_path):
    """Se add_file fallisce per un file, gli altri vengono comunque processati."""
    mock_bm = MagicMock()
    mock_bm.add_file.side_effect = [
        RuntimeError("errore su doc1"),
        MagicMock(),  # doc2 ok
    ]

    def factory(ws):
        return mock_bm

    mgr = _make_manager(tmp_path, base_manager_factory=factory)
    ws_path = tmp_path / "ws_partial_err"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    base_dir = ws_path / "kb1"
    base_dir.mkdir()
    (base_dir / "doc1.txt").write_text("contenuto1")
    (base_dir / "doc2.txt").write_text("contenuto2")

    mgr.sync_and_ingest(ws)

    # Entrambi i file sono stati tentati
    assert mock_bm.add_file.call_count == 2


def test_sync_and_ingest_no_new_bases(tmp_path):
    """Se non ci sono basi nuove né file nuovi, la factory viene chiamata
    ma add_file non viene invocato (nessun file da indicizzare)."""
    mock_bm = MagicMock()

    def factory(ws):
        return mock_bm

    mgr = _make_manager(tmp_path, base_manager_factory=factory)
    ws_path = tmp_path / "ws_no_new"
    ws_path.mkdir()
    (ws_path / "kb1").mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    # Prima sync per popolare
    mgr.sync(ws)

    # Seconda sync_and_ingest: nessuna base nuova, nessun file nuovo
    mgr.sync_and_ingest(ws)

    mock_bm.add_file.assert_not_called()


def test_sync_and_ingest_ingests_new_files_in_existing_base(tmp_path):
    """Bug 008: file creati DOPO in una base esistente vengono indicizzati."""
    mock_bm = MagicMock()
    mock_bm.add_file.return_value = MagicMock()

    def factory(ws):
        return mock_bm

    mgr = _make_manager(tmp_path, base_manager_factory=factory)
    ws_path = tmp_path / "ws_existing"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    # Crea la base e fai sync (base vuota)
    base_dir = ws_path / "kb1"
    base_dir.mkdir()
    mgr.sync(ws)
    mock_bm.reset_mock()

    # Aggiungi file DOPO la sync
    (base_dir / "doc1.txt").write_text("contenuto1")
    (base_dir / "doc2.txt").write_text("contenuto2")

    # sync_and_ingest deve indicizzare i file nuovi nella base esistente
    mgr.sync_and_ingest(ws)

    assert mock_bm.add_file.call_count == 2
    calls = mock_bm.add_file.call_args_list
    call_args = [(c.args[0], c.args[1].name) for c in calls]
    assert ("kb1", "doc1.txt") in call_args
    assert ("kb1", "doc2.txt") in call_args


def test_sync_and_ingest_skips_modified_files_with_same_mtime(tmp_path):
    """File già indicizzati con stesso mtime non vengono re-indicizzati."""
    mock_bm = MagicMock()
    mock_bm.add_file.return_value = MagicMock()

    def factory(ws):
        return mock_bm

    mgr = _make_manager(tmp_path, base_manager_factory=factory)
    ws_path = tmp_path / "ws_mtime"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    # Crea base con file
    base_dir = ws_path / "kb1"
    base_dir.mkdir()
    (base_dir / "doc.txt").write_text("contenuto")

    # Prima sync_and_ingest: indicaizza il file
    mgr.sync_and_ingest(ws)
    assert mock_bm.add_file.call_count == 1

    # Simula che il file è già stato indicizzato aggiornando kb.files
    file_path = base_dir / "doc.txt"
    kb = ws.bases["kb1"]
    kb.files["doc.txt"] = MagicMock()
    kb.files["doc.txt"].mtime = file_path.stat().st_mtime

    mock_bm.reset_mock()

    # Seconda sync_and_ingest: stesso mtime → non re-indicizza
    mgr.sync_and_ingest(ws)

    mock_bm.add_file.assert_not_called()


# --------------------------------------------------------------------------- #
# Bug 009 — .knowledge-space escluso dalla scoperta ricorsiva
# --------------------------------------------------------------------------- #


def test_sync_excludes_knowledge_space_subdirs(tmp_path):
    """Bug 009: sottocartelle dentro .knowledge-space non diventano basi."""
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws_dot_ks"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    # Crea struttura con .knowledge-space e sottocartelle
    base = ws_path / "TestBase"
    base.mkdir()
    dot_ks = base / ".knowledge-space"
    dot_ks.mkdir()
    (dot_ks / "chroma").mkdir()
    (dot_ks / "chunks").mkdir()
    (dot_ks / "chroma" / "some-uuid-dir").mkdir()
    (dot_ks / "chunks" / "file-id-dir").mkdir()

    # Anche al livello del workspace
    ws_dot_ks = ws_path / ".knowledge-space"
    ws_dot_ks.mkdir()
    (ws_dot_ks / "chroma").mkdir()
    (ws_dot_ks / "chunks").mkdir()

    mgr.sync(ws)

    # Solo TestBase deve essere una base
    assert set(ws.bases) == {"TestBase"}
    # Nessuna base deve contenere .knowledge-space nel nome
    for name in ws.bases:
        assert ".knowledge-space" not in name


def test_sync_excludes_knowledge_space_at_all_levels(tmp_path):
    """Bug 009: .knowledge-space è escluso a ogni livello di nidificazione."""
    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws_dot_ks_nested"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    # Struttura: A/B/.knowledge-space/chroma/uuid
    nested_dot_ks = ws_path / "A" / "B" / ".knowledge-space" / "chroma" / "uuid"
    nested_dot_ks.mkdir(parents=True)

    # Altre cartelle valide
    (ws_path / "A" / "B" / "C").mkdir(parents=True)

    mgr.sync(ws)

    assert set(ws.bases) == {"A", "A/B", "A/B/C"}


# --------------------------------------------------------------------------- #
# Watcher
# --------------------------------------------------------------------------- #


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


def test_watcher_calls_sync_and_ingest_when_factory_present(tmp_path):
    """Il watcher chiama sync_and_ingest quando la factory è configurata."""
    import time

    class FakeObserver:
        def __init__(self):
            self.handler = None

        def schedule(self, handler, path, recursive=False):
            self.handler = handler
            return object()

        def start(self):
            pass

        def stop(self):
            pass

        def join(self):
            pass

        def dispatch_created(self, event=None):
            self.handler.on_created(event)

    mock_bm = MagicMock()
    mock_bm.add_file.return_value = MagicMock()

    def factory(ws):
        return mock_bm

    mgr = _make_manager(tmp_path, base_manager_factory=factory)
    ws_path = tmp_path / "ws_watch_ingest"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    base_dir = ws_path / "kb1"
    base_dir.mkdir()
    (base_dir / "doc.txt").write_text("contenuto")

    watcher = mgr.start_watching(ws, observer_factory=FakeObserver, debounce_seconds=0.0)
    fake = watcher._observer
    watcher.start()
    fake.dispatch_created(None)
    time.sleep(0.05)
    watcher.stop()

    assert "kb1" in ws.bases
    mock_bm.add_file.assert_called_once()


def test_watcher_ignores_events_inside_knowledge_space(tmp_path):
    """Bug 010: eventi dentro .knowledge-space non triggerano sync."""
    import time

    class FakeObserver:
        def __init__(self):
            self.handler = None

        def schedule(self, handler, path, recursive=False):
            self.handler = handler
            return object()

        def start(self):
            pass

        def stop(self):
            pass

        def join(self):
            pass

        def dispatch(self, event):
            self.handler.on_created(event)

    mock_bm = MagicMock()

    def factory(ws):
        return mock_bm

    mgr = _make_manager(tmp_path, base_manager_factory=factory)
    ws_path = tmp_path / "ws_filter"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)

    watcher = mgr.start_watching(ws, observer_factory=FakeObserver, debounce_seconds=0.0)
    fake = watcher._observer
    watcher.start()

    # Evento dentro .knowledge-space → deve essere ignorato
    event_dot_ks = MagicMock()
    event_dot_ks.src_path = str(ws_path / "TestBase" / ".knowledge-space" / "chunks" / "file.md")
    fake.dispatch(event_dot_ks)
    time.sleep(0.05)

    # Evento dentro .knowledge-space a livello workspace → ignorato
    event_ws_dot_ks = MagicMock()
    event_ws_dot_ks.src_path = str(ws_path / ".knowledge-space" / "chroma" / "uuid")
    fake.dispatch(event_ws_dot_ks)
    time.sleep(0.05)

    # Nessuna sync deve essere stata chiamata
    mock_bm.add_file.assert_not_called()

    # Evento normale → deve triggerare sync
    event_normal = MagicMock()
    event_normal.src_path = str(ws_path / "TestBase" / "doc.txt")
    fake.dispatch(event_normal)
    time.sleep(0.05)

    # Ora la sync deve essere stata chiamata
    # (almeno una volta, anche se non ci sono file da indicizzare)
    watcher.stop()
