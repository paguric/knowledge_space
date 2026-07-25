"""Strategie di post-retrieval: reranking e compression dei risultati.

Ogni strategia riceve una lista di :class:`RetrievalResult` e la
riordina/comprime. Strategie con ``requires_model=True`` richiedono un
modello (es. cross-encoder) al costruttore; quelle con
``requires_llm=True`` richiedono un :class:`LLMStrategy`.

Strategie:
- ``identity``: no-op, restituisce i risultati invariati.
- ``relevance``: rule-based, filtra per soglia di score.
- ``mmr``: Maximal Marginal Relevance, usa embedding dei chunk.
- ``cross_encoder``: model-based reranker (import lazy come embedding.py).
- ``llm``: LLM-based reranker.
- ``llm_chain_extract``: compressor LLM.
- ``selective_context``: compressor basato su contesto selettivo.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from knowledge_base.strategies import (
    EmbeddingStrategy,
    LLMStrategy,
    PostRetrievalStrategy,
    RetrievalResult,
    post_retrieval_registry,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Classe base
# --------------------------------------------------------------------------- #


class BasePostRetrieval:
    """Base comune per strategie di post-retrieval."""

    name: str = ""
    requires_llm: bool = False
    requires_model: bool = False

    def __init__(self, **params: Any) -> None:
        self.params = params

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# identity — no-op
# --------------------------------------------------------------------------- #


class IdentityPostRetrieval(BasePostRetrieval):
    """No-op: restituisce i risultati invariati, troncati a top_k."""

    name = "identity"
    requires_llm = False
    requires_model = False

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        return results[:top_k]


# --------------------------------------------------------------------------- #
# relevance — rule-based, filtra per soglia
# --------------------------------------------------------------------------- #


class RelevancePostRetrieval(BasePostRetrieval):
    """Filtra i risultati sotto una soglia di score (rule-based).

    Nessun modello richiesto. Utile come post-filter dopo un retrieval
    generoso (top_k alto) per eliminare risultati poco rilevanti.
    """

    name = "relevance"
    requires_llm = False
    requires_model = False

    def __init__(
        self,
        threshold: float = 0.3,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.threshold = threshold

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        filtered = [r for r in results if r.score >= self.threshold]
        return filtered[:top_k]


# --------------------------------------------------------------------------- #
# mmr — Maximal Marginal Relevance
# --------------------------------------------------------------------------- #


class MMRPostRetrieval(BasePostRetrieval):
    """Maximal Marginal Relevance (MMR).

    Seleziona risultati che massimizzano un compromesso tra rilevanza
    (score originale) e diversità (dissimilarità dai risultati già
    selezionati). Usa gli embedding dei chunk per calcolare la
    similarità.

    ``lambda_param`` controlla il trade-off:
    - ``lambda_param = 1.0`` → puro score (equivalente a identity).
    - ``lambda_param = 0.0`` → pura diversità (seleziona i più diversi).
    """

    name = "mmr"
    requires_llm = False
    requires_model = False

    def __init__(
        self,
        embedder: Optional[EmbeddingStrategy] = None,
        lambda_param: float = 0.5,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.embedder = embedder
        self.lambda_param = lambda_param

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        if not results or self.embedder is None:
            return results[:top_k]

        if len(results) <= top_k:
            return results

        # Embed all result texts
        texts = [r.text for r in results]
        embeddings = self.embedder.embed(texts)

        # MMR selection
        selected_indices: List[int] = []
        remaining_indices = list(range(len(results)))

        # First: select the highest-scored result
        best_idx = max(remaining_indices, key=lambda i: results[i].score)
        selected_indices.append(best_idx)
        remaining_indices.remove(best_idx)

        # Iteratively select results that maximize MMR
        while len(selected_indices) < top_k and remaining_indices:
            best_mmr = float("-inf")
            best_idx = remaining_indices[0]

            for idx in remaining_indices:
                # Relevance component
                relevance = results[idx].score

                # Diversity component: max similarity to already selected
                max_sim = max(
                    _cosine_similarity(embeddings[idx], embeddings[sel])
                    for sel in selected_indices
                )

                # MMR score
                mmr = self.lambda_param * relevance - (1 - self.lambda_param) * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = idx

            selected_indices.append(best_idx)
            remaining_indices.remove(best_idx)

        return [results[i] for i in selected_indices]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calcola la similarità coseno tra due vettori."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# --------------------------------------------------------------------------- #
# cross_encoder — model-based reranker (import lazy)
# --------------------------------------------------------------------------- #


class CrossEncoderPostRetrieval(BasePostRetrieval):
    """Reranker basato su cross-encoder model.

    Usa un modello cross-encoder (es. ``cross-encoder/ms-marco-MiniLM-L-6-v2``)
    per riordinare i risultati. Il modello è caricato lazy al primo uso,
    come in ``embedding.py``.

    ``model_name`` è il nome del modello HuggingFace. Se non fornito,
    usa un default ragionevole.
    """

    name = "cross_encoder"
    requires_llm = False
    requires_model = True

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        if not results:
            return []

        model = self._load_model()
        pairs = [(query, r.text) for r in results]
        scores = model.predict(pairs)

        # Associa gli score e ordina
        scored = list(zip(results, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            RetrievalResult(
                chunk_id=r.chunk_id,
                text=r.text,
                score=float(s),
                metadata={**r.metadata, "reranked": True},
            )
            for r, s in scored[:top_k]
        ]


# --------------------------------------------------------------------------- #
# llm — LLM-based reranker
# --------------------------------------------------------------------------- #


class LLMPostRetrieval(BasePostRetrieval):
    """Reranker basato su LLM.

    Chiede all'LLM di valutare la rilevanza di ogni risultato rispetto
    alla query e riordina in base al punteggio assegnato. Richiede
    ``requires_llm=True``.
    """

    name = "llm"
    requires_llm = True
    requires_model = False

    def __init__(
        self,
        llm: LLMStrategy,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.llm = llm

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        if not results:
            return []

        # Per ogni risultato, chiedi all'LLM un punteggio 1-10
        scored_results: List[tuple[RetrievalResult, float]] = []
        for r in results:
            score = self._score_relevance(query, r.text)
            scored_results.append((r, score))

        # Ordina per score decrescente
        scored_results.sort(key=lambda x: x[1], reverse=True)

        return [
            RetrievalResult(
                chunk_id=r.chunk_id,
                text=r.text,
                score=s / 10.0,  # Normalizza in [0, 1]
                metadata={**r.metadata, "llm_reranked": True},
            )
            for r, s in scored_results[:top_k]
        ]

    def _score_relevance(self, query: str, text: str) -> float:
        """Chiede all'LLM un punteggio di rilevanza 1-10."""
        prompt = (
            "Valuta la rilevanza del seguente testo rispetto alla domanda. "
            "Rispondi SOLO con un numero da 1 (irrilevante) a 10 (molto rilevante).\n\n"
            f"Domanda: {query}\n\n"
            f"Testo: {text[:500]}\n\n"
            "Punteggio:"
        )
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate(messages, max_tokens=10, temperature=0.0)
        try:
            return float(response.strip())
        except ValueError:
            return 5.0  # Default neutro se il parsing fallisce


# --------------------------------------------------------------------------- #
# llm_chain_extract — compressor LLM
# --------------------------------------------------------------------------- #


class LLMChainExtractPostRetrieval(BasePostRetrieval):
    """Compressor basato su LLM: estrae solo le parti rilevanti.

    Per ogni risultato, chiede all'LLM di estrarre solo le frasi/punti
    rilevanti rispetto alla query, riducendo la lunghezza del testo.
    Richiede ``requires_llm=True``.
    """

    name = "llm_chain_extract"
    requires_llm = True
    requires_model = False

    def __init__(
        self,
        llm: LLMStrategy,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.llm = llm

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        if not results:
            return []

        compressed: List[RetrievalResult] = []
        for r in results[:top_k]:
            extracted = self._extract(query, r.text)
            if extracted.strip():
                compressed.append(
                    RetrievalResult(
                        chunk_id=r.chunk_id,
                        text=extracted,
                        score=r.score,
                        metadata={**r.metadata, "compressed": True},
                    )
                )
        return compressed

    def _extract(self, query: str, text: str) -> str:
        """Estrae le parti rilevanti dal testo."""
        prompt = (
            "Data la seguente domanda, estrai SOLO le frasi o i punti "
            "del testo che sono rilevanti per rispondere. Mantieni il "
            "testo originale senza parafrasare. Se nulla è rilevante, "
            "rispondi con 'NESSUN CONTENUTO RILEVANTE'.\n\n"
            f"Domanda: {query}\n\n"
            f"Testo:\n{text}\n\n"
            "Estratto rilevante:"
        )
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate(messages, max_tokens=1024, temperature=0.0)
        if "NESSUN CONTENUTO RILEVANTE" in response.upper():
            return ""
        return response.strip()


# --------------------------------------------------------------------------- #
# selective_context — compressor basato su contesto selettivo
# --------------------------------------------------------------------------- #


class SelectiveContextPostRetrieval(BasePostRetrieval):
    """Compressor basato su selezione del contesto.

    Seleziona le frasi del documento che massimizzano la copertura
    informativa rispetto alla query, usando l'LLM per identificare le
    frasi chiave. Richiede ``requires_llm=True``.
    """

    name = "selective_context"
    requires_llm = True
    requires_model = False

    def __init__(
        self,
        llm: LLMStrategy,
        compression_ratio: float = 0.5,
        **params: Any,
    ) -> None:
        super().__init__(**params)
        self.llm = llm
        self.compression_ratio = compression_ratio

    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int = 10,
    ) -> List[RetrievalResult]:
        if not results:
            return []

        compressed: List[RetrievalResult] = []
        for r in results[:top_k]:
            selected = self._select_context(query, r.text)
            if selected.strip():
                compressed.append(
                    RetrievalResult(
                        chunk_id=r.chunk_id,
                        text=selected,
                        score=r.score,
                        metadata={
                            **r.metadata,
                            "compressed": True,
                            "compression_ratio": self.compression_ratio,
                        },
                    )
                )
        return compressed

    def _select_context(self, query: str, text: str) -> str:
        """Seleziona le frasi più rilevanti dal testo."""
        # Dividi in frasi
        sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
        if not sentences:
            return text

        # Calcola quante frasi mantenere
        n_keep = max(1, int(len(sentences) * self.compression_ratio))

        # Chiedi all'LLM di selezionare le frasi più importanti
        sentences_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sentences))
        prompt = (
            f"Dalla seguente lista di frasi, seleziona le {n_keep} più "
            f"rilevanti per rispondere alla domanda. Rispondi SOLO con i "
            f"numeri delle frasi selezionate, separati da virgole.\n\n"
            f"Domanda: {query}\n\n"
            f"Frasi:\n{sentences_text}\n\n"
            f"Numeri selezionati:"
        )
        messages = [{"role": "user", "content": prompt}]
        response = self.llm.generate(messages, max_tokens=100, temperature=0.0)

        # Parse della risposta
        try:
            indices = [int(x.strip()) - 1 for x in response.strip().split(",")]
            selected = [sentences[i] for i in indices if 0 <= i < len(sentences)]
            if selected:
                return ". ".join(selected)
        except (ValueError, IndexError):
            pass

        # Fallback: prime n_keep frasi
        return ". ".join(sentences[:n_keep])


# --------------------------------------------------------------------------- #
# Registrazione all'avvio
# --------------------------------------------------------------------------- #

post_retrieval_registry.register("identity", IdentityPostRetrieval)
post_retrieval_registry.register("relevance", RelevancePostRetrieval)
post_retrieval_registry.register("mmr", MMRPostRetrieval)
post_retrieval_registry.register("cross_encoder", CrossEncoderPostRetrieval)
post_retrieval_registry.register("llm", LLMPostRetrieval)
post_retrieval_registry.register("llm_chain_extract", LLMChainExtractPostRetrieval)
post_retrieval_registry.register("selective_context", SelectiveContextPostRetrieval)
