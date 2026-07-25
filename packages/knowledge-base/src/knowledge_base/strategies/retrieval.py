"""Strategie di retrieval: dense, sparse e hybrid.

Ogni strategia esegue la ricerca su un vector store (Chroma) e/o un
indice sparse (BM25) e restituisce risultati ordinati per score.

Strategie:
- ``dense``: similarity search su Chroma.
- ``sparse``: BM25-like con ``rank_bm25``.
- ``hybrid``: ensemble dense + sparse, fusione ``rrf`` o ``weighted_sum``.

Query mode:
- ``original``: embed_query standard.
- ``hyde``: genera documento ipotetico con LLM, poi embed_documents.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from knowledge_base.strategies import (
    EmbeddingStrategy,
    LLMStrategy,
    RetrievalResult,
    RetrievalStrategy,
    retrieval_registry,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Eccezioni
# --------------------------------------------------------------------------- #


class CollectionNotReadyError(RuntimeError):
    """Sollevata quando la collection Chroma non è accessibile."""

    def __init__(self, base_name: str, detail: str) -> None:
        self.base_name = base_name
        super().__init__(
            f"Collection per la base '{base_name}' non pronta: {detail}"
        )


# --------------------------------------------------------------------------- #
# Classe base
# --------------------------------------------------------------------------- #


class BaseRetrieval:
    """Base comune per strategie di retrieval."""

    name: str = ""

    def __init__(self, **params: Any) -> None:
        self.params = params

    def search(
        self, query: str, *, top_k: int = 10, **kwargs: Any
    ) -> List[RetrievalResult]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# dense — similarity search su Chroma
# --------------------------------------------------------------------------- #


class DenseRetrieval(BaseRetrieval):
    """Similarity search su Chroma.

    Supporta due query mode:
    - ``original`` (default): embed della query con ``embed_query``.
    - ``hyde``: genera un documento ipotetico con LLM, poi embed del
      documento con ``embed_documents``.

    Il collection accessor Chroma è iniettato al costruttore come
    callable ``collection_factory``.
    """

    name = "dense"

    def __init__(
        self,
        embedder: EmbeddingStrategy,
        collection_factory: Callable[[], Any],
        query_mode: str = "original",
        llm: Optional[LLMStrategy] = None,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.embedder = embedder
        self.collection_factory = collection_factory
        self.query_mode = query_mode
        self.llm = llm

    def search(
        self, query: str, *, top_k: int = 10, **kwargs: Any
    ) -> List[RetrievalResult]:
        collection = self.collection_factory()
        query_vector = self._embed_query(query, **kwargs)

        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=["documents", "distances", "metadatas"],
        )

        return self._parse_chroma_results(results)

    def _embed_query(self, query: str, **kwargs: Any) -> List[float]:
        """Embed della query secondo la modalità configurata."""
        if self.query_mode == "hyde" and self.llm is not None:
            return self._hyde_embed(query)
        return self.embedder.embed([query])[0]

    def _hyde_embed(self, query: str) -> List[float]:
        """HyDE: genera documento ipotetico, poi embed_documento."""
        prompt = (
            "Scrivi un breve paragrafo (3-5 frasi) che risponda alla "
            f"seguente domanda in modo dettagliato e fattuale.\n\n"
            f"Domanda: {query}"
        )
        messages = [{"role": "user", "content": prompt}]
        hypothetical_doc = self.llm.generate(messages, max_tokens=256)  # type: ignore[union-attr]
        return self.embedder.embed([hypothetical_doc])[0]

    @staticmethod
    def _parse_chroma_results(results: dict) -> List[RetrievalResult]:
        """Converte i risultati grezzi di Chroma in RetrievalResult."""
        parsed: List[RetrievalResult] = []
        if not results or not results.get("ids"):
            return parsed

        ids = results["ids"][0]
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        for i, chunk_id in enumerate(ids):
            # Chroma cosine distance: 0 = identico, 2 = opposto.
            # Convertiamo in score: 1 - distance/2 → [0, 1] (1 = perfetto).
            distance = distances[i] if i < len(distances) else 0.0
            score = max(0.0, 1.0 - distance / 2.0)
            text = documents[i] if i < len(documents) else ""
            metadata = metadatas[i] if i < len(metadatas) else {}
            parsed.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    text=text,
                    score=score,
                    metadata=metadata,
                )
            )
        return parsed


# --------------------------------------------------------------------------- #
# sparse — BM25-like
# --------------------------------------------------------------------------- #


class SparseRetrieval(BaseRetrieval):
    """BM25-like retrieval con ``rank_bm25``.

    Mantiene un indice in memoria costruito dai documenti della collection
    Chroma. Per Fase 1B, l'indice è costruito on-demand alla prima
    ricerca (lazy loading).

    Se ``rank_bm25`` non è installato, solleva ``ImportError`` con
    messaggio esplicativo.
    """

    name = "sparse"

    def __init__(
        self,
        collection_factory: Callable[[], Any],
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.collection_factory = collection_factory
        self._bm25 = None
        self._doc_ids: List[str] = []
        self._doc_texts: List[str] = []

    def _build_index(self) -> None:
        """Costruisce l'indice BM25 dalla collection Chroma."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            raise ImportError(
                "La strategy 'sparse' richiede 'rank_bm25'. "
                "Installare con: pip install rank-bm25"
            )

        collection = self.collection_factory()
        all_docs = collection.get(include=["documents"])

        if not all_docs or not all_docs.get("ids"):
            self._bm25 = BM25Okapi(["placeholder".split()])
            self._doc_ids = []
            self._doc_texts = []
            return

        self._doc_ids = all_docs["ids"]
        self._doc_texts = all_docs["documents"]
        tokenized = [text.split() for text in self._doc_texts]
        self._bm25 = BM25Okapi(tokenized)

    def search(
        self, query: str, *, top_k: int = 10, **kwargs: Any
    ) -> List[RetrievalResult]:
        if self._bm25 is None:
            self._build_index()

        if not self._doc_ids:
            return []

        assert self._bm25 is not None
        tokenized_query = query.split()
        scores = self._bm25.get_scores(tokenized_query)

        # Ordina per score decrescente e prendi top_k
        scored = sorted(
            zip(self._doc_ids, self._doc_texts, scores),
            key=lambda x: x[2],
            reverse=True,
        )[:top_k]

        results: List[RetrievalResult] = []
        for chunk_id, text, score in scored:
            # Normalizza score BM25 in [0, 1] (approssimazione)
            normalized_score = min(1.0, max(0.0, score / (score + 1.0)))
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    text=text,
                    score=normalized_score,
                    metadata={"bm25_raw_score": float(score)},
                )
            )
        return results


# --------------------------------------------------------------------------- #
# hybrid — ensemble dense + sparse
# --------------------------------------------------------------------------- #


def _rrf_fusion(
    dense_results: List[RetrievalResult],
    sparse_results: List[RetrievalResult],
    k: int = 60,
) -> List[RetrievalResult]:
    """Reciprocal Rank Fusion (RRF).

    Combina due liste ordinate di risultati usando la formula:
    ``score = sum(1 / (k + rank_i))`` dove ``rank_i`` è la posizione (0-based)
    nella lista i-esima.
    """
    rrf_scores: Dict[str, float] = {}
    chunk_map: Dict[str, RetrievalResult] = {}

    for rank, result in enumerate(dense_results):
        rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0.0) + 1.0 / (k + rank)
        chunk_map[result.chunk_id] = result

    for rank, result in enumerate(sparse_results):
        rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0.0) + 1.0 / (k + rank)
        if result.chunk_id not in chunk_map:
            chunk_map[result.chunk_id] = result

    # Ordina per RRF score decrescente
    sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

    results: List[RetrievalResult] = []
    for chunk_id in sorted_ids:
        original = chunk_map[chunk_id]
        results.append(
            RetrievalResult(
                chunk_id=chunk_id,
                text=original.text,
                score=rrf_scores[chunk_id],
                metadata={**original.metadata, "fusion_method": "rrf"},
            )
        )
    return results


def _weighted_sum_fusion(
    dense_results: List[RetrievalResult],
    sparse_results: List[RetrievalResult],
    dense_weight: float = 0.7,
    sparse_weight: float = 0.3,
) -> List[RetrievalResult]:
    """Weighted sum fusion.

    Combina gli score di dense e sparse con pesi configurabili.
    """
    score_map: Dict[str, float] = {}
    chunk_map: Dict[str, RetrievalResult] = {}

    for result in dense_results:
        score_map[result.chunk_id] = score_map.get(result.chunk_id, 0.0) + result.score * dense_weight
        chunk_map[result.chunk_id] = result

    for result in sparse_results:
        score_map[result.chunk_id] = score_map.get(result.chunk_id, 0.0) + result.score * sparse_weight
        if result.chunk_id not in chunk_map:
            chunk_map[result.chunk_id] = result

    sorted_ids = sorted(score_map.keys(), key=lambda cid: score_map[cid], reverse=True)

    results: List[RetrievalResult] = []
    for chunk_id in sorted_ids:
        original = chunk_map[chunk_id]
        results.append(
            RetrievalResult(
                chunk_id=chunk_id,
                text=original.text,
                score=score_map[chunk_id],
                metadata={**original.metadata, "fusion_method": "weighted_sum"},
            )
        )
    return results


class HybridRetrieval(BaseRetrieval):
    """Ensemble dense + sparse con fusione configurabile.

    Combina i risultati di ``DenseRetrieval`` e ``SparseRetrieval``
    usando una strategia di fusione:
    - ``rrf`` (default): Reciprocal Rank Fusion.
    - ``weighted_sum``: somma pesata degli score.
    """

    name = "hybrid"

    def __init__(
        self,
        dense: DenseRetrieval,
        sparse: SparseRetrieval,
        fusion: str = "rrf",
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        rrf_k: int = 60,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.dense = dense
        self.sparse = sparse
        self.fusion = fusion
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.rrf_k = rrf_k

    def search(
        self, query: str, *, top_k: int = 10, **kwargs: Any
    ) -> List[RetrievalResult]:
        # Recupera più risultati dal componente per garantire che
        # la fusione abbia materiale sufficiente.
        fetch_k = top_k * 3
        dense_results = self.dense.search(query, top_k=fetch_k, **kwargs)
        sparse_results = self.sparse.search(query, top_k=fetch_k, **kwargs)

        if self.fusion == "weighted_sum":
            fused = _weighted_sum_fusion(
                dense_results,
                sparse_results,
                self.dense_weight,
                self.sparse_weight,
            )
        else:
            fused = _rrf_fusion(dense_results, sparse_results, self.rrf_k)

        return fused[:top_k]


# --------------------------------------------------------------------------- #
# Registrazione all'avvio
# --------------------------------------------------------------------------- #

retrieval_registry.register("dense", DenseRetrieval)
retrieval_registry.register("sparse", SparseRetrieval)
retrieval_registry.register("hybrid", HybridRetrieval)
