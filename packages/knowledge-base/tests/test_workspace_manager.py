"""Test per WorkspaceManager: CRUD, sincronizzazione ricorsiva e ingest."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from knowledge_base.models import ChunkRef, FileEntry, KnowledgeBase, Workspace
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


def test_prune_stale_removes_workspaces_scomparsi(tmp_path):
    """prune_stale_workspaces rimuove i workspace non più su disco."""
    import shutil

    mgr = _make_manager(tmp_path)

    ws_existing = tmp_path / "ws_esistente"
    ws_existing.mkdir()
    ws_stale = tmp_path / "ws_stale"
    ws_stale.mkdir()
    mgr.add(ws_existing)
    mgr.add(ws_stale)

    # Il workspace stale sparisce da disco
    shutil.rmtree(ws_stale)

    removed = mgr.prune_stale_workspaces()

    assert removed == [ws_stale]
    assert mgr.list() == [ws_existing]


def test_prune_stale_pulisce_last_workspace(tmp_path):
    """Se il workspace rimosso era l'ultimo usato, last_workspace va a None."""
    import shutil

    mgr = _make_manager(tmp_path)
    ws_stale = tmp_path / "ws_stale"
    ws_stale.mkdir()
    mgr.add(ws_stale)
    mgr.set_last_workspace(ws_stale)

    shutil.rmtree(ws_stale)
    mgr.prune_stale_workspaces()

    assert mgr.get_last_workspace() is None


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


def test_sync_removes_base_from_domains_too(tmp_path):
    """Bug 022: base rimossa da disco sparisce anche da domain.base_names."""
    from knowledge_base.models import Domain, WorkspaceConfigData

    mgr = _make_manager(tmp_path)
    ws_path = tmp_path / "ws_domain"
    ws_path.mkdir()
    mgr.add(ws_path)
    ws = mgr.load(ws_path)
    ws.domains = [Domain(name="Paper", active=True, base_names=["Papers/Base1"])]

    kb_dir = ws_path / "Papers" / "Base1"
    kb_dir.mkdir(parents=True)
    mgr.sync(ws)
    assert "Papers/Base1" in ws.bases
    assert "Papers/Base1" in ws.domains[0].base_names

    import shutil

    shutil.rmtree(ws_path / "Papers")
    mgr.sync(ws)

    assert "Papers/Base1" not in ws.bases
    assert ws.domains[0].base_names == []


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

    def fake_add_file(base_name, src):
        # Simula il comportamento reale: registra il file nel modello,
        # così la sync successiva non lo re-ingesta (short-circuit mtime).
        kb = ws.bases[base_name]
        kb.files[src.name] = MagicMock(mtime=src.stat().st_mtime)
        return MagicMock()

    mock_bm.add_file.side_effect = fake_add_file

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
    # La sync iniziale di start() ingesta il file; il dispatch successivo
    # trova il file già nel modello → add_file chiamato una sola volta.
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


# --------------------------------------------------------------------------- #
# Bug 020: adozione stato per basi copiate/spostate
# --------------------------------------------------------------------------- #


def _make_fake_base_manager(ws: Workspace) -> MagicMock:
    """Base manager finto: registra file nel modello e crea chunk su disco."""
    bm = MagicMock()

    def fake_add_file(base_name, src):
        kb = ws.bases[base_name]
        file_id = hashlib.md5(src.name.encode()).hexdigest()
        chunks_dir = src.parent / ".knowledge-space" / "chunks" / file_id
        chunks_dir.mkdir(parents=True, exist_ok=True)
        (chunks_dir / f"{file_id}_chunk_0.md").write_text(
            "contenuto", encoding="utf-8"
        )
        entry = FileEntry(
            mtime=src.stat().st_mtime,
            added="2026-01-01T00:00:00",
            file_id=file_id,
            name=src.name,
            chunks=[ChunkRef(index=0)],
        )
        kb.files[src.name] = entry
        return entry

    bm.add_file.side_effect = fake_add_file
    return bm


def test_sync_and_ingest_adotta_stato_base_copiata(tmp_path):
    """Bug 020: copia di una base nel workspace → stato riusato, nessuna re-ingest."""
    import shutil

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    (ws_path / "src").mkdir()
    (ws_path / "src" / "doc.md").write_text("p1\n\np2", encoding="utf-8")

    mgr = _make_manager(tmp_path)
    mgr.add(ws_path)
    ws = mgr.load(ws_path)
    bm = _make_fake_base_manager(ws)
    mgr._base_manager_factory = lambda _w: bm  # type: ignore[assignment]

    # Prima sync: src ingerita normalmente.
    mgr.sync_and_ingest(ws)
    assert "src" in ws.bases
    assert len(ws.bases["src"].files) == 1
    bm.add_file.reset_mock()

    # Copia la base dentro il workspace.
    shutil.copytree(ws_path / "src", ws_path / "src_copy")

    mgr.sync_and_ingest(ws)

    # src_copy adottata senza re-ingestione: stessi file e file_id.
    assert "src_copy" in ws.bases
    copied = ws.bases["src_copy"]
    assert len(copied.files) == 1
    src_entry = ws.bases["src"].files["doc.md"]
    assert copied.files["doc.md"].file_id == src_entry.file_id
    assert copied.path == ws_path / "src_copy"
    # Nessuna chiamata add_file per la copia.
    add_calls = [c for c in bm.add_file.call_args_list if c[0][0] == "src_copy"]
    assert add_calls == []
    # Chroma rinominata senza drop (la sorgente esiste ancora).
    bm.rename_chroma_collection.assert_called_once_with(
        "src", "src_copy", drop_old=False
    )


def test_sync_and_ingest_adotta_stato_base_spostata(tmp_path):
    """Bug 020: move/rename di una base → stato riusato, collection droppata."""
    import shutil

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    (ws_path / "vecchia").mkdir()
    (ws_path / "vecchia" / "doc.md").write_text("p1\n\np2", encoding="utf-8")

    mgr = _make_manager(tmp_path)
    mgr.add(ws_path)
    ws = mgr.load(ws_path)
    bm = _make_fake_base_manager(ws)
    mgr._base_manager_factory = lambda _w: bm  # type: ignore[assignment]

    mgr.sync_and_ingest(ws)
    assert "vecchia" in ws.bases
    bm.add_file.reset_mock()

    # Sposta (rinomina) la base dentro il workspace.
    shutil.move(ws_path / "vecchia", ws_path / "nuova")

    mgr.sync_and_ingest(ws)

    assert "vecchia" not in ws.bases
    assert "nuova" in ws.bases
    assert len(ws.bases["nuova"].files) == 1
    # Drop della collection sorgente (non esiste più).
    bm.rename_chroma_collection.assert_called_once_with(
        "vecchia", "nuova", drop_old=True
    )
    add_calls = [c for c in bm.add_file.call_args_list if c[0][0] == "nuova"]
    assert add_calls == []


def test_sync_and_ingest_non_adotta_senza_chunk_su_disco(tmp_path):
    """Base nuova senza .knowledge-space/chunks → ingest normale."""
    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    (ws_path / "src").mkdir()
    (ws_path / "src" / "doc.md").write_text("p1\n\np2", encoding="utf-8")

    mgr = _make_manager(tmp_path)
    mgr.add(ws_path)
    ws = mgr.load(ws_path)
    bm = _make_fake_base_manager(ws)
    mgr._base_manager_factory = lambda _w: bm  # type: ignore[assignment]

    mgr.sync_and_ingest(ws)
    bm.add_file.reset_mock()

    # Nuova base VUOTA di chunk (es. copia senza .knowledge-space).
    (ws_path / "fresca").mkdir()
    (ws_path / "fresca" / "doc.md").write_text("p1\n\np2", encoding="utf-8")

    mgr.sync_and_ingest(ws)

    assert "fresca" in ws.bases
    assert len(ws.bases["fresca"].files) == 1
    bm.add_file.assert_called()  # re-ingestione normale
    bm.rename_chroma_collection.assert_not_called()


def test_sync_and_ingest_adotta_con_chunk_orfani_nella_copia(tmp_path):
    """La copia può contenere file_id orfani in più: l'adozione non deve fallire."""
    import shutil

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    (ws_path / "src").mkdir()
    (ws_path / "src" / "doc.md").write_text("p1\n\np2", encoding="utf-8")

    mgr = _make_manager(tmp_path)
    mgr.add(ws_path)
    ws = mgr.load(ws_path)
    bm = _make_fake_base_manager(ws)
    mgr._base_manager_factory = lambda _w: bm  # type: ignore[assignment]

    mgr.sync_and_ingest(ws)
    bm.add_file.reset_mock()

    shutil.copytree(ws_path / "src", ws_path / "src_copy")
    # Aggiungi un chunk orfano (file_id non nel modello): es. ingestione
    # interrotta o race CLI/watcher che lascia residui.
    orphan = ws_path / "src_copy" / ".knowledge-space" / "chunks" / ("c" * 32)
    orphan.mkdir(parents=True)
    (orphan / f"{'c' * 32}_chunk_0.md").write_text("orfano", encoding="utf-8")

    mgr.sync_and_ingest(ws)

    assert "src_copy" in ws.bases
    assert len(ws.bases["src_copy"].files) == 1
    bm.rename_chroma_collection.assert_called_once_with(
        "src", "src_copy", drop_old=False
    )
    add_calls = [c for c in bm.add_file.call_args_list if c[0][0] == "src_copy"]
    assert add_calls == []


def test_sync_and_ingest_adotta_copia_da_altro_workspace(tmp_path):
    """Bug 020 cross-workspace: base copiata con cp -r da un altro
    workspace → stato adottato (modello clonato, nessuna re-ingest)."""
    import shutil

    # ws1 con base ingerita
    ws1 = tmp_path / "ws1"
    ws1.mkdir()
    (ws1 / "src").mkdir()
    (ws1 / "src" / "doc.md").write_text("p1\n\np2", encoding="utf-8")

    mgr = _make_manager(tmp_path)
    mgr.add(ws1)
    ws1_obj = mgr.load(ws1)
    bm = _make_fake_base_manager(ws1_obj)
    mgr._base_manager_factory = lambda _w: bm  # type: ignore[assignment]
    mgr.sync_and_ingest(ws1_obj)
    bm.add_file.reset_mock()

    # ws2: base copiata con cp -r (chunks su disco inclusi)
    ws2 = tmp_path / "ws2"
    ws2.mkdir()
    shutil.copytree(ws1 / "src", ws2 / "src")
    mgr.add(ws2)
    ws2_obj = mgr.load(ws2)
    mgr.sync_and_ingest(ws2_obj)

    # Stato adottato: file nel modello, nessuna re-ingest
    assert "src" in ws2_obj.bases
    assert len(ws2_obj.bases["src"].files) == 1
    add_calls = [c for c in bm.add_file.call_args_list if c[0][0] == "src"]
    assert add_calls == []
    bm.copy_chroma_collection_from.assert_called_once_with(
        ws1, "src", "src"
    )


def test_sync_and_ingest_non_adotta_da_altro_workspace_se_già_ingerita(tmp_path):
    """Base già presente (e ingerita) in ws2 → nessuna adozione, ingest
    solo dei file nuovi."""
    import shutil

    ws1 = tmp_path / "ws1"
    ws1.mkdir()
    (ws1 / "src").mkdir()
    (ws1 / "src" / "doc.md").write_text("p1\n\np2", encoding="utf-8")

    mgr = _make_manager(tmp_path)
    mgr.add(ws1)
    ws1_obj = mgr.load(ws1)
    bm = _make_fake_base_manager(ws1_obj)
    mgr._base_manager_factory = lambda _w: bm  # type: ignore[assignment]
    mgr.sync_and_ingest(ws1_obj)
    bm.add_file.reset_mock()

    # ws2 con la stessa base già ingerita (stesso file_id via fake add_file:
    # l'hash md5 del nome è deterministico → stessi file_id su disco)
    ws2 = tmp_path / "ws2"
    ws2.mkdir()
    shutil.copytree(ws1 / "src", ws2 / "src")
    mgr.add(ws2)
    ws2_obj = mgr.load(ws2)
    mgr.sync_and_ingest(ws2_obj)

    # La base in ws2 è stata ingerita (nuova) → file presente
    assert len(ws2_obj.bases["src"].files) == 1


def test_sync_and_ingest_adotta_base_gia_registrata_con_modello_vuoto(tmp_path):
    """Caso reale: workspace add scopre la base (sync) PRIMA dell'ingest;
    sync_and_ingest successivo deve comunque adottare lo stato da un
    altro workspace (base esistente con modello vuoto)."""
    import shutil

    ws1 = tmp_path / "ws1"
    ws1.mkdir()
    (ws1 / "src").mkdir()
    (ws1 / "src" / "doc.md").write_text("p1\n\np2", encoding="utf-8")

    mgr = _make_manager(tmp_path)
    mgr.add(ws1)
    ws1_obj = mgr.load(ws1)
    bm = _make_fake_base_manager(ws1_obj)
    mgr._base_manager_factory = lambda _w: bm  # type: ignore[assignment]
    mgr.sync_and_ingest(ws1_obj)
    bm.add_file.reset_mock()

    # ws2: copia; base registrata da workspace add (solo sync, modello vuoto)
    ws2 = tmp_path / "ws2"
    ws2.mkdir()
    shutil.copytree(ws1 / "src", ws2 / "src")
    mgr.add(ws2)
    ws2_obj = mgr.load(ws2)
    mgr.sync(ws2_obj)  # registra la base nel modello (files={})

    # Il sync_and_ingest successivo deve adottare (modello vuoto → adozione)
    bm.add_file.reset_mock()
    bm.copy_chroma_collection_from.reset_mock()
    mgr.sync_and_ingest(ws2_obj)

    assert len(ws2_obj.bases["src"].files) == 1
    add_calls = [c for c in bm.add_file.call_args_list if c[0][0] == "src"]
    assert add_calls == []
    bm.copy_chroma_collection_from.assert_called_once_with(ws1, "src", "src")
