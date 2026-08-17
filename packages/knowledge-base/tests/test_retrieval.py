"""Test per la pipeline di retrieval (Step 8 — Fase 1B).

Copre:
- Pre-retrieval: identity, multi_query, step_back, least_to_most.
- Retrieval: dense (mock collection), sparse (mock BM25), hybrid (RRF, weighted_sum).
- Post-retrieval: identity, relevance, mmr, llm reranker, llm_chain_extract.
- SearchService: orchestrazione, fallback LLM mancante, configurazione TOML.
- BaseConfig: sezioni [pre_retrieval], [retrieval], [post_retrieval].
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from knowledge_base.base_config import (
    BaseConfig,
    PostRetrievalConfig,
    PreRetrievalConfig,
    PreRetrievalStageConfig,
    RetrievalConfig,
)
from knowledge_base.strategies import (
    RetrievalResult,
    llm_registry,
    post_retrieval_registry,
    pre_retrieval_registry,
    retrieval_registry,
)
from knowledge_base.strategies.llm import MockEchoLLM, MockFixedLLM, clear_llm_cache


# --------------------------------------------------------------------------- #
# Helpers e fixture
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _clear_llm_cache():
    clear_llm_cache()
    yield
    clear_llm_cache()


def _make_result(chunk_id: str, text: str, score: float) -> RetrievalResult:
    return RetrievalResult(chunk_id=chunk_id, text=text, score=score)


def _make_results(n: int = 5) -> List[RetrievalResult]:
    return [
        _make_result(f"chunk_{i}", f"Testo del chunk {i}", 1.0 - i * 0.1)
        for i in range(n)
    ]


class MockCollection:
    """Mock per una collection Chroma."""

    def __init__(self, docs: Optional[Dict[str, str]] = None, dim: int = 384) -> None:
        self._docs = docs or {}
        self._dim = dim

    def query(self, query_embeddings, n_results=10, include=None):
        ids = list(self._docs.keys())[:n_results]
        documents = [self._docs[cid] for cid in ids]
        # Simula distanze: più basso = più simile
        distances = [0.1 * i for i in range(len(ids))]
        metadatas = [{"base_name": "test"} for _ in ids]
        return {
            "ids": [ids],
            "documents": [documents],
            "distances": [distances],
            "metadatas": [metadatas],
        }

    def get(self, include=None):
        return {
            "ids": list(self._docs.keys()),
            "documents": list(self._docs.values()),
        }


class MockEmbedder:
    """Mock per EmbeddingStrategy."""

    def __init__(self, dim: int = 384) -> None:
        self.name = "mock/embedder"
        self.metadata = MagicMock()
        self.metadata.dim = dim
        self.metadata.max_context_tokens = 512
        self._dim = dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        # Restituisce vettori deterministici basati sul testo
        results = []
        for text in texts:
            # Vettore semplice basato sulla lunghezza del testo
            vec = [float(len(text) % 100) / 100.0] * self._dim
            results.append(vec)
        return results


# --------------------------------------------------------------------------- #
# Pre-retrieval — Registry
# --------------------------------------------------------------------------- #


class TestPreRetrievalRegistry:
    def test_all_strategies_registered(self):
        names = set(pre_retrieval_registry.list_names())
        assert names == {"identity", "multi_query", "step_back", "least_to_most"}

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError, match="non trovata"):
            pre_retrieval_registry.get("sconosciuta")


# --------------------------------------------------------------------------- #
# Pre-retrieval — identity
# --------------------------------------------------------------------------- #


class TestIdentityPreRetrieval:
    def test_expand_returns_queries_unchanged(self):
        from knowledge_base.strategies.pre_retrieval import IdentityPreRetrieval

        strategy = IdentityPreRetrieval()
        queries = ["domanda 1", "domanda 2"]
        result = strategy.expand(queries)
        assert result == ["domanda 1", "domanda 2"]

    def test_expand_returns_copy_not_reference(self):
        from knowledge_base.strategies.pre_retrieval import IdentityPreRetrieval

        strategy = IdentityPreRetrieval()
        queries = ["domanda"]
        result = strategy.expand(queries)
        result.append("nuova")
        assert queries == ["domanda"]  # originale invariato

    def test_expand_empty_list(self):
        from knowledge_base.strategies.pre_retrieval import IdentityPreRetrieval

        strategy = IdentityPreRetrieval()
        assert strategy.expand([]) == []

    def test_metadata(self):
        from knowledge_base.strategies.pre_retrieval import IdentityPreRetrieval

        strategy = IdentityPreRetrieval()
        assert strategy.name == "identity"
        assert strategy.requires_llm is False


# --------------------------------------------------------------------------- #
# Pre-retrieval — multi_query
# --------------------------------------------------------------------------- #


class TestMultiQueryPreRetrieval:
    def test_expand_with_echo_llm(self):
        from knowledge_base.strategies.pre_retrieval import MultiQueryPreRetrieval

        llm = MockEchoLLM()
        strategy = MultiQueryPreRetrieval(llm=llm, n=2)
        queries = ["Cos'è il machine learning?"]
        result = strategy.expand(queries)
        # Echo LLM restituisce il prompt, quindi le varianti saranno
        # estratte dal prompt stesso
        assert len(result) >= 1  # almeno la query originale
        assert result[0] == "Cos'è il machine learning?"

    def test_expand_preserves_original(self):
        from knowledge_base.strategies.pre_retrieval import MultiQueryPreRetrieval

        llm = MockFixedLLM()
        strategy = MultiQueryPreRetrieval(llm=llm, n=3)
        result = strategy.expand(["domanda originale"])
        assert result[0] == "domanda originale"

    def test_metadata(self):
        from knowledge_base.strategies.pre_retrieval import MultiQueryPreRetrieval

        llm = MockFixedLLM()
        strategy = MultiQueryPreRetrieval(llm=llm)
        assert strategy.name == "multi_query"
        assert strategy.requires_llm is True

    def test_expand_multiple_queries(self):
        from knowledge_base.strategies.pre_retrieval import MultiQueryPreRetrieval

        llm = MockFixedLLM()
        strategy = MultiQueryPreRetrieval(llm=llm, n=2)
        result = strategy.expand(["q1", "q2"])
        # Ogni query produce originale + varianti
        assert result[0] == "q1"
        assert "q2" in result


# --------------------------------------------------------------------------- #
# Pre-retrieval — step_back
# --------------------------------------------------------------------------- #


class TestStepBackPreRetrieval:
    def test_expand_with_echo_llm(self):
        from knowledge_base.strategies.pre_retrieval import StepBackPreRetrieval

        llm = MockEchoLLM()
        strategy = StepBackPreRetrieval(llm=llm)
        result = strategy.expand(["Qual è la capitale della Francia?"])
        # Dovrebbe contenere la query originale + una domanda astratta
        assert len(result) >= 2
        assert result[0] == "Qual è la capitale della Francia?"

    def test_metadata(self):
        from knowledge_base.strategies.pre_retrieval import StepBackPreRetrieval

        llm = MockFixedLLM()
        strategy = StepBackPreRetrieval(llm=llm)
        assert strategy.name == "step_back"
        assert strategy.requires_llm is True


# --------------------------------------------------------------------------- #
# Pre-retrieval — least_to_most
# --------------------------------------------------------------------------- #


class TestLeastToMostPreRetrieval:
    def test_expand_with_echo_llm(self):
        from knowledge_base.strategies.pre_retrieval import LeastToMostPreRetrieval

        llm = MockEchoLLM()
        strategy = LeastToMostPreRetrieval(llm=llm, max_subquestions=3)
        result = strategy.expand(["Come funziona un motore?"])
        # Dovrebbe contenere la query originale + sotto-domande
        assert len(result) >= 1
        assert result[0] == "Come funziona un motore?"

    def test_metadata(self):
        from knowledge_base.strategies.pre_retrieval import LeastToMostPreRetrieval

        llm = MockFixedLLM()
        strategy = LeastToMostPreRetrieval(llm=llm)
        assert strategy.name == "least_to_most"
        assert strategy.requires_llm is True


# --------------------------------------------------------------------------- #
# Pre-retrieval — _parse_lines helper
# --------------------------------------------------------------------------- #


class TestParseLines:
    def test_removes_numbering(self):
        from knowledge_base.strategies.pre_retrieval import _parse_lines

        text = "1. Prima domanda\n2. Seconda domanda\n3. Terza domanda"
        result = _parse_lines(text, max_lines=3)
        assert result == ["Prima domanda", "Seconda domanda", "Terza domanda"]

    def test_limits_lines(self):
        from knowledge_base.strategies.pre_retrieval import _parse_lines

        text = "a\nb\nc\nd\ne"
        result = _parse_lines(text, max_lines=2)
        assert len(result) == 2

    def test_removes_empty_lines(self):
        from knowledge_base.strategies.pre_retrieval import _parse_lines

        text = "prima\n\nseconda\n\n"
        result = _parse_lines(text)
        assert result == ["prima", "seconda"]


# --------------------------------------------------------------------------- #
# Retrieval — Registry
# --------------------------------------------------------------------------- #


class TestRetrievalRegistry:
    def test_all_strategies_registered(self):
        names = set(retrieval_registry.list_names())
        assert names == {"dense", "sparse", "hybrid"}

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError, match="non trovata"):
            retrieval_registry.get("sconosciuta")


# --------------------------------------------------------------------------- #
# Retrieval — Dense
# --------------------------------------------------------------------------- #


class TestDenseRetrieval:
    def test_search_returns_results(self):
        from knowledge_base.strategies.retrieval import DenseRetrieval

        docs = {"c1": "testo 1", "c2": "testo 2", "c3": "testo 3"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        strategy = DenseRetrieval(
            embedder=embedder,
            collection_factory=lambda: collection,
        )
        results = strategy.search("test query", top_k=3)
        assert len(results) == 3
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_search_with_query_embedding_skips_embed(self):
        """bug-026: con query_embedding fornito non si ri-embeda la query."""
        from knowledge_base.strategies.retrieval import DenseRetrieval

        docs = {"c1": "testo 1"}
        collection = MockCollection(docs=docs)

        class CountingEmbedder(MockEmbedder):
            def __init__(self):
                super().__init__()
                self.embed_calls = 0

            def embed(self, texts):
                self.embed_calls += 1
                return super().embed(texts)

        embedder = CountingEmbedder()
        strategy = DenseRetrieval(
            embedder=embedder,
            collection_factory=lambda: collection,
        )
        results = strategy.search(
            "test query", top_k=3, query_embedding=[0.1, 0.2, 0.3]
        )
        assert len(results) == 1
        assert embedder.embed_calls == 0

    def test_search_respects_top_k(self):
        from knowledge_base.strategies.retrieval import DenseRetrieval

        docs = {f"c{i}": f"testo {i}" for i in range(10)}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        strategy = DenseRetrieval(
            embedder=embedder,
            collection_factory=lambda: collection,
        )
        results = strategy.search("test", top_k=2)
        assert len(results) == 2

    def test_search_empty_collection(self):
        from knowledge_base.strategies.retrieval import DenseRetrieval

        collection = MockCollection(docs={})
        embedder = MockEmbedder()

        strategy = DenseRetrieval(
            embedder=embedder,
            collection_factory=lambda: collection,
        )
        results = strategy.search("test", top_k=5)
        assert results == []

    def test_parse_chroma_results_empty(self):
        from knowledge_base.strategies.retrieval import DenseRetrieval

        assert DenseRetrieval._parse_chroma_results({}) == []
        assert DenseRetrieval._parse_chroma_results({"ids": []}) == []

    def test_parse_chroma_results_normalizes_scores(self):
        from knowledge_base.strategies.retrieval import DenseRetrieval

        results = {
            "ids": [["c1"]],
            "documents": [["text"]],
            "distances": [[0.5]],
            "metadatas": [[{"key": "value"}]],
        }
        parsed = DenseRetrieval._parse_chroma_results(results)
        assert len(parsed) == 1
        # score = 1 - 0.5/2 = 0.75
        assert parsed[0].score == pytest.approx(0.75)
        assert parsed[0].chunk_id == "c1"
        assert parsed[0].text == "text"


# --------------------------------------------------------------------------- #
# Retrieval — Sparse
# --------------------------------------------------------------------------- #


class TestSparseRetrieval:
    def test_search_returns_results(self):
        from knowledge_base.strategies.retrieval import SparseRetrieval

        docs = {"c1": "machine learning algoritmo", "c2": "rete neurale profonda"}
        collection = MockCollection(docs=docs)

        strategy = SparseRetrieval(collection_factory=lambda: collection)
        results = strategy.search("machine learning", top_k=2)
        assert len(results) > 0
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_search_empty_collection(self):
        from knowledge_base.strategies.retrieval import SparseRetrieval

        collection = MockCollection(docs={})
        strategy = SparseRetrieval(collection_factory=lambda: collection)
        results = strategy.search("test", top_k=5)
        assert results == []

    def test_search_normalizes_scores(self):
        from knowledge_base.strategies.retrieval import SparseRetrieval

        docs = {"c1": "testo rilevante"}
        collection = MockCollection(docs=docs)
        strategy = SparseRetrieval(collection_factory=lambda: collection)
        results = strategy.search("testo", top_k=1)
        assert len(results) == 1
        assert 0 <= results[0].score <= 1.0


# --------------------------------------------------------------------------- #
# Retrieval — Hybrid (RRF e weighted_sum)
# --------------------------------------------------------------------------- #


class TestHybridRetrieval:
    def test_search_rrf_fusion(self):
        from knowledge_base.strategies.retrieval import (
            DenseRetrieval,
            HybridRetrieval,
            SparseRetrieval,
        )

        docs = {"c1": "testo 1", "c2": "testo 2"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        dense = DenseRetrieval(
            embedder=embedder,
            collection_factory=lambda: collection,
        )
        sparse = SparseRetrieval(collection_factory=lambda: collection)
        hybrid = HybridRetrieval(dense=dense, sparse=sparse, fusion="rrf")

        results = hybrid.search("test", top_k=2)
        assert len(results) > 0
        assert all(r.metadata.get("fusion_method") == "rrf" for r in results)

    def test_search_weighted_sum_fusion(self):
        from knowledge_base.strategies.retrieval import (
            DenseRetrieval,
            HybridRetrieval,
            SparseRetrieval,
        )

        docs = {"c1": "testo 1", "c2": "testo 2"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        dense = DenseRetrieval(
            embedder=embedder,
            collection_factory=lambda: collection,
        )
        sparse = SparseRetrieval(collection_factory=lambda: collection)
        hybrid = HybridRetrieval(
            dense=dense,
            sparse=sparse,
            fusion="weighted_sum",
            dense_weight=0.6,
            sparse_weight=0.4,
        )

        results = hybrid.search("test", top_k=2)
        assert len(results) > 0
        assert all(
            r.metadata.get("fusion_method") == "weighted_sum" for r in results
        )


# --------------------------------------------------------------------------- #
# Fusion helpers
# --------------------------------------------------------------------------- #


class TestFusionHelpers:
    def test_rrf_fusion_combines_results(self):
        from knowledge_base.strategies.retrieval import _rrf_fusion

        dense = [_make_result("c1", "t1", 0.9), _make_result("c2", "t2", 0.8)]
        sparse = [_make_result("c2", "t2", 0.7), _make_result("c3", "t3", 0.6)]

        fused = _rrf_fusion(dense, sparse, k=60)
        chunk_ids = [r.chunk_id for r in fused]
        assert "c1" in chunk_ids
        assert "c2" in chunk_ids
        assert "c3" in chunk_ids
        # c2 dovrebbe avere lo score più alto (presente in entrambe)
        assert fused[0].chunk_id == "c2"

    def test_weighted_sum_fusion(self):
        from knowledge_base.strategies.retrieval import _weighted_sum_fusion

        dense = [_make_result("c1", "t1", 0.9)]
        sparse = [_make_result("c1", "t1", 0.8)]

        fused = _weighted_sum_fusion(dense, sparse, dense_weight=0.7, sparse_weight=0.3)
        assert len(fused) == 1
        expected = 0.9 * 0.7 + 0.8 * 0.3
        assert fused[0].score == pytest.approx(expected)

    def test_rrf_empty_lists(self):
        from knowledge_base.strategies.retrieval import _rrf_fusion

        assert _rrf_fusion([], []) == []

    def test_weighted_sum_empty_lists(self):
        from knowledge_base.strategies.retrieval import _weighted_sum_fusion

        assert _weighted_sum_fusion([], []) == []


# --------------------------------------------------------------------------- #
# Post-retrieval — Registry
# --------------------------------------------------------------------------- #


class TestPostRetrievalRegistry:
    def test_all_strategies_registered(self):
        names = set(post_retrieval_registry.list_names())
        assert names == {
            "identity",
            "relevance",
            "mmr",
            "cross_encoder",
            "llm",
            "llm_chain_extract",
            "selective_context",
        }

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError, match="non trovata"):
            post_retrieval_registry.get("sconosciuta")


# --------------------------------------------------------------------------- #
# Post-retrieval — identity
# --------------------------------------------------------------------------- #


class TestIdentityPostRetrieval:
    def test_rerank_returns_results_unchanged(self):
        from knowledge_base.strategies.post_retrieval import IdentityPostRetrieval

        strategy = IdentityPostRetrieval()
        results = _make_results(5)
        reranked = strategy.rerank("query", results, top_k=3)
        assert len(reranked) == 3
        assert reranked == results[:3]

    def test_rerank_empty_list(self):
        from knowledge_base.strategies.post_retrieval import IdentityPostRetrieval

        strategy = IdentityPostRetrieval()
        assert strategy.rerank("query", [], top_k=5) == []

    def test_metadata(self):
        from knowledge_base.strategies.post_retrieval import IdentityPostRetrieval

        strategy = IdentityPostRetrieval()
        assert strategy.name == "identity"
        assert strategy.requires_llm is False
        assert strategy.requires_model is False


# --------------------------------------------------------------------------- #
# Post-retrieval — relevance
# --------------------------------------------------------------------------- #


class TestRelevancePostRetrieval:
    def test_filters_below_threshold(self):
        from knowledge_base.strategies.post_retrieval import RelevancePostRetrieval

        strategy = RelevancePostRetrieval(threshold=0.5)
        results = [
            _make_result("c1", "t1", 0.9),
            _make_result("c2", "t2", 0.3),  # sotto soglia
            _make_result("c3", "t3", 0.6),
        ]
        reranked = strategy.rerank("query", results, top_k=10)
        assert len(reranked) == 2
        assert all(r.score >= 0.5 for r in reranked)

    def test_respects_top_k(self):
        from knowledge_base.strategies.post_retrieval import RelevancePostRetrieval

        strategy = RelevancePostRetrieval(threshold=0.0)
        results = _make_results(5)
        reranked = strategy.rerank("query", results, top_k=2)
        assert len(reranked) == 2

    def test_default_threshold(self):
        from knowledge_base.strategies.post_retrieval import RelevancePostRetrieval

        strategy = RelevancePostRetrieval()
        assert strategy.threshold == 0.3


# --------------------------------------------------------------------------- #
# Post-retrieval — mmr
# --------------------------------------------------------------------------- #


class TestMMRPostRetrieval:
    def test_selects_diverse_results(self):
        from knowledge_base.strategies.post_retrieval import MMRPostRetrieval

        embedder = MockEmbedder()
        strategy = MMRPostRetrieval(embedder=embedder, lambda_param=0.5)
        results = _make_results(5)
        reranked = strategy.rerank("query", results, top_k=3)
        assert len(reranked) == 3

    def test_without_embedder_returns_top_k(self):
        from knowledge_base.strategies.post_retrieval import MMRPostRetrieval

        strategy = MMRPostRetrieval(embedder=None, lambda_param=0.5)
        results = _make_results(5)
        reranked = strategy.rerank("query", results, top_k=3)
        assert len(reranked) == 3
        assert reranked == results[:3]

    def test_lambda_1_is_identity(self):
        from knowledge_base.strategies.post_retrieval import MMRPostRetrieval

        embedder = MockEmbedder()
        strategy = MMRPostRetrieval(embedder=embedder, lambda_param=1.0)
        results = _make_results(5)
        reranked = strategy.rerank("query", results, top_k=3)
        assert len(reranked) == 3
        # Con lambda=1, dovrebbe selezionare per puro score
        assert reranked[0].score >= reranked[1].score

    def test_fewer_results_than_top_k(self):
        from knowledge_base.strategies.post_retrieval import MMRPostRetrieval

        embedder = MockEmbedder()
        strategy = MMRPostRetrieval(embedder=embedder)
        results = _make_results(2)
        reranked = strategy.rerank("query", results, top_k=5)
        assert len(reranked) == 2

    def test_empty_results(self):
        from knowledge_base.strategies.post_retrieval import MMRPostRetrieval

        embedder = MockEmbedder()
        strategy = MMRPostRetrieval(embedder=embedder)
        assert strategy.rerank("query", [], top_k=5) == []


# --------------------------------------------------------------------------- #
# Post-retrieval — llm (reranker)
# --------------------------------------------------------------------------- #


class TestLLMPostRetrieval:
    def test_rerank_with_fixed_llm(self):
        from knowledge_base.strategies.post_retrieval import LLMPostRetrieval

        llm = MockFixedLLM()
        strategy = LLMPostRetrieval(llm=llm)
        results = _make_results(3)
        reranked = strategy.rerank("query", results, top_k=3)
        assert len(reranked) == 3
        # MockFixedLLM restituisce "Risposta mock" che non è un numero → default 5.0
        assert all(r.score == pytest.approx(0.5) for r in reranked)

    def test_rerank_empty_results(self):
        from knowledge_base.strategies.post_retrieval import LLMPostRetrieval

        llm = MockFixedLLM()
        strategy = LLMPostRetrieval(llm=llm)
        assert strategy.rerank("query", [], top_k=5) == []

    def test_metadata(self):
        from knowledge_base.strategies.post_retrieval import LLMPostRetrieval

        llm = MockFixedLLM()
        strategy = LLMPostRetrieval(llm=llm)
        assert strategy.name == "llm"
        assert strategy.requires_llm is True


# --------------------------------------------------------------------------- #
# Post-retrieval — llm_chain_extract
# --------------------------------------------------------------------------- #


class TestLLMChainExtractPostRetrieval:
    def test_compress_results(self):
        from knowledge_base.strategies.post_retrieval import (
            LLMChainExtractPostRetrieval,
        )

        llm = MockEchoLLM()
        strategy = LLMChainExtractPostRetrieval(llm=llm)
        results = _make_results(3)
        reranked = strategy.rerank("query", results, top_k=3)
        assert len(reranked) <= 3
        if reranked:
            assert all(r.metadata.get("compressed") is True for r in reranked)

    def test_empty_results(self):
        from knowledge_base.strategies.post_retrieval import (
            LLMChainExtractPostRetrieval,
        )

        llm = MockFixedLLM()
        strategy = LLMChainExtractPostRetrieval(llm=llm)
        assert strategy.rerank("query", [], top_k=5) == []

    def test_metadata(self):
        from knowledge_base.strategies.post_retrieval import (
            LLMChainExtractPostRetrieval,
        )

        llm = MockFixedLLM()
        strategy = LLMChainExtractPostRetrieval(llm=llm)
        assert strategy.name == "llm_chain_extract"
        assert strategy.requires_llm is True


# --------------------------------------------------------------------------- #
# Post-retrieval — selective_context
# --------------------------------------------------------------------------- #


class TestSelectiveContextPostRetrieval:
    def test_compress_results(self):
        from knowledge_base.strategies.post_retrieval import (
            SelectiveContextPostRetrieval,
        )

        llm = MockEchoLLM()
        strategy = SelectiveContextPostRetrieval(
            llm=llm, compression_ratio=0.5
        )
        results = _make_results(2)
        reranked = strategy.rerank("query", results, top_k=2)
        assert len(reranked) <= 2

    def test_metadata(self):
        from knowledge_base.strategies.post_retrieval import (
            SelectiveContextPostRetrieval,
        )

        llm = MockFixedLLM()
        strategy = SelectiveContextPostRetrieval(llm=llm)
        assert strategy.name == "selective_context"
        assert strategy.requires_llm is True


# --------------------------------------------------------------------------- #
# Post-retrieval — cosine_similarity helper
# --------------------------------------------------------------------------- #


class TestCosineSimilarity:
    def test_identical_vectors(self):
        from knowledge_base.strategies.post_retrieval import _cosine_similarity

        assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        from knowledge_base.strategies.post_retrieval import _cosine_similarity

        assert _cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_zero_vector(self):
        from knowledge_base.strategies.post_retrieval import _cosine_similarity

        assert _cosine_similarity([0, 0], [1, 0]) == 0.0


# --------------------------------------------------------------------------- #
# RetrievalResult
# --------------------------------------------------------------------------- #


class TestRetrievalResult:
    def test_creation(self):
        r = RetrievalResult(chunk_id="c1", text="testo", score=0.9)
        assert r.chunk_id == "c1"
        assert r.text == "testo"
        assert r.score == 0.9
        assert r.metadata == {}

    def test_with_metadata(self):
        r = RetrievalResult(
            chunk_id="c1", text="testo", score=0.5, metadata={"key": "val"}
        )
        assert r.metadata == {"key": "val"}

    def test_repr(self):
        r = RetrievalResult(chunk_id="c1", text="testo lungo " * 10, score=0.1234)
        repr_str = repr(r)
        assert "c1" in repr_str
        assert "0.1234" in repr_str

    def test_eq(self):
        r1 = RetrievalResult(chunk_id="c1", text="a", score=0.9)
        r2 = RetrievalResult(chunk_id="c1", text="b", score=0.9)
        r3 = RetrievalResult(chunk_id="c2", text="a", score=0.9)
        assert r1 == r2  # same chunk_id + score
        assert r1 != r3

    def test_hash(self):
        r1 = RetrievalResult(chunk_id="c1", text="a", score=0.9)
        r2 = RetrievalResult(chunk_id="c1", text="b", score=0.9)
        assert hash(r1) == hash(r2)
        assert len({r1, r2}) == 1


# --------------------------------------------------------------------------- #
# SearchService — orchestratore
# --------------------------------------------------------------------------- #


class TestSearchService:
    def test_search_identity_pipeline(self):
        """Pipeline identity → dense → identity."""
        from knowledge_base.search_service import SearchService

        docs = {"c1": "testo 1", "c2": "testo 2"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        service = SearchService(
            llm_factory=None,
            embedder_factory=lambda model: embedder,
            collection_factory=lambda: collection,
        )
        results = service.search("test query", top_k=2)
        assert len(results) <= 2

    def test_embedder_factory_called_once_per_model(self):
        """bug-026: l'embedder si costruisce UNA volta per modello,
        anche cercando in più basi (collection diverse)."""
        from knowledge_base.search_service import SearchService

        calls = []

        def factory(model_name):
            calls.append(model_name)
            return MockEmbedder()

        service = SearchService(embedder_factory=factory)
        for i in range(3):
            collection = MockCollection(docs={"c1": f"testo {i}"})
            service.search(
                "query",
                collection_factory=lambda c=collection: c,
            )
        assert len(calls) == 1

    def test_query_embedded_once_across_bases(self):
        """bug-026: il vettore della query si calcola una volta per
        (modello, query), non per base."""
        from knowledge_base.search_service import SearchService

        class CountingEmbedder(MockEmbedder):
            def __init__(self):
                super().__init__()
                self.embed_calls = 0

            def embed(self, texts):
                self.embed_calls += 1
                return super().embed(texts)

        embedder = CountingEmbedder()
        service = SearchService(embedder_factory=lambda m: embedder)
        for i in range(3):
            collection = MockCollection(docs={"c1": f"testo {i}"})
            service.search(
                "stessa query",
                collection_factory=lambda c=collection: c,
            )
        assert embedder.embed_calls == 1

    def test_search_with_pre_retrieval(self):
        """Pre-retrieval identity non cambia la query."""
        from knowledge_base.search_service import (
            SearchConfig,
            SearchService,
        )

        docs = {"c1": "testo 1"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        service = SearchService(
            embedder_factory=lambda model: embedder,
            collection_factory=lambda: collection,
        )
        config = SearchConfig()
        results = service.search("test", config=config, top_k=1)
        assert len(results) <= 1

    def test_search_with_post_retrieval_relevance(self):
        """Post-retrieval relevance filtra per soglia."""
        from knowledge_base.search_service import (
            PostRetrievalConfig,
            SearchConfig,
            SearchService,
        )

        docs = {"c1": "testo molto rilevante"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        service = SearchService(
            embedder_factory=lambda model: embedder,
            collection_factory=lambda: collection,
        )
        config = SearchConfig(
            post_retrieval=PostRetrievalConfig(
                method="relevance", params={"threshold": 0.0}
            )
        )
        results = service.search("test", config=config, top_k=5)
        assert isinstance(results, list)

    def test_search_with_mmr_post_retrieval(self):
        """Post-retrieval MMR seleziona risultati diversificati."""
        from knowledge_base.search_service import (
            PostRetrievalConfig,
            SearchConfig,
            SearchService,
        )

        docs = {f"c{i}": f"testo {i}" for i in range(5)}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        service = SearchService(
            embedder_factory=lambda model: embedder,
            collection_factory=lambda: collection,
        )
        config = SearchConfig(
            post_retrieval=PostRetrievalConfig(
                method="mmr", params={"lambda_param": 0.5}
            )
        )
        results = service.search("test", config=config, top_k=3)
        assert len(results) <= 3

    def test_fallback_when_llm_missing(self):
        """Fallback a identity se LLM non è configurato."""
        from knowledge_base.search_service import (
            PreRetrievalStageConfig,
            SearchConfig,
            SearchService,
        )
        import logging

        docs = {"c1": "testo"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        # Nessuna llm_factory → fallback
        service = SearchService(
            llm_factory=None,
            embedder_factory=lambda model: embedder,
            collection_factory=lambda: collection,
        )
        config = SearchConfig(
            pre_retrieval=[PreRetrievalStageConfig(method="multi_query")]
        )

        # Non dovrebbe sollevare eccezioni, solo warn
        with patch("knowledge_base.search_service.logger") as mock_logger:
            results = service.search("test", config=config, top_k=5)
            mock_logger.warning.assert_called()

        assert isinstance(results, list)

    def test_fallback_post_retrieval_llm_missing(self):
        """Fallback a identity per post-retrieval se LLM mancante."""
        from knowledge_base.search_service import (
            PostRetrievalConfig,
            SearchConfig,
            SearchService,
        )

        docs = {"c1": "testo"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        service = SearchService(
            llm_factory=None,
            embedder_factory=lambda model: embedder,
            collection_factory=lambda: collection,
        )
        config = SearchConfig(
            post_retrieval=PostRetrievalConfig(method="llm")
        )

        with patch("knowledge_base.search_service.logger") as mock_logger:
            results = service.search("test", config=config, top_k=5)
            mock_logger.warning.assert_called()

        assert isinstance(results, list)

    def test_invalid_retrieval_method_raises(self):
        """Metodo di retrieval sconosciuto solleva errore."""
        from knowledge_base.search_service import (
            RetrievalConfig,
            SearchConfig,
            SearchConfigError,
            SearchService,
        )

        docs = {"c1": "testo"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        service = SearchService(
            embedder_factory=lambda model: embedder,
            collection_factory=lambda: collection,
        )
        config = SearchConfig(
            retrieval=RetrievalConfig(method="non_esistente")
        )

        with pytest.raises(SearchConfigError, match="non_esistente"):
            service.search("test", config=config)

    def test_search_with_llm_factory(self):
        """SearchService con LLM factory funzionante."""
        from knowledge_base.search_service import (
            PreRetrievalStageConfig,
            SearchConfig,
            SearchService,
        )

        docs = {"c1": "testo"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        llm = MockFixedLLM()
        service = SearchService(
            llm_factory=lambda model: llm,
            embedder_factory=lambda model: embedder,
            collection_factory=lambda: collection,
        )
        config = SearchConfig(
            pre_retrieval=[PreRetrievalStageConfig(method="step_back")]
        )

        results = service.search("test", config=config, top_k=5)
        assert isinstance(results, list)

    def test_default_config(self):
        """Configurazione di default: identity → dense → identity."""
        from knowledge_base.search_service import SearchService

        docs = {"c1": "testo"}
        collection = MockCollection(docs=docs)
        embedder = MockEmbedder()

        service = SearchService(
            embedder_factory=lambda model: embedder,
            collection_factory=lambda: collection,
        )
        # config=None dovrebbe usare i default
        results = service.search("test")
        assert isinstance(results, list)


# --------------------------------------------------------------------------- #
# SearchService — configurazione
# --------------------------------------------------------------------------- #


class TestSearchServiceConfig:
    def test_pre_retrieval_stage_config(self):
        from knowledge_base.search_service import PreRetrievalStageConfig

        config = PreRetrievalStageConfig(method="multi_query", params={"n": 5})
        assert config.method == "multi_query"
        assert config.params == {"n": 5}

    def test_retrieval_config_defaults(self):
        from knowledge_base.search_service import RetrievalConfig

        config = RetrievalConfig()
        assert config.method == "dense"
        assert config.query_mode == "original"
        assert config.top_k == 10

    def test_post_retrieval_config_defaults(self):
        from knowledge_base.search_service import PostRetrievalConfig

        config = PostRetrievalConfig()
        assert config.method == "identity"

    def test_search_config_defaults(self):
        from knowledge_base.search_service import SearchConfig

        config = SearchConfig()
        assert len(config.pre_retrieval) == 1
        assert config.pre_retrieval[0].method == "identity"
        assert config.retrieval.method == "dense"
        assert config.post_retrieval.method == "identity"


# --------------------------------------------------------------------------- #
# BaseConfig — sezioni retrieval nel TOML
# --------------------------------------------------------------------------- #


class TestBaseConfigRetrievalSections:
    def test_default_config_has_retrieval_sections(self):
        config = BaseConfig()
        assert config.pre_retrieval is not None
        assert config.retrieval is not None
        assert config.post_retrieval is not None
        assert config.pre_retrieval.stages[0].method == "identity"
        assert config.retrieval.method == "dense"
        assert config.post_retrieval.method == "identity"

    def test_from_toml_pre_retrieval(self):
        data = {
            "pre_retrieval": {
                "stages": [
                    {"method": "multi_query", "params": {"n": 3}},
                ]
            }
        }
        config = BaseConfig.from_toml(data)
        assert config.pre_retrieval.stages[0].method == "multi_query"
        assert config.pre_retrieval.stages[0].params == {"n": 3}

    def test_from_toml_retrieval(self):
        data = {
            "retrieval": {
                "method": "hybrid",
                "query_mode": "hyde",
                "top_k": 20,
            }
        }
        config = BaseConfig.from_toml(data)
        assert config.retrieval.method == "hybrid"
        assert config.retrieval.query_mode == "hyde"
        assert config.retrieval.top_k == 20

    def test_from_toml_post_retrieval(self):
        data = {
            "post_retrieval": {
                "method": "mmr",
                "params": {"lambda_param": 0.7},
            }
        }
        config = BaseConfig.from_toml(data)
        assert config.post_retrieval.method == "mmr"
        assert config.post_retrieval.params == {"lambda_param": 0.7}

    def test_from_toml_multiple_pre_retrieval_stages(self):
        data = {
            "pre_retrieval": {
                "stages": [
                    {"method": "multi_query"},
                    {"method": "step_back"},
                ]
            }
        }
        config = BaseConfig.from_toml(data)
        assert len(config.pre_retrieval.stages) == 2
        assert config.pre_retrieval.stages[0].method == "multi_query"
        assert config.pre_retrieval.stages[1].method == "step_back"

    def test_from_toml_invalid_pre_retrieval_stage(self):
        """Stage non-dict viene ignorato con warning."""
        data = {"pre_retrieval": {"stages": ["not_a_dict", {"method": "identity"}]}}
        config = BaseConfig.from_toml(data)
        # Solo il secondo stage valido viene parsato
        assert len(config.pre_retrieval.stages) == 1
        assert config.pre_retrieval.stages[0].method == "identity"

    def test_from_toml_unknown_field_retrieval(self):
        """Campo sconosciuto in [retrieval] viene ignorato."""
        data = {"retrieval": {"method": "dense", "campo_sconosciuto": True}}
        config = BaseConfig.from_toml(data)
        assert config.retrieval.method == "dense"

    def test_from_toml_invalid_params_retrieval(self):
        """params non-dict in [retrieval] viene ignorato."""
        data = {"retrieval": {"method": "dense", "params": "not_a_dict"}}
        config = BaseConfig.from_toml(data)
        assert config.retrieval.params == {}

    def test_override_retrieval_sections(self):
        base = BaseConfig()
        other = BaseConfig.from_toml(
            {"retrieval": {"method": "hybrid", "top_k": 50}}
        )
        merged = base.override(other)
        assert merged.retrieval.method == "hybrid"
        assert merged.retrieval.top_k == 50

    def test_full_toml_example(self):
        """Esempio TOML completo dalla roadmap."""
        data = {
            "pre_retrieval": {
                "stages": [{"method": "identity"}],
            },
            "retrieval": {
                "method": "dense",
                "top_k": 10,
            },
            "post_retrieval": {
                "method": "identity",
            },
        }
        config = BaseConfig.from_toml(data)
        assert config.pre_retrieval.stages[0].method == "identity"
        assert config.retrieval.method == "dense"
        assert config.retrieval.top_k == 10
        assert config.post_retrieval.method == "identity"


# --------------------------------------------------------------------------- #
# Active filter helpers (Bug-012)
# --------------------------------------------------------------------------- #


class TestIsBaseSearchable:
    """Test per ``is_base_searchable``."""

    def test_base_attiva_senza_domini(self):
        from knowledge_base.models import KnowledgeBase
        from knowledge_base.search_service import is_base_searchable

        kb = KnowledgeBase(path="/tmp/test")
        assert is_base_searchable("Test", kb, []) is True

    def test_base_disattivata(self):
        from knowledge_base.models import KnowledgeBase
        from knowledge_base.search_service import is_base_searchable

        kb = KnowledgeBase(path="/tmp/test", active=False)
        assert is_base_searchable("Test", kb, []) is False

    def test_base_in_dominio_attivo(self):
        from knowledge_base.models import Domain, KnowledgeBase
        from knowledge_base.search_service import is_base_searchable

        kb = KnowledgeBase(path="/tmp/test")
        domains = [Domain(name="D1", active=True, base_names=["Test"])]
        assert is_base_searchable("Test", kb, domains) is True

    def test_base_in_dominio_disattivato(self):
        from knowledge_base.models import Domain, KnowledgeBase
        from knowledge_base.search_service import is_base_searchable

        kb = KnowledgeBase(path="/tmp/test")
        domains = [Domain(name="D1", active=False, base_names=["Test"])]
        assert is_base_searchable("Test", kb, domains) is False

    def test_base_non_in_alcun_dominio(self):
        """Base non in nessun dominio è sempre searchable."""
        from knowledge_base.models import Domain, KnowledgeBase
        from knowledge_base.search_service import is_base_searchable

        kb = KnowledgeBase(path="/tmp/test")
        domains = [Domain(name="D1", active=True, base_names=["Altro"])]
        assert is_base_searchable("Test", kb, domains) is True


class TestFilterActiveChunks:
    """Test per ``filter_active_chunks``."""

    def test_chunk_attivo_non_filtrato(self):
        from knowledge_base.models import ChunkRef, FileEntry, KnowledgeBase
        from knowledge_base.search_service import filter_active_chunks
        from knowledge_base.strategies import RetrievalResult

        kb = KnowledgeBase(path="/tmp/test")
        kb.files["doc.pdf"] = FileEntry(
            mtime=1.0,
            added="2026-01-01",
            file_id="abc123",
            active=True,
            chunks=[ChunkRef(index=0, active=True)],
        )
        results = [RetrievalResult(
            chunk_id="Test::abc123::0",
            text="test",
            score=0.9,
        )]
        filtered = filter_active_chunks(results, kb)
        assert len(filtered) == 1

    def test_file_disattivato_filtrato(self):
        from knowledge_base.models import ChunkRef, FileEntry, KnowledgeBase
        from knowledge_base.search_service import filter_active_chunks
        from knowledge_base.strategies import RetrievalResult

        kb = KnowledgeBase(path="/tmp/test")
        kb.files["doc.pdf"] = FileEntry(
            mtime=1.0,
            added="2026-01-01",
            file_id="abc123",
            active=False,
            chunks=[ChunkRef(index=0, active=True)],
        )
        results = [RetrievalResult(
            chunk_id="Test::abc123::0",
            text="test",
            score=0.9,
        )]
        filtered = filter_active_chunks(results, kb)
        assert len(filtered) == 0

    def test_chunk_disattivato_filtrato(self):
        from knowledge_base.models import ChunkRef, FileEntry, KnowledgeBase
        from knowledge_base.search_service import filter_active_chunks
        from knowledge_base.strategies import RetrievalResult

        kb = KnowledgeBase(path="/tmp/test")
        kb.files["doc.pdf"] = FileEntry(
            mtime=1.0,
            added="2026-01-01",
            file_id="abc123",
            active=True,
            chunks=[ChunkRef(index=0, active=False)],
        )
        results = [RetrievalResult(
            chunk_id="Test::abc123::0",
            text="test",
            score=0.9,
        )]
        filtered = filter_active_chunks(results, kb)
        assert len(filtered) == 0

    def test_chunk_id_malformed_ignorato(self):
        from knowledge_base.models import KnowledgeBase
        from knowledge_base.search_service import filter_active_chunks
        from knowledge_base.strategies import RetrievalResult

        kb = KnowledgeBase(path="/tmp/test")
        results = [RetrievalResult(
            chunk_id="formato_sbagliato",
            text="test",
            score=0.9,
        )]
        filtered = filter_active_chunks(results, kb)
        assert len(filtered) == 0
