"""Test per DomainManager: creazione, auto-generazione, flag active, add/remove base."""

from pathlib import Path

from knowledge_base.models import Domain, KnowledgeBase, Workspace
from knowledge_base.persistence import GlobalIndex
from knowledge_base.domain_manager import DomainManager
from knowledge_base.workspace_manager import WorkspaceManager


def _make_managers(tmp_path):
    index_path = tmp_path / "workspaces.json"
    config_root = tmp_path / "configs"

    def config_path_for(ws_path: Path) -> Path:
        return config_root / ws_path.name / "config.json"

    wsm = WorkspaceManager(GlobalIndex(path=index_path), config_path_for)
    dm = DomainManager(config_path_for)
    return wsm, dm


def test_create_domain(tmp_path):
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws1"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)

    dm.create(ws, "Corso algoritmi 1", base_names=["Appunti", "Algoritmi 1"])
    assert len(ws.domains) == 1
    assert ws.domains[0].name == "Corso algoritmi 1"
    assert ws.domains[0].base_names == ["Appunti", "Algoritmi 1"]
    assert ws.domains[0].active is True

    # persistito
    ws2 = wsm.load(ws_path)
    assert ws2.domains[0].name == "Corso algoritmi 1"


def test_create_duplicate_raises(tmp_path):
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws1"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)

    dm.create(ws, "domain1")
    import pytest

    with pytest.raises(ValueError, match="esiste gi"):
        dm.create(ws, "domain1")


def test_delete_domain(tmp_path):
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws1"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)
    dm.create(ws, "domain1")

    assert dm.delete(ws, "domain1") is True
    assert dm.delete(ws, "domain1") is False
    assert ws.domains == []


def test_activate_deactivate(tmp_path):
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws1"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)
    dm.create(ws, "domain1")

    assert dm.deactivate(ws, "domain1") is True
    assert ws.domains[0].active is False

    assert dm.activate(ws, "domain1") is True
    assert ws.domains[0].active is True

    # dominio inesistente
    assert dm.deactivate(ws, "nostalgia") is False
    assert dm.activate(ws, "nostalgia") is False


def test_add_and_remove_base(tmp_path):
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws1"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)
    dm.create(ws, "domain1")

    assert dm.add_base(ws, "domain1", "kb1") is True
    # idempotente
    assert dm.add_base(ws, "domain1", "kb1") is False
    assert "kb1" in ws.domains[0].base_names

    assert dm.remove_base(ws, "domain1", "kb1") is True
    assert dm.remove_base(ws, "domain1", "kb1") is False
    assert "kb1" not in ws.domains[0].base_names

    # dominio inesistente
    assert dm.add_base(ws, "nostalgia", "kb1") is False
    assert dm.remove_base(ws, "nostalgia", "kb1") is False


def test_auto_generate_simple_domain(tmp_path):
    """Cartella con sotto-cartelle foglia → dominio con basi."""
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws_auto"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)

    # ws_auto/Corso algoritmi 1/Appunti  (foglia)
    # ws_auto/Corso algoritmi 1/Algoritmi 1  (foglia)
    (ws_path / "Corso algoritmi 1").mkdir()
    (ws_path / "Corso algoritmi 1" / "Appunti").mkdir()
    (ws_path / "Corso algoritmi 1" / "Algoritmi 1").mkdir()

    dm.auto_generate(ws)

    # "Corso algoritmi 1" era una cartella con sotto-cartelle → dominio
    names = {d.name for d in ws.domains}
    assert "Corso algoritmi 1" in names
    dom = next(d for d in ws.domains if d.name == "Corso algoritmi 1")
    assert "Corso algoritmi 1/Appunti" in dom.base_names
    assert "Corso algoritmi 1/Algoritmi 1" in dom.base_names

    # le basi sono registrate anche nel workspace.bases
    assert "Corso algoritmi 1/Appunti" in ws.bases
    assert "Corso algoritmi 1/Algoritmi 1" in ws.bases


def test_auto_generate_standalone_leaf(tmp_path):
    """Cartella foglia al primo livello → base standalone, nessun dominio."""
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws_standalone"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)

    (ws_path / "kb_solo").mkdir()

    dm.auto_generate(ws)

    # nessun dominio: la cartella non ha sotto-cartelle
    assert ws.domains == []
    assert "kb_solo" in ws.bases


def test_auto_generate_ignores_hidden(tmp_path):
    """Le cartelle nascoste (.something) vengono ignorate."""
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws_hidden"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)

    (ws_path / ".git").mkdir()
    (ws_path / ".git" / "objects").mkdir()
    (ws_path / "kb1").mkdir()

    dm.auto_generate(ws)

    names = {d.name for d in ws.domains}
    assert "git" not in names
    assert "objects" not in names
    assert ".git" not in ws.bases
    assert "kb1" in ws.bases


def test_auto_generate_merge_existing_domain(tmp_path):
    """Auto-generazione su dominio esistente: le nuove basi vengono unite."""
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws_merge"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)

    (ws_path / "Corso algoritmi 1").mkdir()
    (ws_path / "Corso algoritmi 1" / "Appunti").mkdir()

    dm.auto_generate(ws)
    assert "Corso algoritmi 1/Appunti" in ws.bases
    dom = next(d for d in ws.domains if d.name == "Corso algoritmi 1")
    assert "Corso algoritmi 1/Appunti" in dom.base_names

    # aggiungi una nuova base sotto-cartella e ri-esegui
    (ws_path / "Corso algoritmi 1" / "Algoritmi 1").mkdir()
    dm.auto_generate(ws)

    dom = next(d for d in ws.domains if d.name == "Corso algoritmi 1")
    assert "Corso algoritmi 1/Algoritmi 1" in dom.base_names
    # La vecchia base è ancora lì
    assert "Corso algoritmi 1/Appunti" in dom.base_names
    # numero di domini "Corso algoritmi 1" ancora uno
    assert sum(1 for d in ws.domains if d.name == "Corso algoritmi 1") == 1


def test_auto_generate_nested_subfolder_leaf_inherits_domain(tmp_path):
    """Una sotto-cartella foglia più profonda eredita il dominio del padre."""
    wsm, dm = _make_managers(tmp_path)
    ws_path = tmp_path / "ws_nested"
    ws_path.mkdir()
    wsm.add(ws_path)
    ws = wsm.load(ws_path)

    # ws_nested/Corso algoritmi 1/Appunti/2024  (foglia profonda)
    (ws_path / "Corso algoritmi 1").mkdir(parents=True, exist_ok=True)
    (ws_path / "Corso algoritmi 1" / "Appunti").mkdir(parents=True, exist_ok=True)
    (ws_path / "Corso algoritmi 1" / "Appunti" / "2024").mkdir()

    dm.auto_generate(ws)

    dom = next(d for d in ws.domains if d.name == "Corso algoritmi 1")
    assert "Corso algoritmi 1/Appunti/2024" in dom.base_names
    assert "Corso algoritmi 1/Appunti/2024" in ws.bases