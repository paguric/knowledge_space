"""Test di persistenza per GlobalIndex e WorkspaceConfig."""

from pathlib import Path

from knowledge_base.models import (
    Domain,
    GlobalIndexData,
    KnowledgeBase,
    WorkspaceConfigData,
)
from knowledge_base.persistence import GlobalIndex, WorkspaceConfig


# --------------------------------------------------------------------------- #
# GlobalIndex
# --------------------------------------------------------------------------- #


def test_global_index_default_when_file_missing(tmp_path):
    index_path = tmp_path / "workspaces.json"
    gi = GlobalIndex(path=index_path)
    data = gi.load()
    assert data.workspaces == []
    assert data.last_workspace is None
    assert not index_path.exists()


def test_global_index_save_and_load_roundtrip(tmp_path):
    index_path = tmp_path / "workspaces.json"
    gi = GlobalIndex(path=index_path)
    ws1, ws2 = tmp_path / "ws1", tmp_path / "ws2"

    data = GlobalIndexData(last_workspace=ws1, workspaces=[ws1, ws2])
    gi.save(data)

    assert index_path.exists()
    restored = gi.load()
    assert restored.version == 1
    assert restored.last_workspace == ws1
    assert restored.workspaces == [ws1, ws2]


def test_global_index_add_workspace(tmp_path):
    gi = GlobalIndex(path=tmp_path / "workspaces.json")
    ws_a, ws_b = tmp_path / "ws_a", tmp_path / "ws_b"
    assert gi.add_workspace(ws_a) is True
    assert gi.add_workspace(ws_a) is False  # già presente
    assert gi.add_workspace(ws_b) is True
    assert gi.list_workspaces() == [ws_a, ws_b]


def test_global_index_remove_workspace(tmp_path):
    gi = GlobalIndex(path=tmp_path / "workspaces.json")
    ws_a, ws_b = tmp_path / "ws_a", tmp_path / "ws_b"
    gi.add_workspace(ws_a)
    gi.add_workspace(ws_b)
    gi.set_last_workspace(ws_a)

    assert gi.remove_workspace(ws_a) is True
    assert gi.remove_workspace(ws_a) is False
    assert gi.list_workspaces() == [ws_b]
    # rimuovendo il last_workspace, il campo viene pulito
    assert gi.get_last_workspace() is None


def test_global_index_set_last_workspace(tmp_path):
    gi = GlobalIndex(path=tmp_path / "workspaces.json")
    ws_c = tmp_path / "ws_c"
    gi.set_last_workspace(ws_c)
    assert gi.get_last_workspace() == ws_c


# --------------------------------------------------------------------------- #
# WorkspaceConfig
# --------------------------------------------------------------------------- #


def test_workspace_config_default_when_file_missing(tmp_path):
    config_path = tmp_path / ".ks" / "config.json"
    wc = WorkspaceConfig(config_path=config_path, workspace_path=tmp_path)
    assert not wc.exists()
    data = wc.load()
    assert data.version == 1
    assert data.domains == []
    assert data.bases == {}


def test_workspace_config_save_and_load_roundtrip(tmp_path):
    config_path = tmp_path / ".ks" / "config.json"
    wc = WorkspaceConfig(config_path=config_path, workspace_path=tmp_path)

    data = WorkspaceConfigData(
        domains=[Domain(name="domain1", base_names=["kb1"])],
        bases={
            "kb1": KnowledgeBase(
                path=tmp_path / "kb1",
                files={
                    "doc.pdf": {
                        "mtime": 1.0,
                        "added": "2026-07-13T20:04:44",
                        "active": True,
                        "chunks": [{"index": 0, "active": True}],
                    }
                },
            )
        },
    )
    wc.save(data)

    assert wc.exists()
    assert wc.config_path == config_path

    restored = wc.load()
    assert restored.version == 1
    assert restored.domains[0].name == "domain1"
    assert restored.domains[0].base_names == ["kb1"]
    assert "kb1" in restored.bases
    assert restored.bases["kb1"].files["doc.pdf"].chunks[0].index == 0


def test_workspace_config_init_default(tmp_path):
    config_path = tmp_path / ".ks" / "config.json"
    wc = WorkspaceConfig(config_path=config_path, workspace_path=tmp_path)
    wc.init_default()
    assert wc.exists()
    assert wc.load().version == 1
    # una seconda chiamata nonostante esista non deve lanciare
    wc.init_default()
    assert wc.exists()


def test_workspace_config_to_workspace(tmp_path):
    config_path = tmp_path / ".ks" / "config.json"
    wc = WorkspaceConfig(config_path=config_path, workspace_path=tmp_path)
    wc.save(
        WorkspaceConfigData(
            domains=[Domain(name="domain1")],
            bases={"kb1": KnowledgeBase(path=tmp_path / "kb1")},
        )
    )
    ws = wc.to_workspace()
    assert ws.path == tmp_path
    assert ws.domains[0].name == "domain1"
    assert "kb1" in ws.bases