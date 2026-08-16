"""Graph retriever: un solo retriever (refactor-001).

``HybridCypherRetriever``: vector + full-text (somma punteggi) +
traversal ``[:MENTIONS]``. Supporta il filtro ``active_base_names``
sulle proprietà ``base_name`` dei nodi Chunk (invariante 2: la ricerca
sul grafo rispetta le basi attive come la ricerca vettoriale).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Modelli
# --------------------------------------------------------------------------- #


class GraphSearchResult:
    """Singolo risultato di ricerca su grafo."""

    def __init__(
        self,
        chunk_id: str,
        text: str,
        score: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.chunk_id = chunk_id
        self.text = text
        self.score = score
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return (
            f"GraphSearchResult(chunk_id={self.chunk_id!r}, "
            f"score={self.score:.4f}, text={self.text[:50]!r}...)"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GraphSearchResult):
            return NotImplemented
        return self.chunk_id == other.chunk_id and self.score == other.score

    def __hash__(self) -> int:
        return hash((self.chunk_id, self.score))


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #


class GraphRetriever(Protocol):
    """Interfaccia per retriever su grafo."""

    name: str

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        active_base_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[GraphSearchResult]:
        """Esegue la ricerca sul grafo.

        Args:
            query: query testuale.
            top_k: numero massimo di risultati.
            active_base_names: se non ``None``, restringe i risultati ai
                chunk delle sole basi elencate.
        """
        ...


# --------------------------------------------------------------------------- #
# Implementazione
# --------------------------------------------------------------------------- #

# Costanti (refactor-001: niente config, nomi fissi per workspace).
_VECTOR_INDEX = "chunk-embeddings"
_FULLTEXT_INDEX = "chunk-text"

# Traversal di default: entità menzionate dal chunk (OPTIONAL: un chunk
# senza MENTIONS — es. estrazione LLM fallita — resta comunque un
# risultato di ricerca).
_DEFAULT_RETRIEVAL_QUERY = """
WITH node, combinedScore AS score
OPTIONAL MATCH (node)-[:MENTIONS]->(e)
RETURN node.chunk_id AS chunk_id, node.text AS text, score,
       collect(DISTINCT e.name) AS entities
"""


class HybridCypherRetriever:
    """Vector + full-text + traversal MENTIONS (unico retriever)."""

    name = "hybrid_cypher"

    def __init__(
        self,
        store: Any,
        embedder: Any,
        vector_index: str = _VECTOR_INDEX,
        fulltext_index: str = _FULLTEXT_INDEX,
        retrieval_query: str = _DEFAULT_RETRIEVAL_QUERY,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._vector_index = vector_index
        self._fulltext_index = fulltext_index
        self._retrieval_query = retrieval_query

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        active_base_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[GraphSearchResult]:
        """Ricerca ibrida con filtro opzionale sulle basi attive.

        ``active_base_names=None`` → nessun filtro (compatibilità test).
        """
        query_embedding = self._embedder.embed([query])[0]

        # Filtro sui chunk per base_name (prima del traversal).
        if active_base_names:
            base_filter = "WHERE base IN $active_base_names"
        else:
            base_filter = ""

        cypher = f"""
        CALL db.index.vector.queryNodes($vector_index, $top_k, $embedding)
        YIELD node AS vectorNode, score AS vectorScore
        WITH collect({{node: vectorNode, score: vectorScore}}) AS vectorResults

        CALL db.index.fulltext.queryNodes($fulltext_index, $query)
        YIELD node AS textNode, score AS textScore
        WITH vectorResults, collect({{node: textNode, score: textScore}}) AS textResults

        WITH vectorResults + textResults AS allResults
        UNWIND allResults AS result
        WITH result.node AS node, result.score AS score,
             result.node.base_name AS base
        {base_filter}
        WITH node, sum(score) AS combinedScore
        {self._retrieval_query}
        ORDER BY score DESC
        LIMIT $top_k
        """
        parameters: Dict[str, Any] = {
            "vector_index": self._vector_index,
            "fulltext_index": self._fulltext_index,
            "top_k": top_k,
            "embedding": query_embedding,
            "query": query,
        }
        if active_base_names:
            parameters["active_base_names"] = active_base_names

        results = self._store.execute_query(cypher, parameters)
        return [
            GraphSearchResult(
                chunk_id=r.get("chunk_id", ""),
                text=r.get("text", ""),
                score=r.get("score", 0.0),
                metadata={"entities": r.get("entities", [])},
            )
            for r in results
        ]
