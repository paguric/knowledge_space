"""SearchService — orchestrazione della pipeline di retrieval.

La pipeline è composta da 3 step sequenziali:

1. **Pre-retrieval**: espansione testuale delle query (identity, multi_query,
   step_back, least_to_most). Ogni stadio riceve le query del precedente.
2. **Retrieval**: ricerca su Chroma (dense) o BM25 (sparse) o entrambi
   (hybrid). Supporta query mode ``original`` e ``hyde``.
3. **Post-retrieval**: reranking/compression dei risultati (identity,
   relevance, mmr, cross_encoder, llm, llm_chain_extract, selective_context).

Se un metodo richiede LLM ma non è configurato → fallback automatico a
``identity`` con warning. Nessuna variabile globale: tutto iniettato.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from knowledge_base.strategies import (
    LLMStrategy,
    PostRetrievalStrategy,
    PreRetrievalStrategy,
    RetrievalResult,
    RetrievalStrategy,
    post_retrieval_registry,
    pre_retrieval_registry,
    retrieval_registry,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Helpers per il filtro active (usati da CLI e SearchService)
# --------------------------------------------------------------------------- #


def is_base_searchable(base_name: str, kb: Any, domains: List[Any]) -> bool:
    """``True`` se la base è attiva e appartiene ad almeno un dominio attivo.

    Se non ci sono domini configurati, tutte le basi sono considerate
    searchable (basta che la base stessa sia attiva).
    """
    if not kb.active:
        return False
    if not domains:
        return True
    for d in domains:
        if base_name in d.base_names:
            return d.active
    return True


def filter_active_chunks(
    results: List[RetrievalResult],
    kb: Any,
) -> List[RetrievalResult]:
    """Filtra i risultati escludendo chunk di file o chunk disattivati.

    Parsa ``chunk_id`` (formato ``"{base_name}::{file_id}::{i}"``) per
    risalire a :class:`FileEntry` e :class:`ChunkRef` nel modello ``kb``.
    """
    # Pre-costruisci lookup file_id → FileEntry (più efficiente dell'iterazione)
    file_by_id: Dict[str, Any] = {}
    for fe in kb.files.values():
        if fe.file_id:
            file_by_id[fe.file_id] = fe

    filtered: List[RetrievalResult] = []
    for r in results:
        parts = r.chunk_id.rsplit("::", 2)
        if len(parts) != 3:
            continue
        _, file_id_str, index_str = parts
        try:
            idx = int(index_str)
        except ValueError:
            continue

        fe = file_by_id.get(file_id_str)
        if fe is None or not fe.active:
            continue
        if idx >= len(fe.chunks) or not fe.chunks[idx].active:
            continue
        filtered.append(r)
    return filtered


# --------------------------------------------------------------------------- #
# Eccezioni
# --------------------------------------------------------------------------- #


class SearchConfigError(ValueError):
    """Sollevata per errori di configurazione della ricerca."""


# --------------------------------------------------------------------------- #
# Data classes per la configurazione
# --------------------------------------------------------------------------- #


class PreRetrievalStageConfig:
    """Configurazione di un singolo stadio di pre-retrieval."""

    def __init__(
        self,
        method: str = "identity",
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.method = method
        self.params = params or {}


class RetrievalConfig:
    """Configurazione della fase di retrieval."""

    def __init__(
        self,
        method: str = "dense",
        query_mode: str = "original",
        top_k: int = 10,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.method = method
        self.query_mode = query_mode
        self.top_k = top_k
        self.params = params or {}


class PostRetrievalConfig:
    """Configurazione della fase di post-retrieval."""

    def __init__(
        self,
        method: str = "identity",
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.method = method
        self.params = params or {}


class SearchConfig:
    """Configurazione completa della ricerca."""

    def __init__(
        self,
        pre_retrieval: Optional[List[PreRetrievalStageConfig]] = None,
        retrieval: Optional[RetrievalConfig] = None,
        post_retrieval: Optional[PostRetrievalConfig] = None,
    ) -> None:
        self.pre_retrieval = pre_retrieval or [PreRetrievalStageConfig()]
        self.retrieval = retrieval or RetrievalConfig()
        self.post_retrieval = post_retrieval or PostRetrievalConfig()


# --------------------------------------------------------------------------- #
# SearchService
# --------------------------------------------------------------------------- #


class SearchService:
    """Orchestrazione della pipeline di retrieval.

    Costruisce le strategy in base alla configurazione e le esegue
    sequenzialmente. Le factory sono iniettate per testabilità e per
    supportare il fallback automatico quando LLM non è configurato.

    Args:
        llm_factory: factory per creare un LLMStrategy dato il nome del
            modello. ``None`` se nessun LLM è configurato (fallback a identity).
        embedder_factory: factory per creare un EmbeddingStrategy dato il
            nome del modello.
        collection_factory: callable che restituisce la collection Chroma.
    """

    def __init__(
        self,
        llm_factory: Optional[Any] = None,
        embedder_factory: Optional[Any] = None,
        collection_factory: Optional[Any] = None,
    ) -> None:
        self._llm_factory = llm_factory
        self._embedder_factory = embedder_factory
        self._collection_factory = collection_factory
        self._llm_cache: Dict[str, LLMStrategy] = {}
        # Cache per-modello: evita di ricaricare il modello SentenceTransformer
        # da disco per ogni base/query (bug-026: ~5s a caricamento su CPU).
        self._embedder_cache: Dict[str, Any] = {}
        # Cache del vettore della query per (model_name, query): con più
        # basi sullo stesso modello la query si embedda una volta sola.
        self._query_embed_cache: Dict[tuple, List[float]] = {}

    def _get_llm(self, model_name: str) -> Optional[LLMStrategy]:
        """Ottieni un LLM dalla factory, con caching."""
        if self._llm_factory is None:
            return None
        if model_name not in self._llm_cache:
            try:
                self._llm_cache[model_name] = self._llm_factory(model_name)
            except Exception:
                logger.warning(
                    "LLM '%s' non disponibile, fallback a identity", model_name
                )
                return None
        return self._llm_cache[model_name]

    def _get_embedder(self, model_name: str) -> Optional[Any]:
        """Ottieni un embedder dalla factory, con caching (bug-026)."""
        if self._embedder_factory is None:
            return None
        if model_name not in self._embedder_cache:
            try:
                self._embedder_cache[model_name] = self._embedder_factory(model_name)
            except Exception:
                logger.warning("Embedder '%s' non disponibile", model_name)
                return None
        return self._embedder_cache[model_name]

    def _get_query_embedding(
        self, model_name: str, query: str
    ) -> Optional[List[float]]:
        """Vettore della query con cache per (modello, query)."""
        key = (model_name, query)
        if key not in self._query_embed_cache:
            embedder = self._get_embedder(model_name)
            if embedder is None:
                return None
            self._query_embed_cache[key] = list(embedder.embed([query])[0])
        return self._query_embed_cache[key]

    def search(
        self,
        query: str,
        config: Optional[SearchConfig] = None,
        top_k: int = 10,
        kb: Any = None,
        collection_factory: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        """Esegue la pipeline di ricerca completa.

        Args:
            query: query dell'utente.
            config: configurazione della ricerca. Se ``None``, usa i default.
            top_k: numero massimo di risultati da restituire.
            kb: opzionale :class:`KnowledgeBase` per filtrare chunk/file
                disattivati prima di restituire i risultati.
            collection_factory: override per-chiamata della collection
                (bug-026: un solo SearchService per tutte le basi).

        Returns:
            Lista di :class:`RetrievalResult` ordinati per rilevanza.
        """
        logger.info("Ricerca: query='%s', top_k=%d", query, top_k)
        if config is None:
            config = SearchConfig()

        # 1. Pre-retrieval: espansione delle query
        queries = [query]
        for stage_config in config.pre_retrieval:
            queries = self._run_pre_retrieval_stage(queries, stage_config)

        # 2. Retrieval: ricerca su ogni query e unisci risultati
        all_results: List[RetrievalResult] = []
        seen_chunk_ids: set[str] = set()

        retrieval_top_k = config.retrieval.top_k
        for q in queries:
            results = self._run_retrieval(
                q, config.retrieval, retrieval_top_k, collection_factory
            )
            for r in results:
                if r.chunk_id not in seen_chunk_ids:
                    all_results.append(r)
                    seen_chunk_ids.add(r.chunk_id)

        # Ordina per score e prendi top_k
        all_results.sort(key=lambda r: r.score, reverse=True)
        all_results = all_results[:retrieval_top_k]

        # 3. Post-retrieval: reranking/compression
        final_results = self._run_post_retrieval(
            query, all_results, config.post_retrieval, top_k
        )

        logger.info("Ricerca completata: %d risultati", len(final_results))

        # Filtro post-retrieval: chunk/file disattivati
        if kb is not None:
            final_results = filter_active_chunks(final_results, kb)

        return final_results

    def _run_pre_retrieval_stage(
        self,
        queries: List[str],
        stage_config: PreRetrievalStageConfig,
    ) -> List[str]:
        """Esegue un singolo stadio di pre-retrieval con fallback."""
        method = stage_config.method
        params = dict(stage_config.params)

        # Verifica che la strategy esista
        if not pre_retrieval_registry.contains(method):
            logger.warning(
                "Pre-retrieval strategy '%s' non trovata, fallback a identity",
                method,
            )
            return queries

        strategy_cls = pre_retrieval_registry.get(method)

        # Se richiede LLM, iniettalo
        if getattr(strategy_cls, "requires_llm", False):
            model_name = params.pop("model", "mock/echo")
            llm = self._get_llm(model_name)
            if llm is None:
                logger.warning(
                    "Pre-retrieval '%s' richiede LLM '%s' non disponibile, "
                    "fallback a identity",
                    method,
                    model_name,
                )
                return queries
            params["llm"] = llm

        try:
            strategy = strategy_cls(**params)
            return strategy.expand(queries)
        except Exception as exc:
            logger.warning(
                "Pre-retrieval '%s' fallito: %s, fallback a identity",
                method,
                exc,
            )
            return queries

    def _run_retrieval(
        self,
        query: str,
        retrieval_config: RetrievalConfig,
        top_k: int,
        collection_factory: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        """Esegue la fase di retrieval."""
        method = retrieval_config.method
        params = dict(retrieval_config.params)

        if not retrieval_registry.contains(method):
            raise SearchConfigError(
                f"Retrieval strategy '{method}' non trovata. "
                f"Disponibili: {retrieval_registry.list_names()}"
            )

        strategy_cls = retrieval_registry.get(method)

        # Inietta dipendenze in base al tipo di strategy
        if method == "dense":
            strategy = self._build_dense_strategy(retrieval_config, params, collection_factory)
        elif method == "sparse":
            strategy = self._build_sparse_strategy(params)
        elif method == "hybrid":
            strategy = self._build_hybrid_strategy(retrieval_config, params, collection_factory)
        else:
            raise SearchConfigError(f"Metodo di retrieval non supportato: {method}")

        # Query embedding condiviso (bug-026): per dense/hybrid si calcola
        # UNA volta per (modello, query) e si passa alla strategy — niente
        # re-embed per base. HyDE escluso (il documento ipotetico cambia
        # per chiamata).
        query_embedding = None
        if method in ("dense", "hybrid") and retrieval_config.query_mode != "hyde":
            model_name = params.get(
                "model",
                "BAAI/bge-m3",
            )
            query_embedding = self._get_query_embedding(model_name, query)

        return strategy.search(query, top_k=top_k, query_embedding=query_embedding)

    def _build_dense_strategy(
        self,
        retrieval_config: RetrievalConfig,
        params: Dict[str, Any],
        collection_factory: Optional[Any] = None,
    ) -> Any:
        """Costruisce DenseRetrieval con le dipendenze iniettate."""
        from knowledge_base.strategies.retrieval import DenseRetrieval

        embedder = None
        if self._embedder_factory:
            model_name = params.pop("model", "BAAI/bge-m3")
            embedder = self._get_embedder(model_name)

        if embedder is None:
            raise SearchConfigError(
                "Embedder non configurato per retrieval dense. "
                "Fornire un embedder_factory."
            )

        llm = None
        if retrieval_config.query_mode == "hyde":
            model_name = params.pop("hyde_model", "mock/echo")
            llm = self._get_llm(model_name)

        return DenseRetrieval(
            embedder=embedder,
            collection_factory=collection_factory or self._collection_factory,
            query_mode=retrieval_config.query_mode,
            llm=llm,
            **params,
        )

    def _build_sparse_strategy(
        self,
        params: Dict[str, Any],
    ) -> Any:
        """Costruisce SparseRetrieval con le dipendenze iniettate."""
        from knowledge_base.strategies.retrieval import SparseRetrieval

        return SparseRetrieval(
            collection_factory=self._collection_factory,
            **params,
        )

    def _build_hybrid_strategy(
        self,
        retrieval_config: RetrievalConfig,
        params: Dict[str, Any],
        collection_factory: Optional[Any] = None,
    ) -> Any:
        """Costruisce HybridRetrieval con le dipendenze iniettate."""
        from knowledge_base.strategies.retrieval import HybridRetrieval

        # Estrai parametri per la fusione
        fusion = params.pop("fusion", "rrf")
        dense_weight = params.pop("dense_weight", 0.7)
        sparse_weight = params.pop("sparse_weight", 0.3)
        rrf_k = params.pop("rrf_k", 60)

        # Costruisci le componenti
        dense = self._build_dense_strategy(retrieval_config, dict(params), collection_factory)
        sparse = self._build_sparse_strategy(dict(params))

        return HybridRetrieval(
            dense=dense,
            sparse=sparse,
            fusion=fusion,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            rrf_k=rrf_k,
        )

    def _run_post_retrieval(
        self,
        query: str,
        results: List[RetrievalResult],
        post_config: PostRetrievalConfig,
        top_k: int,
    ) -> List[RetrievalResult]:
        """Esegue la fase di post-retrieval con fallback."""
        method = post_config.method
        params = dict(post_config.params)

        if not post_retrieval_registry.contains(method):
            logger.warning(
                "Post-retrieval strategy '%s' non trovata, fallback a identity",
                method,
            )
            return results[:top_k]

        strategy_cls = post_retrieval_registry.get(method)

        # Se richiede LLM, iniettalo
        if getattr(strategy_cls, "requires_llm", False):
            model_name = params.pop("model", "mock/echo")
            llm = self._get_llm(model_name)
            if llm is None:
                logger.warning(
                    "Post-retrieval '%s' richiede LLM '%s' non disponibile, "
                    "fallback a identity",
                    method,
                    model_name,
                )
                return results[:top_k]
            params["llm"] = llm

        # Se richiede embedder (per mmr), iniettalo
        if method == "mmr" and "embedder" not in params:
            if self._embedder_factory:
                model_name = params.pop(
                    "model", "BAAI/bge-m3"
                )
                try:
                    params["embedder"] = self._embedder_factory(model_name)
                except Exception:
                    logger.warning(
                        "Post-retrieval '%s': embedder non disponibile, "
                        "fallback a identity",
                        method,
                    )
                    return results[:top_k]

        try:
            strategy = strategy_cls(**params)
            return strategy.rerank(query, results, top_k)
        except Exception as exc:
            logger.warning(
                "Post-retrieval '%s' fallito: %s, fallback a identity",
                method,
                exc,
            )
            return results[:top_k]
