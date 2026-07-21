"""Strategy registry per ingestion, chunking ed embedding.

Ogni categoria di strategia ha il proprio registry, implementato con il
pattern plugin: si registra una strategia per nome e la si recupera per
nome. Il registry è istanziato come singleton di modulo e popolato
all'avvio con le strategie built-in.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Protocol, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class StrategyRegistry:
    """Registry generico per strategie identificate da nome.

    Uso tipico::

        registry = StrategyRegistry()
        registry.register("docling", DoclingIngestion)
        strategy_cls = registry.get("docling")
        instance = strategy_cls(**params)
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, Type] = {}

    def register(self, name: str, strategy_cls: Type) -> None:
        """Registra una strategia con il nome dato."""
        self._strategies[name] = strategy_cls
        logger.debug("Registrata strategia '%s' -> %s", name, strategy_cls)

    def get(self, name: str) -> Type:
        """Restituisce la classe della strategia registrata.

        Solleva ``KeyError`` se il nome non è registrato.
        """
        if name not in self._strategies:
            available = ", ".join(sorted(self._strategies)) or "(nessuna)"
            raise KeyError(
                f"Strategia '{name}' non trovata. Disponibili: {available}"
            )
        return self._strategies[name]

    def get_or_default(self, name: Optional[str], default: str) -> Type:
        """Restituisce la strategia per ``name``, o quella ``default`` se
        ``name`` è ``None``."""
        return self.get(name if name is not None else default)

    def list_names(self) -> List[str]:
        """Restituisce i nomi di tutte le strategie registrate."""
        return sorted(self._strategies)

    def contains(self, name: str) -> bool:
        """Restituisce ``True`` se il nome è registrato."""
        return name in self._strategies


# --------------------------------------------------------------------------- #
# Interfacce (Protocol) per type checking
# --------------------------------------------------------------------------- #


class IngestionStrategy(Protocol):
    """Interfaccia per le strategie di ingestion (Step 4)."""

    name: str
    supported_extensions: List[str]

    def convert(self, source_path: str) -> str:
        """Converte un file sorgente in markdown."""
        ...


class ChunkingStrategy(Protocol):
    """Interfaccia per le strategie di chunking (Step 5)."""

    name: str
    requires_embedding: bool = False

    def split(self, text: str) -> List[str]:
        """Divide un testo in chunk."""
        ...


class EmbeddingMetadata:
    """Metadati discoverable di un modello di embedding (Step 6)."""

    def __init__(
        self,
        model_name: str,
        languages: List[str],
        dim: int,
        max_context_tokens: int,
        license: str,
        requires_api: bool = False,
    ) -> None:
        self.model_name = model_name
        self.languages = languages
        self.dim = dim
        self.max_context_tokens = max_context_tokens
        self.license = license
        self.requires_api = requires_api


class EmbeddingStrategy(Protocol):
    """Interfaccia per le strategie di embedding (Step 6)."""

    name: str
    metadata: EmbeddingMetadata

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Restituisce embedding per ogni testo in input."""
        ...


# --------------------------------------------------------------------------- #
# Registry singleton di modulo (popolati all'avvio)
# --------------------------------------------------------------------------- #

ingestion_registry = StrategyRegistry()
chunking_registry = StrategyRegistry()
embedding_registry = StrategyRegistry()


# Import dei submoduli alla fine: la loro importazione popola i registry
# con le strategie built-in. I submoduli importano nomi già definiti sopra
# (nessun import circolare).
from knowledge_base.strategies import chunking as _chunking  # noqa: F401,E402
from knowledge_base.strategies import embedding as _embedding  # noqa: F401,E402
from knowledge_base.strategies import ingestion as _ingestion  # noqa: F401,E402
