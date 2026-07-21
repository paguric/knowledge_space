"""Test per le strategie di embedding (Step 6).

Copre:
- Registry: 12 modelli registrati con metadati completi.
- EmbeddingMetadata: dim, languages, max_context_tokens, license, requires_api.
- LocalEmbedding: mock di SentenceTransformer, device, vettori dim corretta.
- OpenAIEmbedding: mock del client, api_base, MissingAPIKeyError.
- CohereEmbedding: mock del client, MissingAPIKeyError.
- VoyageEmbedding: mock del client, MissingAPIKeyError.
- estimate_tokens + validate_chunk_context + ChunkTooLongError.
- Factory dal registry: istanziazione con parametri da BaseConfig.

I test di integrazione con API reali (Cohere, Voyage) sono in
``test_embedding_integration.py`` con marker ``@pytest.mark.api``.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from knowledge_base.strategies import embedding_registry
from knowledge_base.strategies.embedding import (
    ChunkTooLongError,
    CohereEmbedding,
    LocalEmbedding,
    MissingAPIKeyError,
    OpenAIEmbedding,
    VoyageEmbedding,
    estimate_tokens,
    validate_chunk_context,
)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


class TestEmbeddingRegistry:
    def test_twelve_models_registered(self):
        names = set(embedding_registry.list_names())
        assert len(names) == 12

    def test_all_local_models_present(self):
        names = set(embedding_registry.list_names())
        assert "sentence-transformers/all-mpnet-base-v2" in names
        assert "sentence-transformers/all-MiniLM-L6-v2" in names
        assert "Alibaba-NLP/gte-large-en-v1.5" in names
        assert "BAAI/bge-large-en-v1.5" in names
        assert "BAAI/bge-m3" in names
        assert "intfloat/multilingual-e5-small" in names
        assert "intfloat/multilingual-e5-large" in names

    def test_all_remote_models_present(self):
        names = set(embedding_registry.list_names())
        assert "openai/text-embedding-3-small" in names
        assert "openai/text-embedding-3-large" in names
        assert "cohere/embed-multilingual-v3.0" in names
        assert "voyage/voyage-3" in names
        assert "voyage/voyage-3-lite" in names

    def test_registry_unknown_raises(self):
        with pytest.raises(KeyError, match="non trovata"):
            embedding_registry.get("nonexistent/model")


# --------------------------------------------------------------------------- #
# Metadati discoverable
# --------------------------------------------------------------------------- #


class TestEmbeddingMetadata:
    @pytest.mark.parametrize(
        "model,dim,max_ctx,langs,requires_api,license",
        [
            ("sentence-transformers/all-mpnet-base-v2", 768, 384, ["en"], False, "Apache 2.0"),
            ("sentence-transformers/all-MiniLM-L6-v2", 384, 384, ["en"], False, "Apache 2.0"),
            ("Alibaba-NLP/gte-large-en-v1.5", 1024, 8192, ["en"], False, "Apache 2.0"),
            ("BAAI/bge-large-en-v1.5", 1024, 512, ["en"], False, "MIT"),
            ("BAAI/bge-m3", 1024, 8192, ["multilingual"], False, "MIT"),
            ("intfloat/multilingual-e5-small", 384, 512, ["multilingual"], False, "MIT"),
            ("intfloat/multilingual-e5-large", 1024, 512, ["multilingual"], False, "MIT"),
            ("openai/text-embedding-3-small", 1536, 8191, ["multilingual"], True, "Proprietaria"),
            ("openai/text-embedding-3-large", 3072, 8191, ["multilingual"], True, "Proprietaria"),
            ("cohere/embed-multilingual-v3.0", 1024, 512, ["multilingual"], True, "Proprietaria"),
            ("voyage/voyage-3", 1024, 32000, ["multilingual"], True, "Proprietaria"),
            ("voyage/voyage-3-lite", 1024, 32000, ["multilingual"], True, "Proprietaria"),
        ],
    )
    def test_metadata_complete(
        self, model, dim, max_ctx, langs, requires_api, license
    ):
        cls = embedding_registry.get(model)
        inst = cls()
        md = inst.metadata
        assert md.model_name == model
        assert md.dim == dim
        assert md.max_context_tokens == max_ctx
        assert md.languages == langs
        assert md.requires_api is requires_api
        assert md.license == license
        assert inst.name == model

    def test_local_models_have_requires_api_false(self):
        for name in embedding_registry.list_names():
            inst = embedding_registry.get(name)()
            if inst.metadata.requires_api is False:
                assert isinstance(inst, LocalEmbedding)

    def test_remote_models_have_requires_api_true(self):
        remote_names = [
            "openai/text-embedding-3-small",
            "openai/text-embedding-3-large",
            "cohere/embed-multilingual-v3.0",
            "voyage/voyage-3",
            "voyage/voyage-3-lite",
        ]
        for name in remote_names:
            inst = embedding_registry.get(name)()
            assert inst.metadata.requires_api is True


# --------------------------------------------------------------------------- #
# LocalEmbedding — mock di SentenceTransformer
# --------------------------------------------------------------------------- #


def _make_fake_st_model(dim: int):
    """Mock di SentenceTransformer che restituisce vettori deterministici."""
    fake_model = MagicMock()
    fake_model.encode.return_value = np.array(
        [[float(i + j) for j in range(dim)] for i in range(3)]
    )
    return fake_model


class TestLocalEmbedding:
    def test_embed_returns_vectors_of_correct_dim(self):
        cls = embedding_registry.get("sentence-transformers/all-mpnet-base-v2")
        inst = cls()
        dim = inst.metadata.dim
        fake_model = _make_fake_st_model(dim)
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=fake_model,
        ):
            vectors = inst.embed(["text one", "text two", "text three"])
        assert len(vectors) == 3
        assert all(len(v) == dim for v in vectors)

    def test_different_models_different_dims(self):
        """Modelli diversi → vettori di dimensionalità diverse."""
        dims = {}
        for name in [
            "sentence-transformers/all-mpnet-base-v2",  # 768
            "sentence-transformers/all-MiniLM-L6-v2",   # 384
            "Alibaba-NLP/gte-large-en-v1.5",            # 1024
        ]:
            cls = embedding_registry.get(name)
            inst = cls()
            dim = inst.metadata.dim
            fake_model = _make_fake_st_model(dim)
            with patch("sentence_transformers.SentenceTransformer", return_value=fake_model):
                vectors = inst.embed(["test"])
            dims[name] = len(vectors[0])
        assert len(set(dims.values())) == 3  # 3 dim diverse

    def test_device_passed_to_model(self):
        cls = embedding_registry.get("BAAI/bge-m3")
        inst = cls(device="cuda")
        fake_model = _make_fake_st_model(inst.metadata.dim)
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=fake_model,
        ) as mock_st:
            inst.embed(["text"])
        mock_st.assert_called_once()
        assert mock_st.call_args.kwargs.get("device") == "cuda"

    def test_model_loaded_once_and_cached(self):
        cls = embedding_registry.get("sentence-transformers/all-MiniLM-L6-v2")
        inst = cls()
        fake_model = _make_fake_st_model(inst.metadata.dim)
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=fake_model,
        ) as mock_st:
            inst.embed(["a"])
            inst.embed(["b"])
        mock_st.assert_called_once()  # cached, not reloaded


# --------------------------------------------------------------------------- #
# OpenAIEmbedding — mock del client
# --------------------------------------------------------------------------- #


def _make_fake_openai_response(dim: int, n: int):
    """Mock della response di OpenAI embeddings.create."""
    data = [MagicMock(embedding=[float(j) for j in range(dim)]) for _ in range(n)]
    return MagicMock(data=data)


class TestOpenAIEmbedding:
    def test_embed_returns_vectors(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        cls = embedding_registry.get("openai/text-embedding-3-small")
        inst = cls()
        dim = inst.metadata.dim
        fake_response = _make_fake_openai_response(dim, 2)
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = fake_response
        with patch("openai.OpenAI", return_value=fake_client):
            vectors = inst.embed(["hello", "world"])
        assert len(vectors) == 2
        assert all(len(v) == dim for v in vectors)
        fake_client.embeddings.create.assert_called_once()
        # model name senza prefisso provider
        assert fake_client.embeddings.create.call_args.kwargs["model"] == "text-embedding-3-small"

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cls = embedding_registry.get("openai/text-embedding-3-small")
        inst = cls()
        with pytest.raises(MissingAPIKeyError, match="OpenAI"):
            inst.embed(["text"])

    def test_api_base_passed_to_client(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        cls = embedding_registry.get("openai/text-embedding-3-small")
        inst = cls(api_base="http://localhost:11434/v1")
        fake_response = _make_fake_openai_response(inst.metadata.dim, 1)
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = fake_response
        with patch("openai.OpenAI", return_value=fake_client) as mock_openai:
            inst.embed(["text"])
        mock_openai.assert_called_once()
        assert mock_openai.call_args.kwargs["base_url"] == "http://localhost:11434/v1"

    def test_openai_base_url_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.example.com/v1")
        cls = embedding_registry.get("openai/text-embedding-3-small")
        inst = cls()
        fake_response = _make_fake_openai_response(inst.metadata.dim, 1)
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = fake_response
        with patch("openai.OpenAI", return_value=fake_client) as mock_openai:
            inst.embed(["text"])
        assert mock_openai.call_args.kwargs["base_url"] == "https://custom.example.com/v1"

    def test_large_model_has_dim_3072(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        cls = embedding_registry.get("openai/text-embedding-3-large")
        inst = cls()
        assert inst.metadata.dim == 3072


# --------------------------------------------------------------------------- #
# CohereEmbedding — mock del client
# --------------------------------------------------------------------------- #


def _make_fake_cohere_response(dim: int, n: int):
    """Mock della response di cohere ClientV2.embed."""
    resp = MagicMock()
    resp.embeddings.float = [[float(j) for j in range(dim)] for _ in range(n)]
    return resp


class TestCohereEmbedding:
    def test_embed_returns_vectors(self, monkeypatch):
        monkeypatch.setenv("COHERE_API_KEY", "test-key")
        cls = embedding_registry.get("cohere/embed-multilingual-v3.0")
        inst = cls()
        dim = inst.metadata.dim
        fake_response = _make_fake_cohere_response(dim, 2)
        fake_client = MagicMock()
        fake_client.embed.return_value = fake_response
        with patch("cohere.ClientV2", return_value=fake_client):
            vectors = inst.embed(["hello", "world"])
        assert len(vectors) == 2
        assert all(len(v) == dim for v in vectors)
        fake_client.embed.assert_called_once()
        kwargs = fake_client.embed.call_args.kwargs
        assert kwargs["model"] == "embed-multilingual-v3.0"
        assert kwargs["input_type"] == "search_document"

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        cls = embedding_registry.get("cohere/embed-multilingual-v3.0")
        inst = cls()
        with pytest.raises(MissingAPIKeyError, match="Cohere"):
            inst.embed(["text"])


# --------------------------------------------------------------------------- #
# VoyageEmbedding — mock del client
# --------------------------------------------------------------------------- #


def _make_fake_voyage_response(dim: int, n: int):
    """Mock della response di voyageai.Client.embed."""
    resp = MagicMock()
    resp.embeddings = [[float(j) for j in range(dim)] for _ in range(n)]
    return resp


class TestVoyageEmbedding:
    def test_embed_returns_vectors(self, monkeypatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
        cls = embedding_registry.get("voyage/voyage-3")
        inst = cls()
        dim = inst.metadata.dim
        fake_response = _make_fake_voyage_response(dim, 2)
        fake_client = MagicMock()
        fake_client.embed.return_value = fake_response
        with patch("voyageai.Client", return_value=fake_client):
            vectors = inst.embed(["hello", "world"])
        assert len(vectors) == 2
        assert all(len(v) == dim for v in vectors)
        fake_client.embed.assert_called_once()
        kwargs = fake_client.embed.call_args.kwargs
        assert kwargs["model"] == "voyage-3"
        assert kwargs["input_type"] == "document"

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        cls = embedding_registry.get("voyage/voyage-3")
        inst = cls()
        with pytest.raises(MissingAPIKeyError, match="Voyage"):
            inst.embed(["text"])

    def test_voyage_3_lite_same_dim(self, monkeypatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
        cls = embedding_registry.get("voyage/voyage-3-lite")
        inst = cls()
        assert inst.metadata.dim == 1024
        assert inst.metadata.max_context_tokens == 32000


# --------------------------------------------------------------------------- #
# Stima token + validazione contesto
# --------------------------------------------------------------------------- #


class TestEstimateTokens:
    def test_empty_string_returns_one(self):
        assert estimate_tokens("") == 1

    def test_short_string(self):
        assert estimate_tokens("hello") == 1  # 5 chars // 4 = 1

    def test_long_string(self):
        text = "a" * 100
        assert estimate_tokens(text) == 25  # 100 // 4

    def test_conservative_estimate(self):
        text = "word " * 20  # 100 chars
        assert estimate_tokens(text) == 25


class TestValidateChunkContext:
    def test_short_chunk_passes(self):
        validate_chunk_context(
            "short text",
            max_context_tokens=384,
            base_name="mybase",
            file_name="doc.pdf",
            chunk_index=0,
        )

    def test_long_chunk_raises(self):
        long_text = "a" * 2000  # 500 token stimati
        with pytest.raises(ChunkTooLongError, match="supera il limite") as exc_info:
            validate_chunk_context(
                long_text,
                max_context_tokens=384,
                base_name="mybase",
                file_name="doc.pdf",
                chunk_index=3,
            )
        assert exc_info.value.base_name == "mybase"
        assert exc_info.value.file_name == "doc.pdf"
        assert exc_info.value.chunk_index == 3
        assert exc_info.value.n_tokens == 500
        assert exc_info.value.max_tokens == 384

    def test_exact_boundary_passes(self):
        text = "a" * (384 * 4)  # 384 token
        validate_chunk_context(
            text,
            max_context_tokens=384,
            base_name="b",
            file_name="f",
            chunk_index=0,
        )

    def test_one_token_over_raises(self):
        text = "a" * (385 * 4)  # 385 token
        with pytest.raises(ChunkTooLongError):
            validate_chunk_context(
                text,
                max_context_tokens=384,
                base_name="b",
                file_name="f",
                chunk_index=0,
            )

    def test_voyage_long_context_allowed(self):
        """Voyage con 32k token permette chunk molto grandi."""
        text = "a" * (30000 * 4)  # 30000 token
        validate_chunk_context(
            text,
            max_context_tokens=32000,
            base_name="b",
            file_name="f",
            chunk_index=0,
        )


# --------------------------------------------------------------------------- #
# Factory dal registry — istanziazione con parametri da BaseConfig
# --------------------------------------------------------------------------- #


class TestRegistryFactory:
    def test_local_factory_with_device(self):
        cls = embedding_registry.get("BAAI/bge-m3")
        inst = cls(device="cpu")
        assert isinstance(inst, LocalEmbedding)
        assert inst.device == "cpu"
        assert inst.metadata.dim == 1024

    def test_openai_factory_with_api_base(self):
        cls = embedding_registry.get("openai/text-embedding-3-small")
        inst = cls(api_base="http://localhost:11434/v1")
        assert isinstance(inst, OpenAIEmbedding)
        assert inst.api_base == "http://localhost:11434/v1"

    def test_cohere_factory(self):
        cls = embedding_registry.get("cohere/embed-multilingual-v3.0")
        inst = cls()
        assert isinstance(inst, CohereEmbedding)
        assert inst.metadata.dim == 1024

    def test_voyage_factory(self):
        cls = embedding_registry.get("voyage/voyage-3")
        inst = cls()
        assert isinstance(inst, VoyageEmbedding)
        assert inst.metadata.dim == 1024

    def test_metadata_accessible_without_api_key(self):
        """I metadati sono accessibili anche senza API key (nessuna
        chiamata al client finché non si chiama embed())."""
        cls = embedding_registry.get("openai/text-embedding-3-large")
        inst = cls()
        assert inst.metadata.dim == 3072
        assert inst.metadata.requires_api is True
