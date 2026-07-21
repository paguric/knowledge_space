"""Test per RuntimePaths (path XDG e convenzioni .knowledge-space/)."""

from pathlib import Path

from knowledge_space.runtime_paths import RuntimePaths


def test_default_respects_xdg_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    rp = RuntimePaths.default(app_name="TestApp")

    assert rp.config_home == tmp_path / "cfg" / "TestApp"
    assert rp.data_home == tmp_path / "data" / "TestApp"
    assert rp.state_home == tmp_path / "state" / "TestApp"


def test_default_falls_back_to_freedesktop(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    rp = RuntimePaths.default(app_name="TestApp")

    assert rp.config_home == Path("~/.config").expanduser() / "TestApp"
    assert rp.data_home == Path("~/.local/share").expanduser() / "TestApp"
    assert rp.state_home == Path("~/.local/state").expanduser() / "TestApp"


def test_derived_app_paths(tmp_path):
    rp = RuntimePaths(
        config_home=tmp_path / "cfg",
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
    )
    assert rp.user_settings_file == tmp_path / "cfg" / "config.json"
    assert rp.workspaces_index == tmp_path / "state" / "workspaces.json"
    assert rp.log_file == tmp_path / "state" / "log"


def test_derived_workspace_paths(tmp_path):
    rp = RuntimePaths(
        config_home=tmp_path / "cfg",
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
    )
    ws = tmp_path / "my_ws"

    assert rp.workspace_dot_dir(ws) == ws / ".knowledge-space"
    assert rp.workspace_state_file(ws) == ws / ".knowledge-space" / "state.json"
    assert rp.workspace_defaults_toml(ws) == ws / ".knowledge-space" / "defaults.toml"
    assert rp.workspace_graph_dir(ws) == ws / ".knowledge-space" / "graph"
    assert rp.base_toml(ws, "kb1") == ws / "kb1" / ".knowledge-space" / "base.toml"
    assert rp.base_chunks_dir(ws, "kb1") == ws / "kb1" / ".knowledge-space" / "chunks"


def test_ensure_dirs(tmp_path):
    rp = RuntimePaths(
        config_home=tmp_path / "cfg",
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
    )
    rp.ensure_dirs()
    assert rp.config_home.is_dir()
    assert rp.data_home.is_dir()
    assert rp.state_home.is_dir()


def test_frozen_immutable(tmp_path):
    """RuntimePaths è immutabile (frozen): niente assegnazioni post-init."""
    import pydantic

    rp = RuntimePaths(
        config_home=tmp_path / "cfg",
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
    )
    try:
        rp.config_home = tmp_path / "other"
        assert False, "doveva sollevare ValidationError"
    except pydantic.ValidationError:
        pass
