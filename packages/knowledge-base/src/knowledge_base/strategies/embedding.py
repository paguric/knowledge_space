"""Strategie di embedding registrate nel registry.

Step 6 implementerà la logica completa di ciascuna strategia; qui si
registrano gli stub minimi affinché il registry sia popolato all'avvio.
"""

from __future__ import annotations

from typing import List

from knowledge_base.strategies import EmbeddingMetadata, EmbeddingStrategy, embedding_registry


class SentenceTransformersEmbedding:
    """Embedding locale via sentence-transformers (HuggingFace)."""

    def __init__(self, model_name: str, **params) -> None:
        self.model_name = model_name
        self.name = model_name
        self.params = params
        self.metadata = EmbeddingMetadata(
            model_name=model_name,
            languages=["en"],
            dim=768,
            max_context_tokens=384,
            license="Apache 2.0",
            requires_api=False,
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError("Step 6 — non ancora implementato")


# Registrazione all'avvio — modelli locali
def _register_local(model_name: str, dim: int, max_ctx: int, languages: List[str]) -> None:
    """Factory che registra un modello locale con metadati specifici."""

    class _LocalEmbedding(SentenceTransformersEmbedding):
        def __init__(self, **params) -> None:
            super().__init__(model_name=model_name, **params)
            self.metadata = EmbeddingMetadata(
                model_name=model_name,
                languages=languages,
                dim=dim,
                max_context_tokens=max_ctx,
                license="Apache 2.0",
                requires_api=False,
            )

    _LocalEmbedding.__name__ = model_name.replace("/", "_").replace("-", "_")
    embedding_registry.register(model_name, _LocalEmbedding)


_register_local("sentence-transformers/all-mpnet-base-v2", dim=768, max_ctx=384, languages=["en"])
_register_local("sentence-transformers/all-MiniLM-L6-v2", dim=384, max_ctx=384, languages=["en"])
_register_local("Alibaba-NLP/gte-large-en-v1.5", dim=1024, max_ctx=8192, languages=["en"])
_register_local("BAAI/bge-large-en-v1.5", dim=1024, max_ctx=512, languages=["en"])
_register_local("BAAI/bge-m3", dim=1024, max_ctx=8192, languages=["multilingual"])
_register_local("intfloat/multilingual-e5-small", dim=384, max_ctx=512, languages=["multilingual"])
_register_local("intfloat/multilingual-e5-large", dim=1024, max_ctx=512, languages=["multilingual"])


# Modelli remoti (stub — la logica API arriverà in Step 6)
class RemoteEmbeddingStub:
    """Stub per modelli remoti (OpenAI, Cohere, Voyage)."""

    def __init__(self, model_name: str, **params) -> None:
        self.model_name = model_name
        self.name = model_name
        self.params = params
        self.metadata = EmbeddingMetadata(
            model_name=model_name,
            languages=["multilingual"],
            dim=1536,
            max_context_tokens=8191,
            license="Proprietaria",
            requires_api=True,
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError("Step 6 — modelli remoti non ancora implementati")


embedding_registry.register("openai/text-embedding-3-small", lambda **p: RemoteEmbeddingStub("openai/text-embedding-3-small", **p))
embedding_registry.register("openai/text-embedding-3-large", lambda **p: RemoteEmbeddingStub("openai/text-embedding-3-large", **p))
embedding_registry.register("cohere/embed-multilingual-v3.0", lambda **p: RemoteEmbeddingStub("cohere/embed-multilingual-v3.0", **p))
embedding_registry.register("voyage/voyage-3", lambda **p: RemoteEmbeddingStub("voyage/voyage-3", **p))
embedding_registry.register("voyage/voyage-3-lite", lambda **p: RemoteEmbeddingStub("voyage/voyage-3-lite", **p))
