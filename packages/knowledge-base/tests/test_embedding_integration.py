"""Test di integrazione con API embedding remote (Step 6).

Questi test effettuano **chiamate reali** alle API di Cohere e Voyage
usando le chiavi gratuite dei provider. Sono marcati con
``@pytest.mark.api`` e saltati automaticamente se le env var non sono
presenti o se i SDK non sono installati.

Per eseguirli:
    1. Installa i SDK remoti: ``uv sync --extra remote``
    2. Imposta le env var: ``COHERE_API_KEY``, ``VOYAGE_API_KEY``
    3. Esegui: ``pytest -m api``

OpenAI non è testato qui (nessuna API gratuita): la logica è coperta
dai test unitari con mock in ``test_embedding.py``.
"""

from __future__ import annotations

import os

import pytest

from knowledge_base.strategies import embedding_registry

# Skip tutto il modulo se i SDK non sono installati
cohere = pytest.importorskip("cohere", reason="SDK cohere non installato (uv sync --extra remote)")
voyageai = pytest.importorskip("voyageai", reason="SDK voyageai non installato (uv sync --extra remote)")


# --------------------------------------------------------------------------- #
# Cohere — embed-multilingual-v3.0
# --------------------------------------------------------------------------- #


@pytest.mark.api
@pytest.mark.skipif(
    not os.environ.get("COHERE_API_KEY"),
    reason="Richiede COHERE_API_KEY",
)
class TestCohereIntegration:
    def test_real_embed_returns_correct_dim(self):
        cls = embedding_registry.get("cohere/embed-multilingual-v3.0")
        inst = cls()
        vectors = inst.embed(["Hello world", "Ciao mondo"])
        assert len(vectors) == 2
        assert all(len(v) == inst.metadata.dim for v in vectors)
        assert all(isinstance(v, list) for v in vectors)

    def test_real_embed_italian_text(self):
        cls = embedding_registry.get("cohere/embed-multilingual-v3.0")
        inst = cls()
        vectors = inst.embed(["Il gatto è sul tappeto."])
        assert len(vectors) == 1
        assert len(vectors[0]) == inst.metadata.dim

    def test_real_embed_empty_list(self):
        cls = embedding_registry.get("cohere/embed-multilingual-v3.0")
        inst = cls()
        vectors = inst.embed([])
        assert vectors == []


# --------------------------------------------------------------------------- #
# Voyage — voyage-3
# --------------------------------------------------------------------------- #


@pytest.mark.api
@pytest.mark.skipif(
    not os.environ.get("VOYAGE_API_KEY"),
    reason="Richiede VOYAGE_API_KEY",
)
class TestVoyageIntegration:
    def test_real_embed_returns_correct_dim(self):
        cls = embedding_registry.get("voyage/voyage-3")
        inst = cls()
        vectors = inst.embed(["Hello world", "Ciao mondo"])
        assert len(vectors) == 2
        assert all(len(v) == inst.metadata.dim for v in vectors)
        assert all(isinstance(v, list) for v in vectors)

    def test_real_embed_italian_text(self):
        cls = embedding_registry.get("voyage/voyage-3")
        inst = cls()
        vectors = inst.embed(["Il documento contiene informazioni importanti."])
        assert len(vectors) == 1
        assert len(vectors[0]) == inst.metadata.dim

    def test_real_embed_long_context(self):
        """Voyage supporta 32k token: un testo lungo non dovrebbe fallire."""
        cls = embedding_registry.get("voyage/voyage-3")
        inst = cls()
        long_text = "This is a test sentence. " * 500  # ~2500 token
        vectors = inst.embed([long_text])
        assert len(vectors) == 1
        assert len(vectors[0]) == inst.metadata.dim
