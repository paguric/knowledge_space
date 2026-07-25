"""Test per la CLI Typer (Step 13).

Verifica:
- Help message
- Workspace add/list/remove/info
- Domain new/list/remove/add-base/remove-base/auto-generate
- Base add/list/remove/info
- File add/list/remove
- Chunk list/show
- Tree output
- Search (mock)
- Status output
- Config show/init
- Models list/info
- --json flag
- --workspace override
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

import pytest
from typer.testing import CliRunner

from knowledge_space.cli import app

runner = CliRunner()


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    """Crea un workspace temporaneo con .knowledge-space/."""
    ws = tmp_path / "test_workspace"
    ws.mkdir()
    (ws / ".knowledge-space").mkdir()
    return ws


@pytest.fixture
def base_dir(workspace_dir: Path) -> Path:
    """Crea una base temporanea nel workspace."""
    base = workspace_dir / "my_base"
    base.mkdir()
    (base / ".knowledge-space").mkdir()
    return base


@pytest.fixture
def sample_file(workspace_dir: Path) -> Path:
    """Crea un file di esempio nel workspace."""
    sample = workspace_dir / "sample.md"
    sample.write_text("# Test\n\nQuesto è un documento di test.\n\nSecondo paragrafo.")
    return sample


# --------------------------------------------------------------------------- #
# Test help
# --------------------------------------------------------------------------- #


class TestHelp:
    """Test dei messaggi di help."""

    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Knowledge Space" in result.output
        assert "workspace" in result.output
        assert "domain" in result.output
        assert "base" in result.output
        assert "file" in result.output
        assert "search" in result.output

    def test_workspace_help(self):
        result = runner.invoke(app, ["workspace", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "remove" in result.output

    def test_domain_help(self):
        result = runner.invoke(app, ["domain", "--help"])
        assert result.exit_code == 0
        assert "new" in result.output
        assert "auto-generate" in result.output

    def test_base_help(self):
        result = runner.invoke(app, ["base", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "info" in result.output

    def test_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


# --------------------------------------------------------------------------- #
# Test workspace
# --------------------------------------------------------------------------- #


class TestWorkspace:
    """Test comandi workspace."""

    def test_workspace_add_and_list(self, workspace_dir: Path):
        result = runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        assert result.exit_code == 0
        assert "registrato" in result.output.lower() or "Workspace" in result.output

        result = runner.invoke(app, ["workspace", "list"])
        assert result.exit_code == 0

    def test_workspace_add_nonexistent(self, tmp_path: Path):
        result = runner.invoke(app, ["workspace", "add", str(tmp_path / "nonexistent")])
        assert result.exit_code == 1
        assert "non trovato" in result.output.lower() or "errore" in result.output.lower()

    def test_workspace_list_json(self, workspace_dir: Path):
        runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        result = runner.invoke(app, ["workspace", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_workspace_remove(self, workspace_dir: Path):
        runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        result = runner.invoke(app, ["workspace", "remove", str(workspace_dir)])
        assert result.exit_code == 0
        assert "rimosso" in result.output.lower()

    def test_workspace_remove_nonexistent(self, tmp_path: Path):
        result = runner.invoke(
            app, ["workspace", "remove", str(tmp_path / "nonexistent")]
        )
        assert result.exit_code == 1

    def test_workspace_info(self, workspace_dir: Path):
        runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        result = runner.invoke(
            app, ["workspace", "info", str(workspace_dir)]
        )
        assert result.exit_code == 0
        assert "Workspace" in result.output

    def test_workspace_info_json(self, workspace_dir: Path):
        runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        result = runner.invoke(
            app, ["workspace", "info", str(workspace_dir), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "path" in data
        assert "bases" in data


# --------------------------------------------------------------------------- #
# Test domain
# --------------------------------------------------------------------------- #


class TestDomain:
    """Test comandi domain."""

    def test_domain_new(self, workspace_dir: Path):
        result = runner.invoke(
            app,
            ["domain", "new", "diritto", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "diritto" in result.output

    def test_domain_list(self, workspace_dir: Path):
        runner.invoke(
            app, ["domain", "new", "test", "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app, ["domain", "list", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0

    def test_domain_list_json(self, workspace_dir: Path):
        runner.invoke(
            app, ["domain", "new", "test", "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app, ["domain", "list", "--workspace", str(workspace_dir), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_domain_remove(self, workspace_dir: Path):
        runner.invoke(
            app, ["domain", "new", "tmp", "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app, ["domain", "remove", "tmp", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0
        assert "rimosso" in result.output.lower()

    def test_domain_remove_nonexistent(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["domain", "remove", "nope", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 1

    def test_domain_add_base(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["domain", "new", "test", "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            [
                "domain", "add-base", "test", "my_base",
                "--workspace", str(workspace_dir),
            ],
        )
        assert result.exit_code == 0
        assert "my_base" in result.output

    def test_domain_remove_base(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["domain", "new", "test", "--workspace", str(workspace_dir)]
        )
        runner.invoke(
            app,
            [
                "domain", "add-base", "test", "my_base",
                "--workspace", str(workspace_dir),
            ],
        )
        result = runner.invoke(
            app,
            [
                "domain", "remove-base", "test", "my_base",
                "--workspace", str(workspace_dir),
            ],
        )
        assert result.exit_code == 0

    def test_domain_auto_generate(self, workspace_dir: Path):
        # Crea struttura cartelle
        (workspace_dir / "diritto" / "civile").mkdir(parents=True)
        (workspace_dir / "diritto" / "penale").mkdir(parents=True)
        result = runner.invoke(
            app, ["domain", "auto-generate", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0


# --------------------------------------------------------------------------- #
# Test base
# --------------------------------------------------------------------------- #


class TestBase:
    """Test comandi base."""

    def test_base_add(self, workspace_dir: Path, base_dir: Path):
        result = runner.invoke(
            app,
            ["base", "add", str(base_dir), "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "my_base" in result.output

    def test_base_list(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app, ["base", "list", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0

    def test_base_list_json(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app, ["base", "list", "--workspace", str(workspace_dir), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_base_remove(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            ["base", "remove", "my_base", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "rimossa" in result.output.lower() or "rimosso" in result.output.lower()

    def test_base_remove_nonexistent(self, workspace_dir: Path):
        result = runner.invoke(
            app,
            ["base", "remove", "nope", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 1

    def test_base_info(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            ["base", "info", "my_base", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "my_base" in result.output

    def test_base_info_json(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            ["base", "info", "my_base", "--workspace", str(workspace_dir), "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "my_base"


# --------------------------------------------------------------------------- #
# Test file
# --------------------------------------------------------------------------- #


class TestFile:
    """Test comandi file."""

    def test_file_list(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app, ["file", "list", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0

    def test_file_list_json(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app, ["file", "list", "--workspace", str(workspace_dir), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_file_list_by_base(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            [
                "file", "list",
                "--base", "my_base",
                "--workspace", str(workspace_dir),
            ],
        )
        assert result.exit_code == 0

    def test_file_remove_nonexistent(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            [
                "file", "remove", "my_base", "nope.md",
                "--workspace", str(workspace_dir),
            ],
        )
        assert result.exit_code == 1


# --------------------------------------------------------------------------- #
# Test tree
# --------------------------------------------------------------------------- #


class TestTree:
    """Test comando tree."""

    def test_tree_empty(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["tree", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0

    def test_tree_json(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["tree", "--workspace", str(workspace_dir), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "workspace" in data
        assert "bases" in data

    def test_tree_with_base(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app, ["tree", "--workspace", str(workspace_dir), "--base", "my_base"]
        )
        assert result.exit_code == 0


# --------------------------------------------------------------------------- #
# Test search
# --------------------------------------------------------------------------- #


class TestSearch:
    """Test comando search."""

    def test_search_no_bases(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["search", "test query", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 1
        assert "nessuna base" in result.output.lower() or "errore" in result.output.lower()

    def test_search_base_not_found(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            [
                "search", "test",
                "--base", "nonexistent",
                "--workspace", str(workspace_dir),
            ],
        )
        assert result.exit_code == 1


# --------------------------------------------------------------------------- #
# Test status
# --------------------------------------------------------------------------- #


class TestStatus:
    """Test comando status."""

    def test_status(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["status", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0
        assert "Workspace" in result.output

    def test_status_json(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["status", "--workspace", str(workspace_dir), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "workspace" in data
        assert "bases" in data


# --------------------------------------------------------------------------- #
# Test config
# --------------------------------------------------------------------------- #


class TestConfig:
    """Test comandi config."""

    def test_config_show(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["config", "show", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0

    def test_config_show_base(self, workspace_dir: Path, base_dir: Path):
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            ["config", "show", "my_base", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0

    def test_config_show_json(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["config", "show", "--workspace", str(workspace_dir), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "ingestion" in data

    def test_config_init(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["config", "init", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0
        assert "generato" in result.output.lower() or "defaults.toml" in result.output

        # Verifica che il file sia stato creato
        defaults_path = workspace_dir / ".knowledge-space" / "defaults.toml"
        assert defaults_path.exists()


# --------------------------------------------------------------------------- #
# Test models
# --------------------------------------------------------------------------- #


class TestModels:
    """Test comandi models."""

    def test_models_list(self):
        result = runner.invoke(app, ["models", "list"])
        assert result.exit_code == 0
        assert "Modelli" in result.output

    def test_models_list_json(self):
        result = runner.invoke(app, ["models", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_models_info(self):
        result = runner.invoke(
            app, ["models", "info", "sentence-transformers/all-mpnet-base-v2"]
        )
        assert result.exit_code == 0
        assert "all-mpnet-base-v2" in result.output

    def test_models_info_json(self):
        result = runner.invoke(
            app, ["models", "info", "sentence-transformers/all-mpnet-base-v2", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "sentence-transformers/all-mpnet-base-v2"

    def test_models_info_not_found(self):
        result = runner.invoke(app, ["models", "info", "nonexistent-model"])
        assert result.exit_code == 1


# --------------------------------------------------------------------------- #
# Test --workspace override
# --------------------------------------------------------------------------- #


class TestWorkspaceOverride:
    """Test del flag --workspace."""

    def test_workspace_flag_on_workspace_command(self, workspace_dir: Path):
        # --workspace non applicabile a workspace add (usa path diretto)
        result = runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        assert result.exit_code == 0

    def test_workspace_flag_on_domain_command(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["domain", "list", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0

    def test_workspace_flag_on_status(self, workspace_dir: Path):
        result = runner.invoke(
            app, ["status", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0
