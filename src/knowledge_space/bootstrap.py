"""Bootstrap — costruzione di ``AppContext``.

Entry point unico per assemblare tutte le dipendenze dell'applicazione.
CLI, MCP e REST chiamano :func:`build_app_context` per ottenere un
``AppContext`` già pronto.

Step 8-ter della roadmap.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from knowledge_base.base_config import BaseConfigLoader
from knowledge_base.domain_manager import DomainManager
from knowledge_base.graph_manager import GraphManager
from knowledge_base.knowledge_base_manager import (
    KnowledgeBaseManager,
    chroma_collection_name,
)
from knowledge_base.models import Workspace
from knowledge_base.persistence import GlobalIndex, WorkspaceConfig
from knowledge_base.strategies import EmbeddingStrategy, LLMStrategy
from knowledge_base.strategies.embedding import embedding_registry
from knowledge_base.strategies.llm import llm_factory as _default_llm_factory
from knowledge_base.workspace_manager import WorkspaceManager

from knowledge_space.context import AppContext
from knowledge_space.runtime_paths import RuntimePaths

logger = logging.getLogger(__name__)


def _default_embedder_factory(model_name: str) -> EmbeddingStrategy:
    """Costruisce l'embedder dal registry (Step 6).

    Override via env var per ``device``/``api_base`` non implementati qui:
    la factory di default istanzia direttamente dal registry.
    """
    cls = embedding_registry.get(model_name)
    return cls()


def _default_graph_store_factory(
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    database: str = "neo4j",
) -> Any:
    """Store del grafo di default: backend neo4j (refactor-001)."""
    from knowledge_base.graph.store import graph_store_factory

    return graph_store_factory(
        "neo4j", uri=uri, user=user, password=password, database=database
    )


def build_app_context(
    *,
    runtime_paths: Optional[RuntimePaths] = None,
    embedder_factory: Optional[Callable[[str], EmbeddingStrategy]] = None,
    llm_factory: Optional[Callable[[str], LLMStrategy]] = None,
    graph_store_factory: Optional[Callable[..., Any]] = None,
) -> AppContext:
    """Costruisce un ``AppContext`` con tutte le dipendenze.

    Parametri opzionali permettono di iniettare factory custom (per test
    o configurazioni avanzate); i default usano i registry di Step 4/5/6.

    Args:
        runtime_paths: Path XDG. Se ``None``, usa :meth:`RuntimePaths.default`.
        embedder_factory: Factory per embedding. Se ``None``, usa il registry.
        llm_factory: Factory per LLM. Se ``None``, usa ``llm_factory`` di Step 6-bis.
        graph_store_factory: Factory per lo store del grafo (refactor-001).
            Default: backend neo4j via ``graph_store_factory``.

    Returns:
        ``AppContext`` completamente cablato.
    """
    # 1. RuntimePaths
    if runtime_paths is None:
        runtime_paths = RuntimePaths.default()
    runtime_paths.ensure_dirs()

    # 2. GlobalIndex
    global_index = GlobalIndex(path=runtime_paths.workspaces_index)

    # 3. Factory per BaseConfigLoader (dato workspace path)
    def _base_config_loader_factory(ws_path: Path) -> BaseConfigLoader:
        return BaseConfigLoader(
            workspace_path=ws_path,
            dot_folder_name=runtime_paths.dot_folder_name,
        )

    # 4. WorkspaceManager
    def _config_path_for(ws_path: Path) -> Path:
        return runtime_paths.workspace_state_file(ws_path)

    # 5. Embedder factory (definito prima di WorkspaceManager perché serve
    #    al base_manager_factory iniettato nel watcher)
    _embedder = embedder_factory or _default_embedder_factory

    # 6. Base manager factory (dato un Workspace)
    def _base_manager_factory(workspace: Workspace) -> KnowledgeBaseManager:
        config_loader_fn = _base_config_loader_factory(workspace.path)

        def _config_loader(base_name: str):
            return config_loader_fn.load(base_name)

        return KnowledgeBaseManager(
            workspace=workspace,
            config_loader=_config_loader,
            config_path_for=_config_path_for,
            embedder_factory=_embedder,
            dot_folder_name=runtime_paths.dot_folder_name,
        )

    workspace_manager = WorkspaceManager(
        global_index=global_index,
        config_path_for=_config_path_for,
        base_manager_factory=_base_manager_factory,
    )

    # 6-bis. Pulizia workspace orfani (cartelle non più presenti su disco).
    # Analogia con sync() per le basi: all'avvio di ogni comando ks i
    # workspace stale vengono rimossi dal registro. Lo stato su disco
    # resta: un successivo workspace add con lo stesso path lo ripristina.
    workspace_manager.prune_stale_workspaces()

    # 7. DomainManager
    domain_manager = DomainManager(
        config_path_for=_config_path_for,
    )

    # 8. LLM factory
    _llm = llm_factory or _default_llm_factory

    # 9. Graph store factory + GraphManager factory (refactor-001).
    _graph_store = graph_store_factory or _default_graph_store_factory

    def _graph_manager_factory(workspace: Workspace) -> GraphManager:
        config_loader_fn = _base_config_loader_factory(workspace.path)

        def _config_loader(base_name: str):
            return config_loader_fn.load(base_name)

        base_manager = _base_manager_factory(workspace)

        def _chroma_getter(base_name: str):
            return base_manager._chroma_client().get_collection(
                name=chroma_collection_name(base_name)
            )

        return GraphManager(
            workspace=workspace,
            config_loader=_config_loader,
            graph_store_factory=_graph_store,
            llm_factory=_llm,
            embedder_factory=_embedder,
            chroma_getter=_chroma_getter,
        )

    # L'hook grafo nel watcher usa la stessa factory.
    workspace_manager._graph_manager_factory = _graph_manager_factory

    return AppContext(
        runtime_paths=runtime_paths,
        global_index=global_index,
        workspace_manager=workspace_manager,
        domain_manager=domain_manager,
        base_config_loader_factory=_base_config_loader_factory,
        base_manager_factory=_base_manager_factory,
        embedder_factory=_embedder,
        llm_factory=_llm,
        graph_store_factory=_graph_store,
        graph_manager_factory=_graph_manager_factory,
    )
