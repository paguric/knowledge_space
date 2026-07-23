"""Strategy registry per ingestion, chunking, embedding ed LLM.

Ogni categoria di strategia ha il proprio registry, implementato con il
pattern plugin: si registra una strategia per nome e la si recupera per
nome. Il registry è istanziato come singleton di modulo e popolato
all'avvio con le strategie built-in.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Type

logger = logging.getLogger(__name__)


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
    """Interfaccia per le strategie di ingestion (Step 4).

    Una strategia converte un file sorgente in testo Markdown. I parametri
    della libreria sottostante sono passati al costruttore e memorizzati
    nell'istanza; :meth:`convert` riceve solo il path del file.
    """

    name: str
    library: str
    supported_extensions: List[str]

    def convert(self, source_path: Path) -> str:
        """Converte un file sorgente in markdown.

        Solleva :class:`UnsupportedFormatError` se l'estensione del file non
        è in ``supported_extensions``.
        """
        ...


class ChunkingStrategy(Protocol):
    """Interfaccia per le strategie di chunking (Step 5).

    Una strategia suddivide il testo Markdown (proveniente dall'ingestion)
    in frammenti. I parametri sono passati al costruttore dal
    ``BaseConfig.chunking``; :meth:`split` riceve solo il testo.

    Ogni strategia registra ``params_schema`` (mappa nome → tipo) e
    ``requires_embedding`` per la discoverability (il frontend li userà
    per guidare la configurazione utente).
    """

    name: str
    params_schema: Dict[str, type]
    requires_embedding: bool = False

    def split(self, text: str) -> List[Dict[str, Any]]:
        """Divide un testo in chunk.

        Returns:
            lista di dict, ciascuno con almeno ``"text"`` (str) e
            ``"index"`` (int). Strategie avanzate (es. ``markdown``)
            possono aggiungere metadata (es. ``"header_1"``).
        """
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
# LLM (Step 6-bis)
# --------------------------------------------------------------------------- #


class LLMMetadata:
    """Metadati discoverable di un modello LLM (Step 6-bis).

    Spec: ``docs/75-llm.md``. Le strategie mock e gli stub dei provider
    remoti/locali registrano un'istanza di questa classe nel
    :class:`LLMRegistry`. A differenza di :class:`EmbeddingMetadata`, i
    provider LLM non sono istanziabili da una factory generica in Fase
    1A (solo i mock): il registry associa quindi metadati + (opzionale)
    factory callable, e la ``llm_factory`` decide cosa istanziare.
    """

    def __init__(
        self,
        model_name: str,
        provider: str,            # "openai" | "anthropic" | "google" | "cohere"
                                  # | "ollama" | "llamacpp" | "vllm" | "mock"
        context_window: int,      # max input token
        requires_api: bool,       # False = locale, True = API remota
        supports_streaming: bool,
        supports_json: bool,      # function calling / output strutturato
    ) -> None:
        self.model_name = model_name
        self.provider = provider
        self.context_window = context_window
        self.requires_api = requires_api
        self.supports_streaming = supports_streaming
        self.supports_json = supports_json


class LLMStrategy(Protocol):
    """Interfaccia per le strategie LLM (Step 6-bis).

    Usata da pre-retrieval (multi_query/step_back/least_to_most),
    retrieval (HyDE) e post-retrieval (llm reranker, llm_chain_extract),
    oltre a GraphRAG (Fase 1C) e all'LLM generatore (Fase 3/4). Ogni
    componente sceglie il proprio modello nel proprio parametro TOML
    (nessuna sezione ``[llm]`` globale).
    """

    name: str
    metadata: LLMMetadata

    def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> str:
        """Genera testo a partire da una lista di messaggi (chat format).

        Args:
            messages: ``[{"role": "system"/"user"/"assistant",
                          "content": "..."}]``
            max_tokens: token massimi in output
            temperature: 0.0 = deterministico, >0 = più creativo
        """
        ...

    def stream(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Come :meth:`generate`, ma restituisce un iteratore di token."""
        ...


class LLMRegistry:
    """Registry di modelli LLM con metadati discoverable.

    Estende il pattern di :class:`StrategyRegistry` con una tabella
    metadati affiancata alle factory: necessario perché i provider
    remoti/locali, in Fase 1A, sono solo ``stub`` (registrati nei
    metadati ma non istanziabili, vedi ``docs/75-llm.md`` § F0). La
    :func:`llm_factory` consulta i metadati per decidere l'istanziazione.

    Voci registrate:
    - ``mock/*``: factory callable → istanza concreta (unica istanziabile
      in Fase 1A).
    - provider remoti/locali: solo metadati (``factory = None``); la
      ``llm_factory`` valida l'API key (se richiede) e solleva
      ``ProviderNotImplementedError``.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, Tuple[LLMMetadata, Optional[Callable[[], LLMStrategy]]]] = {}

    def register(
        self,
        name: str,
        metadata: LLMMetadata,
        factory: Optional[Callable[[], LLMStrategy]] = None,
    ) -> None:
        """Registra un modello con metadati e (opzionale) factory.

        ``factory = None`` (default) registra solo metadati (stub di
        provider non implementati in Fase 1A).
        """
        self._entries[name] = (metadata, factory)
        logger.debug("Registrato LLM '%s' (provider=%s)", name, metadata.provider)

    def contains(self, name: str) -> bool:
        return name in self._entries

    def get_metadata(self, name: str) -> LLMMetadata:
        if name not in self._entries:
            available = ", ".join(sorted(self._entries)) or "(nessuno)"
            raise KeyError(
                f"LLM '{name}' non registrato. Disponibili: {available}"
            )
        return self._entries[name][0]

    def get_factory(self, name: str) -> Optional[Callable[[], LLMStrategy]]:
        """Restituisce la factory (o ``None`` per stub senza factory)."""
        if name not in self._entries:
            available = ", ".join(sorted(self._entries)) or "(nessuno)"
            raise KeyError(
                f"LLM '{name}' non registrato. Disponibili: {available}"
            )
        return self._entries[name][1]

    def list_names(self) -> List[str]:
        return sorted(self._entries)


# --------------------------------------------------------------------------- #
# Registry singleton di modulo (popolati all'avvio)
# --------------------------------------------------------------------------- #

ingestion_registry = StrategyRegistry()
chunking_registry = StrategyRegistry()
embedding_registry = StrategyRegistry()
llm_registry = LLMRegistry()


# Import dei submoduli alla fine: la loro importazione popola i registry
# con le strategie built-in. I submoduli importano nomi già definiti sopra
# (nessun import circolare).
from knowledge_base.strategies import chunking as _chunking  # noqa: F401,E402
from knowledge_base.strategies import embedding as _embedding  # noqa: F401,E402
from knowledge_base.strategies import ingestion as _ingestion  # noqa: F401,E402
from knowledge_base.strategies import llm as _llm  # noqa: F401,E402
