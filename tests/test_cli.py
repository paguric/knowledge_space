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
from knowledge_space.cli.common import normalize_base_name

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

    def test_workspace_add_does_not_pollute_real_xdg(self, workspace_dir: Path):
        """Verifica che la fixture di isolamento XDG impedisca la scrittura
        nell'indice globale reale (regressione per inquinamento sotto /tmp).

        Con isolamento XDG attivo, ogni test parte da indice vuoto:
        l'unico workspace visibile è quello registrato qui dentro."""
        runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        result = runner.invoke(app, ["workspace", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        resolved = str(Path(workspace_dir).resolve())
        # L'indice contiene esattamente il workspace appena registrato
        assert len(data) == 1
        assert data[0] == resolved
        # Non deve apparire l'indice globale reale (nessun path utente)
        assert all("My Workspace" not in p for p in data)

    def test_workspace_add_creates_defaults_toml(self, workspace_dir: Path):
        """workspace add crea defaults.toml nella dotfolder del workspace."""
        result = runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        assert result.exit_code == 0
        defaults_path = workspace_dir / ".knowledge-space" / "defaults.toml"
        assert defaults_path.exists()
        # Il template contiene sezioni TOML commentate/attive
        content = defaults_path.read_text(encoding="utf-8")
        assert "[ingestion]" in content
        assert "[embedding]" in content

    def test_workspace_add_does_not_overwrite_modified_defaults_toml(
        self, workspace_dir: Path
    ):
        """Secondo add non sovrascrive un defaults.toml modificato dall'utente."""
        # Primo add crea il template
        runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        defaults_path = workspace_dir / ".knowledge-space" / "defaults.toml"
        assert defaults_path.exists()
        # L'utente modifica il file
        custom = "# custom\n[chunking]\nchunk_size = 42\n"
        defaults_path.write_text(custom, encoding="utf-8")
        # Secondo add: non sovrascrive
        runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        assert defaults_path.read_text(encoding="utf-8") == custom

    def test_workspace_add_creates_base_toml_for_discovered_bases(
        self, workspace_dir: Path, base_dir: Path
    ):
        """workspace add crea base.toml per le basi auto-scoperte dalla sync."""
        result = runner.invoke(app, ["workspace", "add", str(workspace_dir)])
        assert result.exit_code == 0
        base_toml = base_dir / ".knowledge-space" / "base.toml"
        assert base_toml.exists()
        content = base_toml.read_text(encoding="utf-8")
        # Il template base ha solo commenti, nessun valore attivo
        assert "# [chunking]" in content


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
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
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
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
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

    def test_base_add_creates_toml_files(
        self, workspace_dir: Path, base_dir: Path
    ):
        """base add crea base.toml e (se mancante) defaults.toml."""
        result = runner.invoke(
            app,
            ["base", "add", str(base_dir), "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        # base.toml creato per la base
        base_toml = base_dir / ".knowledge-space" / "base.toml"
        assert base_toml.exists()
        # defaults.toml creato nel workspace (se non esisteva)
        defaults_toml = workspace_dir / ".knowledge-space" / "defaults.toml"
        assert defaults_toml.exists()

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

    def test_base_remove_trailing_slash(self, workspace_dir: Path, base_dir: Path):
        """Tab-completion aggiunge spesso '/' al nome: non deve far fallire remove."""
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            ["base", "remove", "my_base/", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "rimossa" in result.output.lower() or "rimosso" in result.output.lower()

    def test_normalize_base_name_strips_slash(self):
        assert normalize_base_name("Progetto di Tesi/") == "Progetto di Tesi"
        assert normalize_base_name("Progetto di Tesi") == "Progetto di Tesi"
        assert normalize_base_name("./my_base/") == "my_base"

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

    def test_base_remove_with_files_shows_warning(
        self, workspace_dir: Path, base_dir: Path
    ):
        """Rimozione di una base con file mostra warning e richiede conferma."""
        from knowledge_base.models import (
            ChunkRef,
            FileEntry,
            KnowledgeBase,
            WorkspaceConfigData,
        )
        from knowledge_base.persistence import WorkspaceConfig

        # Scrivi state.json con un file e chunk
        config_path = workspace_dir / ".knowledge-space" / "state.json"
        file_entry = FileEntry(
            name="doc.md",
            file_id="abc123def456",
            mtime=0.0,
            added="2026-01-01T00:00:00",
            content_hash="hash123",
            active=True,
            chunks=[
                ChunkRef(index=0, content_hash="c0"),
                ChunkRef(index=1, content_hash="c1"),
            ],
        )
        kb = KnowledgeBase(
            path=base_dir,
            files={"doc.md": file_entry},
        )
        cfg_data = WorkspaceConfigData(bases={"my_base": kb})
        ws_config = WorkspaceConfig(config_path, workspace_dir)
        ws_config.save(cfg_data)

        # Crea cartella chunks fittizia
        chunks_dir = base_dir / ".knowledge-space" / "chunks" / "abc123def456"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        (chunks_dir / "abc123def456_chunk_0.md").write_text("p1")
        (chunks_dir / "abc123def456_chunk_1.md").write_text("p2")

        # Senza conferma (input="n\n"): annulla
        result = runner.invoke(
            app,
            ["base", "remove", "my_base", "--workspace", str(workspace_dir)],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Attenzione" in result.output
        assert "annullata" in result.output.lower()
        # Base non rimossa: state.json ancora presente
        assert config_path.exists()

    def test_base_remove_with_files_confirm_deletes(
        self, workspace_dir: Path, base_dir: Path
    ):
        """Conferma sì → base rimossa e chunk cancellati."""
        from knowledge_base.models import (
            ChunkRef,
            FileEntry,
            KnowledgeBase,
            WorkspaceConfigData,
        )
        from knowledge_base.persistence import WorkspaceConfig

        config_path = workspace_dir / ".knowledge-space" / "state.json"
        file_entry = FileEntry(
            name="doc.md",
            file_id="abc123def456",
            mtime=0.0,
            added="2026-01-01T00:00:00",
            content_hash="hash123",
            active=True,
            chunks=[
                ChunkRef(index=0, content_hash="c0"),
                ChunkRef(index=1, content_hash="c1"),
            ],
        )
        kb = KnowledgeBase(
            path=base_dir,
            files={"doc.md": file_entry},
        )
        cfg_data = WorkspaceConfigData(bases={"my_base": kb})
        ws_config = WorkspaceConfig(config_path, workspace_dir)
        ws_config.save(cfg_data)

        chunks_dir = base_dir / ".knowledge-space" / "chunks" / "abc123def456"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        (chunks_dir / "abc123def456_chunk_0.md").write_text("p1")
        (chunks_dir / "abc123def456_chunk_1.md").write_text("p2")

        result = runner.invoke(
            app,
            ["base", "remove", "my_base", "--workspace", str(workspace_dir)],
            input="y\n",
        )
        assert result.exit_code == 0
        assert "rimossa" in result.output.lower() or "rimosso" in result.output.lower()
        assert not chunks_dir.exists()

    def test_base_remove_force_flag(
        self, workspace_dir: Path, base_dir: Path
    ):
        """--force salta la conferma."""
        from knowledge_base.models import (
            ChunkRef,
            FileEntry,
            KnowledgeBase,
            WorkspaceConfigData,
        )
        from knowledge_base.persistence import WorkspaceConfig

        config_path = workspace_dir / ".knowledge-space" / "state.json"
        file_entry = FileEntry(
            name="doc.md",
            file_id="abc123def456",
            mtime=0.0,
            added="2026-01-01T00:00:00",
            content_hash="hash123",
            active=True,
            chunks=[
                ChunkRef(index=0, content_hash="c0"),
            ],
        )
        kb = KnowledgeBase(
            path=base_dir,
            files={"doc.md": file_entry},
        )
        cfg_data = WorkspaceConfigData(bases={"my_base": kb})
        ws_config = WorkspaceConfig(config_path, workspace_dir)
        ws_config.save(cfg_data)

        chunks_dir = base_dir / ".knowledge-space" / "chunks" / "abc123def456"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        (chunks_dir / "abc123def456_chunk_0.md").write_text("p1")

        result = runner.invoke(
            app,
            [
                "base", "remove", "my_base",
                "--force",
                "--workspace", str(workspace_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Procedere" not in result.output
        assert "rimossa" in result.output.lower() or "rimosso" in result.output.lower()

    def test_base_remove_empty_base_no_warning(
        self, workspace_dir: Path, base_dir: Path
    ):
        """Base senza file: nessun warning, rimozione diretta."""
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            ["base", "remove", "my_base", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "Attenzione" not in result.output
        assert "rimossa" in result.output.lower() or "rimosso" in result.output.lower()


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
        assert "nessuna base" in result.output.lower()

    def test_search_with_bases(self, workspace_dir: Path, base_dir: Path):
        """La ricerca su basi senza file indicizzati restituisce 0 risultati."""
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app, ["search", "test", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0
        assert "Nessun risultato" in result.output


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

    def test_status_non_mostra_base_rimossa_da_disco(self, workspace_dir: Path, base_dir: Path):
        """Bug 019: base cancellata/spostata su disco sparisce da ks status."""
        import shutil

        # Registra la base nello stato
        result = runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0

        # La base è visibile
        result = runner.invoke(
            app, ["status", "--workspace", str(workspace_dir)]
        )
        assert "my_base" in result.output

        # Rimuovi la directory dal disco (simula mv/rm col watcher spento)
        shutil.rmtree(base_dir)

        # status deve fare sync e non mostrarla più
        result = runner.invoke(
            app, ["status", "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0
        assert "my_base" not in result.output

    def test_workspace_info_non_mostra_base_rimossa_da_disco(
        self, workspace_dir: Path, base_dir: Path
    ):
        """Bug 019: workspace info applica la stessa sync di status."""
        import shutil

        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )

        result = runner.invoke(
            app, ["workspace", "info", str(workspace_dir)]
        )
        assert "1" in result.output  # 1 base

        shutil.rmtree(base_dir)

        result = runner.invoke(
            app, ["workspace", "info", str(workspace_dir)]
        )
        assert result.exit_code == 0
        assert "Basi: 0" in result.output


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

    # --- config set ---

    def test_config_set_defaults(self, workspace_dir: Path, monkeypatch):
        """config set defaults modifica defaults.toml."""
        monkeypatch.chdir(workspace_dir)
        result = runner.invoke(
            app,
            ["config", "set", "chunking.chunk_size", "500",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "chunking.chunk_size" in result.output
        assert "500" in result.output

        # Verifica il contenuto del file
        defaults_path = workspace_dir / ".knowledge-space" / "defaults.toml"
        assert defaults_path.exists()
        import tomllib

        with open(defaults_path, "rb") as f:
            data = tomllib.load(f)
        assert data["chunking"]["chunk_size"] == 500

    def test_config_set_creates_defaults_if_missing(self, workspace_dir: Path, monkeypatch):
        """config set crea defaults.toml se assente."""
        monkeypatch.chdir(workspace_dir)
        defaults_path = workspace_dir / ".knowledge-space" / "defaults.toml"
        assert not defaults_path.exists()

        result = runner.invoke(
            app,
            ["config", "set", "embedding.model", "my/model",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert defaults_path.exists()

        import tomllib

        with open(defaults_path, "rb") as f:
            data = tomllib.load(f)
        assert data["embedding"]["model"] == "my/model"

    def test_config_set_base(self, workspace_dir: Path, base_dir: Path):
        """config set su base crea base.toml e scrive il valore."""
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            ["config", "set", "-b", "my_base", "embedding.model", "BAAI/bge-m3",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0

        base_toml = base_dir / ".knowledge-space" / "base.toml"
        assert base_toml.exists()
        import tomllib

        with open(base_toml, "rb") as f:
            data = tomllib.load(f)
        assert data["embedding"]["model"] == "BAAI/bge-m3"

    def test_config_set_invalid_scope(self, workspace_dir: Path):
        """Base inesistente con -b → errore."""
        result = runner.invoke(
            app,
            ["config", "set", "-b", "nonexistent", "chunking.chunk_size", "500",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 1

    def test_config_set_invalid_key(self, workspace_dir: Path, monkeypatch):
        """Chiave non valida → errore."""
        monkeypatch.chdir(workspace_dir)
        result = runner.invoke(
            app,
            ["config", "set", "badkey",
             "500", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 1

    def test_config_set_unknown_section(self, workspace_dir: Path, monkeypatch):
        """Sezione sconosciuta → errore."""
        monkeypatch.chdir(workspace_dir)
        result = runner.invoke(
            app,
            ["config", "set", "nosuch.field", "x",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 1

    def test_config_set_unknown_field(self, workspace_dir: Path, monkeypatch):
        """Campo inesistente nella sezione → errore."""
        monkeypatch.chdir(workspace_dir)
        result = runner.invoke(
            app,
            ["config", "set", "chunking.nonexistent", "500",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 1

    def test_config_set_preserves_other_keys(self, workspace_dir: Path, monkeypatch):
        """config set non distrugge le chiavi esistenti."""
        monkeypatch.chdir(workspace_dir)
        # Prima set
        runner.invoke(
            app,
            ["config", "set", "chunking.chunk_size", "500",
             "--workspace", str(workspace_dir)],
        )
        # Seconda set su chiave diversa
        runner.invoke(
            app,
            ["config", "set", "embedding.model", "my/model",
             "--workspace", str(workspace_dir)],
        )
        import tomllib

        defaults_path = workspace_dir / ".knowledge-space" / "defaults.toml"
        with open(defaults_path, "rb") as f:
            data = tomllib.load(f)
        assert data["chunking"]["chunk_size"] == 500
        assert data["embedding"]["model"] == "my/model"

    def test_config_set_bool_value(self, workspace_dir: Path, monkeypatch):
        """Valori booleani vengono parsati correttamente."""
        monkeypatch.chdir(workspace_dir)
        result = runner.invoke(
            app,
            ["config", "set", "graph.enabled", "true",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0

        import tomllib

        defaults_path = workspace_dir / ".knowledge-space" / "defaults.toml"
        with open(defaults_path, "rb") as f:
            data = tomllib.load(f)
        assert data["graph"]["enabled"] is True

    # --- config unset ---

    def test_config_unset_removes_key(self, workspace_dir: Path, monkeypatch):
        """config unset rimuove la chiave dal TOML."""
        monkeypatch.chdir(workspace_dir)
        # Set prima
        runner.invoke(
            app,
            ["config", "set", "chunking.chunk_size", "500",
             "--workspace", str(workspace_dir)],
        )
        import tomllib

        defaults_path = workspace_dir / ".knowledge-space" / "defaults.toml"
        with open(defaults_path, "rb") as f:
            data = tomllib.load(f)
        assert "chunk_size" in data.get("chunking", {})

        # Unset
        result = runner.invoke(
            app,
            ["config", "unset", "chunking.chunk_size",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "rimossa" in result.output.lower()

        with open(defaults_path, "rb") as f:
            data = tomllib.load(f)
        assert "chunk_size" not in data.get("chunking", {})

    def test_config_unset_missing_file(self, workspace_dir: Path, monkeypatch):
        """config unset su file inesistente → no-op con messaggio."""
        monkeypatch.chdir(workspace_dir)
        result = runner.invoke(
            app,
            ["config", "unset", "chunking.chunk_size",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "non esiste" in result.output.lower()

    def test_config_unset_missing_key(self, workspace_dir: Path, monkeypatch):
        """config unset su chiave assente → messaggio informativo."""
        monkeypatch.chdir(workspace_dir)
        # Crea il file con init
        runner.invoke(
            app, ["config", "init", "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            ["config", "unset", "chunking.nonexistent",
             "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert "non presente" in result.output.lower()

    # --- config edit ---

    def test_config_edit_creates_file_and_opens_editor(
        self, workspace_dir: Path, monkeypatch
    ):
        """config edit crea il TOML e apre l'editor."""
        monkeypatch.chdir(workspace_dir)
        # Mock EDITOR a 'true' (no-op)
        monkeypatch.setenv("EDITOR", "true")
        defaults_path = workspace_dir / ".knowledge-space" / "defaults.toml"
        assert not defaults_path.exists()

        result = runner.invoke(
            app,
            ["config", "edit", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        assert defaults_path.exists()

    def test_config_edit_base(self, workspace_dir: Path, base_dir: Path, monkeypatch):
        """config edit su base apre base.toml."""
        monkeypatch.setenv("EDITOR", "true")
        runner.invoke(
            app, ["base", "add", str(base_dir), "--workspace", str(workspace_dir)]
        )
        result = runner.invoke(
            app,
            ["config", "edit", "-b", "my_base", "--workspace", str(workspace_dir)],
        )
        assert result.exit_code == 0
        base_toml = base_dir / ".knowledge-space" / "base.toml"
        assert base_toml.exists()

    # --- help e autocomplete ---

    def test_config_set_help_contains_keys(self):
        """config set --help mostra le chiavi configurabili."""
        result = runner.invoke(app, ["config", "set", "--help"])
        assert result.exit_code == 0
        # Verifica che alcune chiavi attese siano presenti
        assert "chunking.method" in result.output
        assert "chunking.chunk_size" in result.output
        assert "embedding.model" in result.output
        assert "ingestion.library" in result.output
        assert "graph.enabled" in result.output

    def test_build_keys_help_contains_expected_keys(self):
        """_build_keys_help() produce una tabella con le chiavi attese."""
        from knowledge_space.cli.config import _build_keys_help

        help_text = _build_keys_help()
        # Header
        assert "KEY" in help_text
        assert "TIPO" in help_text
        assert "DEFAULT" in help_text
        # Chiavi specifiche
        assert "chunking.method" in help_text
        assert "chunking.chunk_size" in help_text
        assert "embedding.model" in help_text
        assert "ingestion.library" in help_text
        assert "graph.enabled" in help_text
        assert "retrieval.method" in help_text
        assert "post_retrieval.method" in help_text
        # Tipi
        assert "int" in help_text
        assert "str" in help_text
        assert "bool" in help_text
        # Valori default
        assert '"recursive"' in help_text
        assert '800' in help_text
        assert '"docling"' in help_text

    def test_all_valid_keys_returns_expected_keys(self):
        """_all_valid_keys() restituisce tutte le chiavi dotted."""
        from knowledge_space.cli.config import _all_valid_keys

        keys = _all_valid_keys()
        assert "chunking.method" in keys
        assert "chunking.chunk_size" in keys
        assert "embedding.model" in keys
        assert "ingestion.library" in keys
        assert "graph.enabled" in keys
        assert len(keys) >= 20  # Almeno 20 chiavi totali

    def test_key_autocomplete_filters_correctly(self):
        """_key_autocomplete filtra le chiavi che iniziano con incomplete."""
        from knowledge_space.cli.config import _key_autocomplete

        # Simula contesto Typer minimale
        class FakeCtx:
            pass

        results = _key_autocomplete(FakeCtx(), [], "chunking.")
        assert len(results) >= 3  # method, chunk_size, chunk_overlap, separator, params
        for key, desc in results:
            assert key.startswith("chunking.")

        results_empty = _key_autocomplete(FakeCtx(), [], "nonexistent.")
        assert results_empty == []


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


# --------------------------------------------------------------------------- #
