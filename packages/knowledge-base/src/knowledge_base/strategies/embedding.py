"""Strategie di embedding: conversione chunk → vettori numerici.

Ogni strategia incapsula un modello di embedding (locale o remoto) e
registra metadati discoverable (``EmbeddingMetadata``). Il modello è
configurato per-base via TOML; il cambio è bloccato se la collection
Chroma non è vuota (Step 3 + Step 7).

Modelli supportati (12):
- 7 locali (sentence-transformers / HuggingFace)
- 2 OpenAI (text-embedding-3-small, text-embedding-3-large)
- 1 Cohere (embed-multilingual-v3.0)
- 2 Voyage (voyage-3, voyage-3-lite)

I client SDK remoti sono importati lazy in ``embed()``: il modulo si
importa anche senza SDK installati (il registry si popola comunque).
Le API key sono lette da env var, mai dal TOML.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from knowledge_base.strategies import (
    EmbeddingMetadata,
    EmbeddingStrategy,
    embedding_registry,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Eccezioni
# --------------------------------------------------------------------------- #


class MissingAPIKeyError(RuntimeError):
    """Sollevata quando una strategy remota non trova l'API key nell'env."""

    def __init__(self, provider: str, env_var: str) -> None:
        self.provider = provider
        self.env_var = env_var
        super().__init__(
            f"API key per {provider} non trovata. "
            f"Impostare la variabile d'ambiente {env_var}."
        )


class ChunkTooLongError(ValueError):
    """Sollevata quando un chunk eccede ``max_context_tokens`` del modello."""

    def __init__(
        self,
        base_name: str,
        file_name: str,
        chunk_index: int,
        n_tokens: int,
        max_tokens: int,
    ) -> None:
        self.base_name = base_name
        self.file_name = file_name
        self.chunk_index = chunk_index
        self.n_tokens = n_tokens
        self.max_tokens = max_tokens
        super().__init__(
            f"Base '{base_name}', file '{file_name}', chunk {chunk_index}: "
            f"lunghezza stimata {n_tokens} token supera il limite "
            f"del modello ({max_tokens} token)."
        )


# --------------------------------------------------------------------------- #
# Stima token + validazione contesto
# --------------------------------------------------------------------------- #


def estimate_tokens(text: str) -> int:
    """Stima conservativa del numero di token di un testo.

    Usa la regola empirica ~4 caratteri/token (valida per inglese; leggermente
    conservativa per italiano, che è ~3 char/token). In futuro si può
    raffinare con ``tiktoken`` (EN) o tokenizer HF (multilingua).
    """
    return max(1, len(text) // 4)


def validate_chunk_context(
    chunk_text: str,
    max_context_tokens: int,
    *,
    base_name: str,
    file_name: str,
    chunk_index: int,
) -> None:
    """Verifica che un chunk non ecceda ``max_context_tokens`` del modello.

    Solleva :class:`ChunkTooLongError` se la lunghezza stimata supera il
    limite. Non tronca silenziosamente.
    """
    n = estimate_tokens(chunk_text)
    if n > max_context_tokens:
        raise ChunkTooLongError(
            base_name, file_name, chunk_index, n, max_context_tokens
        )


# --------------------------------------------------------------------------- #
# Classe base
# --------------------------------------------------------------------------- #


class BaseEmbedding:
    """Base comune: espone ``name`` e ``metadata``. Le sottoclassi
    implementano :meth:`embed`."""

    name: str = ""
    metadata: EmbeddingMetadata

    def __init__(self, **params) -> None:
        self.params = params

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Locali — sentence-transformers (HuggingFace)
# --------------------------------------------------------------------------- #


class LocalEmbedding(BaseEmbedding):
    """Embedding locale via ``sentence-transformers``.

    Il modello viene scaricato al primo uso (cache HuggingFace). Supporta
    ``device`` (es. ``"cpu"``, ``"cuda"``) via parametro.
    """

    requires_api = False

    def __init__(
        self,
        model_name: str,
        metadata: EmbeddingMetadata,
        device: Optional[str] = None,
        **params,
    ) -> None:
        super().__init__(**params)
        self.name = model_name
        self.model_name = model_name
        self.metadata = metadata
        self.device = device
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            kwargs: Dict[str, Any] = {}
            if self.device:
                kwargs["device"] = self.device
            self._model = SentenceTransformer(self.model_name, **kwargs)
        return self._model

    def embed(self, texts: List[str]) -> List[List[float]]:
        import numpy as np

        model = self._load_model()
        vectors = model.encode(texts, convert_to_numpy=True)
        if isinstance(vectors, np.ndarray):
            return vectors.tolist()
        return [list(v) for v in vectors]


# --------------------------------------------------------------------------- #
# Remoti — OpenAI
# --------------------------------------------------------------------------- #


class OpenAIEmbedding(BaseEmbedding):
    """Embedding via OpenAI API (o endpoint OpenAI-compatibile).

    API key da ``OPENAI_API_KEY``. ``api_base`` opzionale per endpoint
    personalizzati (Ollama, vLLM, ecc.).
    """

    requires_api = True
    _ENV_VAR = "OPENAI_API_KEY"
    _DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        model_name: str,
        metadata: EmbeddingMetadata,
        api_base: Optional[str] = None,
        **params,
    ) -> None:
        super().__init__(**params)
        self.name = model_name
        self.model_name = model_name
        self.metadata = metadata
        self.api_base = api_base
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            api_key = os.environ.get(self._ENV_VAR)
            if not api_key:
                raise MissingAPIKeyError("OpenAI", self._ENV_VAR)
            base_url = self.api_base or os.environ.get(
                "OPENAI_BASE_URL", self._DEFAULT_BASE_URL
            )
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        return self._client

    def embed(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        # OpenAI richiede il nome modello senza prefisso provider
        api_model = self.model_name.split("/", 1)[1] if "/" in self.model_name else self.model_name
        response = client.embeddings.create(model=api_model, input=texts)
        return [list(d.embedding) for d in response.data]


# --------------------------------------------------------------------------- #
# Remoti — Cohere
# --------------------------------------------------------------------------- #


class CohereEmbedding(BaseEmbedding):
    """Embedding via Cohere API.

    API key da ``COHERE_API_KEY``. Usa ``input_type="search_document"``
    per i chunk in indicizzazione.
    """

    requires_api = True
    _ENV_VAR = "COHERE_API_KEY"

    def __init__(
        self,
        model_name: str,
        metadata: EmbeddingMetadata,
        api_base: Optional[str] = None,
        **params,
    ) -> None:
        super().__init__(**params)
        self.name = model_name
        self.model_name = model_name
        self.metadata = metadata
        self.api_base = api_base
        self._client = None

    def _get_client(self):
        if self._client is None:
            import cohere

            api_key = os.environ.get(self._ENV_VAR)
            if not api_key:
                raise MissingAPIKeyError("Cohere", self._ENV_VAR)
            kwargs: Dict[str, Any] = {}
            if self.api_base:
                kwargs["base_url"] = self.api_base
            self._client = cohere.ClientV2(api_key=api_key, **kwargs)
        return self._client

    def embed(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        api_model = self.model_name.split("/", 1)[1] if "/" in self.model_name else self.model_name
        response = client.embed(
            texts=texts,
            model=api_model,
            input_type="search_document",
            embedding_types=["float"],
        )
        return [list(v) for v in response.embeddings.float]


# --------------------------------------------------------------------------- #
# Remoti — Voyage
# --------------------------------------------------------------------------- #


class VoyageEmbedding(BaseEmbedding):
    """Embedding via Voyage AI API.

    API key da ``VOYAGE_API_KEY``. Usa ``input_type="document"`` per i
    chunk in indicizzazione.
    """

    requires_api = True
    _ENV_VAR = "VOYAGE_API_KEY"

    def __init__(
        self,
        model_name: str,
        metadata: EmbeddingMetadata,
        api_base: Optional[str] = None,
        **params,
    ) -> None:
        super().__init__(**params)
        self.name = model_name
        self.model_name = model_name
        self.metadata = metadata
        self.api_base = api_base
        self._client = None

    def _get_client(self):
        if self._client is None:
            import voyageai

            api_key = os.environ.get(self._ENV_VAR)
            if not api_key:
                raise MissingAPIKeyError("Voyage", self._ENV_VAR)
            self._client = voyageai.Client(api_key=api_key)
        return self._client

    def embed(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        api_model = self.model_name.split("/", 1)[1] if "/" in self.model_name else self.model_name
        result = client.embed(
            texts=texts,
            model=api_model,
            input_type="document",
        )
        return [list(v) for v in result.embeddings]


# --------------------------------------------------------------------------- #
# Tabella modelli + registrazione
# --------------------------------------------------------------------------- #

_LOCAL_MODELS: List[Dict[str, Any]] = [
    {
        "model_name": "sentence-transformers/all-mpnet-base-v2",
        "languages": ["en"], "dim": 768, "max_ctx": 384, "license": "Apache 2.0",
    },
    {
        "model_name": "sentence-transformers/all-MiniLM-L6-v2",
        "languages": ["en"], "dim": 384, "max_ctx": 384, "license": "Apache 2.0",
    },
    {
        "model_name": "Alibaba-NLP/gte-large-en-v1.5",
        "languages": ["en"], "dim": 1024, "max_ctx": 8192, "license": "Apache 2.0",
    },
    {
        "model_name": "BAAI/bge-large-en-v1.5",
        "languages": ["en"], "dim": 1024, "max_ctx": 512, "license": "MIT",
    },
    {
        "model_name": "BAAI/bge-m3",
        "languages": ["multilingual"], "dim": 1024, "max_ctx": 8192, "license": "MIT",
    },
    {
        "model_name": "intfloat/multilingual-e5-small",
        "languages": ["multilingual"], "dim": 384, "max_ctx": 512, "license": "MIT",
    },
    {
        "model_name": "intfloat/multilingual-e5-large",
        "languages": ["multilingual"], "dim": 1024, "max_ctx": 512, "license": "MIT",
    },
]

_REMOTE_MODELS: List[Dict[str, Any]] = [
    {
        "model_name": "openai/text-embedding-3-small",
        "languages": ["multilingual"], "dim": 1536, "max_ctx": 8191,
        "license": "Proprietaria", "provider": "openai",
    },
    {
        "model_name": "openai/text-embedding-3-large",
        "languages": ["multilingual"], "dim": 3072, "max_ctx": 8191,
        "license": "Proprietaria", "provider": "openai",
    },
    {
        "model_name": "cohere/embed-multilingual-v3.0",
        "languages": ["multilingual"], "dim": 1024, "max_ctx": 512,
        "license": "Proprietaria", "provider": "cohere",
    },
    {
        "model_name": "voyage/voyage-3",
        "languages": ["multilingual"], "dim": 1024, "max_ctx": 32000,
        "license": "Proprietaria", "provider": "voyage",
    },
    {
        "model_name": "voyage/voyage-3-lite",
        "languages": ["multilingual"], "dim": 1024, "max_ctx": 32000,
        "license": "Proprietaria", "provider": "voyage",
    },
]


def _make_metadata(entry: Dict[str, Any], requires_api: bool) -> EmbeddingMetadata:
    return EmbeddingMetadata(
        model_name=entry["model_name"],
        languages=entry["languages"],
        dim=entry["dim"],
        max_context_tokens=entry["max_ctx"],
        license=entry["license"],
        requires_api=requires_api,
    )


def _register_local(entry: Dict[str, Any]) -> None:
    md = _make_metadata(entry, requires_api=False)
    model_name = entry["model_name"]

    def _factory(_model_name=model_name, _md=md, **params):
        return LocalEmbedding(model_name=_model_name, metadata=_md, **params)

    embedding_registry.register(model_name, _factory)


def _register_remote(entry: Dict[str, Any]) -> None:
    md = _make_metadata(entry, requires_api=True)
    model_name = entry["model_name"]
    provider = entry["provider"]
    cls = {"openai": OpenAIEmbedding, "cohere": CohereEmbedding, "voyage": VoyageEmbedding}[provider]

    def _factory(_model_name=model_name, _md=md, _cls=cls, **params):
        return _cls(model_name=_model_name, metadata=_md, **params)

    embedding_registry.register(model_name, _factory)


for _entry in _LOCAL_MODELS:
    _register_local(_entry)

for _entry in _REMOTE_MODELS:
    _register_remote(_entry)
