"""Test per AppContext e build_app_context (Step 8-ter).

Verifica:
- Costruzione con path temporanei (nessun side-effect su ~/.config)
- Tutti i campi sono popolati
- Factory funzionanti (base_manager_factory, embedder_factory, llm_factory)
- Default XDG rispettati
- Wiring corretto (stesse istanze condivise)
- RuntimePaths.ensure_dirs() invocato
- graph_store_factory opzionale
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

from knowledge_base.base_config import BaseConfigLoader
from knowledge_base.domain_manager import DomainManager
from knowledge_base.knowledge_base_manager import KnowledgeBaseManager
from knowledge_base.models import GraphConfigData, Workspace
from knowledge_base.persistence import GlobalIndex, WorkspaceConfig
from knowledge_base.strategies import EmbeddingMetadata, EmbeddingStrategy, LLMStrategy
from knowledge_base.strategies.llm import MockEchoLLM, llm_factory
from knowledge_base.workspace_manager import WorkspaceManager

from knowledge_space.bootstrap import build_app_context
from knowledge_space.context import AppContext
from knowledge_space.runtime_paths import RuntimePaths


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _make_runtime_paths(tmp_path: Path) -> RuntimePaths:
    """Crea RuntimePaths con path temporanei (no side-effect su ~/)."""
    return RuntimePaths(
        config_home=tmp_path / "config",
        data_home=tmp_path / "data",
        state_home=tmp_path / "state",
        dot_folder_name=".knowledge-space",
    )


def _make_mock_embedder(model_name: str) -> EmbeddingStrategy:
    """Embedder mock che restituisce vettori fittizi."""

    class _MockEmbedder:
        name = model_name
        metadata = EmbeddingMetadata(
            model_name=model_name,
            languages=["en"],
            dim=4,
            max_context_tokens=512,
            license="mock",
            requires_api=False,
        )

        def embed(self, texts: List[str]) -> List[List[float]]:
            return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    return _MockEmbedder()  # type: ignore[return-value]


def _make_mock_llm(model_name: str) -> LLMStrategy:
    """LLM mock che restituisce l'ultimo messaggio utente."""
    return MockEchoLLM()


# --------------------------------------------------------------------------- #
# Test AppContext dataclass
# --------------------------------------------------------------------------- #


class TestAppContextDataclass:
    """Test sulla struttura di AppContext."""

    def test_has_all_fields(self):
        """AppContext ha tutti i campi previsti dalla roadmap."""
        import dataclasses

        fields = {f.name for f in dataclasses.fields(AppContext)}
        expected = {
            "runtime_paths",
            "global_index",
            "workspace_manager",
            "domain_manager",
            "base_config_loader_factory",
            "base_manager_factory",
            "embedder_factory",
            "llm_factory",
            "graph_store_factory",
        }
        assert expected == fields

    def test_graph_store_factory_default_none(self):
        """graph_store_factory ha default None."""
        rp = _make_runtime_paths(Path("/tmp"))
        gi = GlobalIndex(path=rp.workspaces_index)

        def _config_path_for(ws_path: Path) -> Path:
            return rp.workspace_state_file(ws_path)

        ctx = AppContext(
            runtime_paths=rp,
            global_index=gi,
            workspace_manager=WorkspaceManager(
                global_index=gi, config_path_for=_config_path_for
            ),
            domain_manager=DomainManager(config_path_for=_config_path_for),
            base_config_loader_factory=lambda p: BaseConfigLoader(workspace_path=p),
            base_manager_factory=lambda ws: None,  # type: ignore[arg-type]
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )
        assert ctx.graph_store_factory is None


# --------------------------------------------------------------------------- #
# Test build_app_context
# --------------------------------------------------------------------------- #


class TestBuildContext:
    """Test su build_app_context."""

    def test_creates_all_fields(self, tmp_path):
        """build_app_context popola tutti i campi."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )

        assert ctx.runtime_paths is rp
        assert isinstance(ctx.global_index, GlobalIndex)
        assert isinstance(ctx.workspace_manager, WorkspaceManager)
        assert isinstance(ctx.domain_manager, DomainManager)
        assert callable(ctx.base_config_loader_factory)
        assert callable(ctx.base_manager_factory)
        assert callable(ctx.embedder_factory)
        assert callable(ctx.llm_factory)
        assert ctx.graph_store_factory is None

    def test_ensure_dirs_called(self, tmp_path):
        """build_app_context crea le directory XDG."""
        rp = _make_runtime_paths(tmp_path)
        build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )
        assert rp.config_home.is_dir()
        assert rp.data_home.is_dir()
        assert rp.state_home.is_dir()

    def test_default_runtime_paths(self, monkeypatch, tmp_path):
        """Se runtime_paths è None, usa RuntimePaths.default()."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

        ctx = build_app_context(
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )

        assert ctx.runtime_paths.config_home == tmp_path / "cfg" / "KnowledgeSpace"
        assert ctx.runtime_paths.data_home == tmp_path / "data" / "KnowledgeSpace"
        assert ctx.runtime_paths.state_home == tmp_path / "state" / "KnowledgeSpace"

    def test_shared_global_index(self, tmp_path):
        """GlobalIndex è condiviso tra context e workspace_manager."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )
        assert ctx.global_index is ctx.workspace_manager._index

    def test_graph_store_factory_custom(self, tmp_path):
        """graph_store_factory custom è preservato."""
        rp = _make_runtime_paths(tmp_path)

        def _my_graph(config: GraphConfigData) -> Any:
            return {"neo4j": True}

        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
            graph_store_factory=_my_graph,
        )
        assert ctx.graph_store_factory is _my_graph


# --------------------------------------------------------------------------- #
# Test factory integrazione
# --------------------------------------------------------------------------- #


class TestFactories:
    """Test sulle factory iniettate in AppContext."""

    def test_embedder_factory_returns_strategy(self, tmp_path):
        """embedder_factory restituisce un EmbeddingStrategy valido."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )
        emb = ctx.embedder_factory("test-model")
        assert hasattr(emb, "embed")
        assert hasattr(emb, "metadata")
        vectors = emb.embed(["hello world"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 4

    def test_llm_factory_returns_strategy(self, tmp_path):
        """llm_factory restituisce un LLMStrategy valido."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )
        llm = ctx.llm_factory("test-model")
        assert hasattr(llm, "generate")
        assert hasattr(llm, "stream")
        result = llm.generate([{"role": "user", "content": "ciao"}])
        assert "ciao" in result

    def test_llm_factory_default_real(self, tmp_path):
        """Senza override, llm_factory usa il registry reale (mock/echo)."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
        )
        llm = ctx.llm_factory("mock/echo")
        result = llm.generate([{"role": "user", "content": "test"}])
        assert result == "test"

    def test_base_config_loader_factory(self, tmp_path):
        """base_config_loader_factory restituisce un BaseConfigLoader."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )
        ws_path = tmp_path / "my_workspace"
        ws_path.mkdir()
        loader = ctx.base_config_loader_factory(ws_path)
        assert isinstance(loader, BaseConfigLoader)
        assert loader._workspace_path == ws_path

    def test_base_manager_factory(self, tmp_path):
        """base_manager_factory restituisce un KnowledgeBaseManager."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )
        ws_path = tmp_path / "my_workspace"
        ws_path.mkdir()
        workspace = Workspace(path=ws_path)
        manager = ctx.base_manager_factory(workspace)
        assert isinstance(manager, KnowledgeBaseManager)

    def test_base_manager_factory_wired_correctly(self, tmp_path):
        """Il KnowledgeBaseManager usa le factory del context."""
        rp = _make_runtime_paths(tmp_path)
        custom_embedder_calls: list[str] = []

        def _tracking_embedder(model_name: str) -> EmbeddingStrategy:
            custom_embedder_calls.append(model_name)
            return _make_mock_embedder(model_name)

        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_tracking_embedder,
            llm_factory=_make_mock_llm,
        )
        ws_path = tmp_path / "my_workspace"
        ws_path.mkdir()
        workspace = Workspace(path=ws_path)
        manager = ctx.base_manager_factory(workspace)
        # La factory dell'embedder è stata iniettata
        assert manager._embedder_factory is _tracking_embedder


# --------------------------------------------------------------------------- #
# Test wiring end-to-end
# --------------------------------------------------------------------------- #


class TestEndToEndWiring:
    """Test di wiring end-to-end con workspace reale."""

    def test_workspace_roundtrip(self, tmp_path):
        """Crea workspace, registra, lista, carica via AppContext."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )

        ws_path = tmp_path / "test_workspace"
        ws_path.mkdir()

        # Add workspace
        added = ctx.workspace_manager.add(ws_path)
        assert added is True

        # List workspaces
        workspaces = ctx.workspace_manager.list()
        assert ws_path in workspaces

        # Load workspace
        workspace = ctx.workspace_manager.load(ws_path)
        assert workspace.path == ws_path

        # Double-add returns False
        assert ctx.workspace_manager.add(ws_path) is False

    def test_domain_roundtrip(self, tmp_path):
        """Crea dominio e base via AppContext."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )

        ws_path = tmp_path / "test_workspace"
        ws_path.mkdir()
        ctx.workspace_manager.add(ws_path)
        workspace = ctx.workspace_manager.load(ws_path)

        # Crea dominio
        domain = ctx.domain_manager.create(workspace, "diritto", ["base1"])
        assert domain.name == "diritto"
        assert domain.base_names == ["base1"]

        # Ricarica workspace e verifica persistenza
        workspace2 = ctx.workspace_manager.load(ws_path)
        assert len(workspace2.domains) == 1
        assert workspace2.domains[0].name == "diritto"

    def test_base_manager_factory_with_real_config(self, tmp_path):
        """Crea KnowledgeBaseManager via factory e verifica config loader."""
        rp = _make_runtime_paths(tmp_path)
        ctx = build_app_context(
            runtime_paths=rp,
            embedder_factory=_make_mock_embedder,
            llm_factory=_make_mock_llm,
        )

        ws_path = tmp_path / "test_workspace"
        ws_path.mkdir()
        ctx.workspace_manager.add(ws_path)

        # Crea una base
        base_path = ws_path / "my_base"
        base_path.mkdir()

        workspace = ctx.workspace_manager.load(ws_path)
        manager = ctx.base_manager_factory(workspace)
        kb = manager.add(base_path)
        assert kb.path == base_path
        assert "my_base" in workspace.bases
