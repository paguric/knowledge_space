"""AppContext — dependency injection container per Knowledge Space.

Punto unico in cui tutte le dipendenze vengono assemblate. CLI, MCP e REST
ricevono un ``AppContext`` già pronto. Nessuna variabile globale: tutto
passato esplicitamente.

Step 8-ter della roadmap.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from knowledge_base.base_config import BaseConfig, BaseConfigLoader
    from knowledge_base.domain_manager import DomainManager
    from knowledge_base.knowledge_base_manager import KnowledgeBaseManager
    from knowledge_base.models import GraphConfigData, Workspace
    from knowledge_base.persistence import GlobalIndex, WorkspaceConfig
    from knowledge_base.strategies import EmbeddingStrategy, LLMStrategy
    from knowledge_base.workspace_manager import WorkspaceManager
    from knowledge_space.runtime_paths import RuntimePaths


@dataclass
class AppContext:
    """Contenitore delle dipendenze dell'applicazione.

    Costruito da :func:`build_app_context`, ricevuto da CLI, MCP e REST.
    Tutti i campi sono iniettati esplicitamente — nessuna variabile globale.
    """

    runtime_paths: RuntimePaths
    """Path XDG e convenzioni .knowledge-space/."""

    global_index: GlobalIndex
    """Loader/saver dell'indice globale dei workspace."""

    workspace_manager: WorkspaceManager
    """Operazioni CRUD sui workspace."""

    domain_manager: DomainManager
    """Operazioni sui domini."""

    base_config_loader_factory: Callable[[Path], BaseConfigLoader]
    """Factory che, dato il path di un workspace, restituisce il
    ``BaseConfigLoader`` per leggere la configurazione delle sue basi."""

    base_manager_factory: Callable[[Workspace], KnowledgeBaseManager]
    """Factory che, dato un ``Workspace``, restituisce un
    ``KnowledgeBaseManager`` configurato per operare su quel workspace."""

    embedder_factory: Callable[[str], EmbeddingStrategy]
    """Factory che, dato il nome di un modello di embedding, restituisce
    la :class:`EmbeddingStrategy` corrispondente."""

    llm_factory: Callable[[str], LLMStrategy]
    """Factory che, dato il nome di un modello LLM, restituisce la
    :class:`LLMStrategy` corrispondente."""

    graph_store_factory: Optional[Callable[..., Any]] = None
    """Factory per lo store del grafo (refactor-001): accetta
    ``uri``/``user``/``password``/``database`` come kwargs e restituisce
    un ``GraphStore``. ``None`` se non configurato."""

    graph_manager_factory: Optional[Callable[[Workspace], Any]] = None
    """Factory che, dato un ``Workspace``, restituisce un ``GraphManager``
    (refactor-001). ``None`` se non configurato."""
