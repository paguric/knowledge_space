"""Graph retriever: strategie di ricerca su grafo Neo4j.

Configurabile via ``[graph].retriever`` per-base. Strategie supportate:

- ``vector``: similarità pura ANN su indice vettoriale
- ``vector_cypher``: vector + traversal Cypher
- ``hybrid``: vector + BM25 full-text
- ``hybrid_cypher``: hybrid + retrieval_query (default)
- ``text2cypher``: LLM genera query Cypher
- ``tools``: LLM seleziona tool

La ``RetrieverFactory`` istanzia la strategy appropriata.
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
        **kwargs: Any,
    ) -> List[GraphSearchResult]:
        """Esegue la ricerca sul grafo.

        Args:
            query: query testuale.
            top_k: numero massimo di risultati.

        Returns:
            Lista ordinata di ``GraphSearchResult``.
        """
        ...


# --------------------------------------------------------------------------- #
# Implementazioni
# --------------------------------------------------------------------------- #


class VectorRetriever:
    """Similarità pura su indice vettoriale Neo4j.

    Args:
        store: GraphStore (Neo4jGraphStore o mock).
        embedder: strategia di embedding per la query.
        index_name: nome dell'indice vettoriale.
        return_properties: proprietà da restituire.
    """

    name = "vector"

    def __init__(
        self,
        store: Any,
        embedder: Any,
        index_name: str = "chunk-embeddings",
        return_properties: Optional[List[str]] = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._index_name = index_name
        self._return_properties = return_properties or ["chunk_id", "text"]

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[GraphSearchResult]:
        query_embedding = self._embedder.embed([query])[0]
        props_str = ", ".join(f"node.{p}" for p in self._return_properties)
        cypher = f"""
        CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
        YIELD node, score
        RETURN {props_str}, score
        ORDER BY score DESC
        """
        results = self._store.execute_query(cypher, {
            "index_name": self._index_name,
            "top_k": top_k,
            "embedding": query_embedding,
        })
        return [
            GraphSearchResult(
                chunk_id=r.get("node.chunk_id", ""),
                text=r.get("node.text", ""),
                score=r.get("score", 0.0),
            )
            for r in results
        ]


class VectorCypherRetriever:
    """Vector + traversal Cypher.

    Args:
        store: GraphStore.
        embedder: strategia di embedding.
        retrieval_query: query Cypher di traversal.
        index_name: nome dell'indice vettoriale.
    """

    name = "vector_cypher"

    def __init__(
        self,
        store: Any,
        embedder: Any,
        retrieval_query: str = "",
        index_name: str = "chunk-embeddings",
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._index_name = index_name
        self._retrieval_query = retrieval_query or """
        WITH node, score
        MATCH (node)-[:MENTIONS]->(e)
        RETURN node.chunk_id AS chunk_id, node.text AS text, score,
               collect(e.name) AS entities
        """

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[GraphSearchResult]:
        query_embedding = self._embedder.embed([query])[0]
        cypher = f"""
        CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
        YIELD node, score
        {self._retrieval_query}
        """
        results = self._store.execute_query(cypher, {
            "index_name": self._index_name,
            "top_k": top_k,
            "embedding": query_embedding,
        })
        return [
            GraphSearchResult(
                chunk_id=r.get("chunk_id", ""),
                text=r.get("text", ""),
                score=r.get("score", 0.0),
                metadata={"entities": r.get("entities", [])},
            )
            for r in results
        ]


class HybridRetriever:
    """Vector + BM25 full-text.

    Args:
        store: GraphStore.
        embedder: strategia di embedding.
        vector_index: nome dell'indice vettoriale.
        fulltext_index: nome dell'indice full-text.
    """

    name = "hybrid"

    def __init__(
        self,
        store: Any,
        embedder: Any,
        vector_index: str = "chunk-embeddings",
        fulltext_index: str = "chunk-text",
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._vector_index = vector_index
        self._fulltext_index = fulltext_index

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[GraphSearchResult]:
        query_embedding = self._embedder.embed([query])[0]
        # Reciprocal Rank Fusion (RRF) di default
        cypher = f"""
        CALL db.index.vector.queryNodes($vector_index, $top_k, $embedding)
        YIELD node AS vectorNode, score AS vectorScore
        WITH collect({{node: vectorNode, score: vectorScore}}) AS vectorResults

        CALL db.index.fulltext.queryNodes($fulltext_index, $query)
        YIELD node AS textNode, score AS textScore
        WITH vectorResults, collect({{node: textNode, score: textScore}}) AS textResults

        WITH vectorResults + textResults AS allResults
        UNWIND allResults AS result
        WITH result.node AS node,
             sum(result.score) AS combinedScore
        RETURN DISTINCT node.chunk_id AS chunk_id,
               node.text AS text,
               combinedScore AS score
        ORDER BY combinedScore DESC
        LIMIT $top_k
        """
        results = self._store.execute_query(cypher, {
            "vector_index": self._vector_index,
            "fulltext_index": self._fulltext_index,
            "top_k": top_k,
            "embedding": query_embedding,
            "query": query,
        })
        return [
            GraphSearchResult(
                chunk_id=r.get("chunk_id", ""),
                text=r.get("text", ""),
                score=r.get("score", 0.0),
            )
            for r in results
        ]


class HybridCypherRetriever:
    """Hybrid + retrieval_query (default per GraphRAG).

    Args:
        store: GraphStore.
        embedder: strategia di embedding.
        retrieval_query: query Cypher di traversal.
        vector_index: nome dell'indice vettoriale.
        fulltext_index: nome dell'indice full-text.
    """

    name = "hybrid_cypher"

    def __init__(
        self,
        store: Any,
        embedder: Any,
        retrieval_query: str = "",
        vector_index: str = "chunk-embeddings",
        fulltext_index: str = "chunk-text",
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._vector_index = vector_index
        self._fulltext_index = fulltext_index
        self._retrieval_query = retrieval_query or """
        WITH node, score
        MATCH (node)-[:MENTIONS]->(e)
        RETURN node.chunk_id AS chunk_id, node.text AS text, score,
               collect(DISTINCT e.name) AS entities
        """

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[GraphSearchResult]:
        query_embedding = self._embedder.embed([query])[0]
        cypher = f"""
        CALL db.index.vector.queryNodes($vector_index, $top_k, $embedding)
        YIELD node AS vectorNode, score AS vectorScore
        WITH collect({{node: vectorNode, score: vectorScore}}) AS vectorResults

        CALL db.index.fulltext.queryNodes($fulltext_index, $query)
        YIELD node AS textNode, score AS textScore
        WITH vectorResults, collect({{node: textNode, score: textScore}}) AS textResults

        WITH vectorResults + textResults AS allResults
        UNWIND allResults AS result
        WITH result.node AS node,
             sum(result.score) AS combinedScore
        {self._retrieval_query}
        ORDER BY score DESC
        LIMIT $top_k
        """
        results = self._store.execute_query(cypher, {
            "vector_index": self._vector_index,
            "fulltext_index": self._fulltext_index,
            "top_k": top_k,
            "embedding": query_embedding,
            "query": query,
        })
        return [
            GraphSearchResult(
                chunk_id=r.get("chunk_id", ""),
                text=r.get("text", ""),
                score=r.get("score", 0.0),
                metadata={"entities": r.get("entities", [])},
            )
            for r in results
        ]


class Text2CypherRetriever:
    """LLM genera query Cypher dalla query naturale.

    Richiede un LLM e uno ``schema.json`` per il contesto.

    Args:
        store: GraphStore.
        llm: strategia LLM.
        schema_text: testo dello schema del grafo (per il prompt).
    """

    name = "text2cypher"

    def __init__(
        self,
        store: Any,
        llm: Any,
        schema_text: str = "",
    ) -> None:
        self._store = store
        self._llm = llm
        self._schema_text = schema_text

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[GraphSearchResult]:
        prompt = f"""Given this Neo4j graph schema:
{self._schema_text}

Convert this question into a Cypher query that returns chunk_id, text, and score.
Return ONLY the Cypher query, no explanation.

Question: {query}"""

        messages = [
            {"role": "system", "content": "You are a Cypher query generator."},
            {"role": "user", "content": prompt},
        ]

        try:
            cypher = self._llm.generate(messages, max_tokens=1024, temperature=0.0)
        except Exception as exc:
            logger.error("Errore generazione Cypher: %s", exc)
            return []

        # Pulisci la query (rimuovi markdown fences se presenti)
        cypher = cypher.strip()
        if cypher.startswith("```"):
            lines = cypher.split("\n")
            cypher = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            results = self._store.execute_query(cypher)
        except Exception as exc:
            logger.error("Errore esecuzione Cypher generato: %s", exc)
            return []

        return [
            GraphSearchResult(
                chunk_id=r.get("chunk_id", ""),
                text=r.get("text", ""),
                score=r.get("score", 1.0),
            )
            for r in results[:top_k]
        ]


class ToolsRetriever:
    """LLM seleziona tool di ricerca.

    Args:
        store: GraphStore.
        llm: strategia LLM.
        tools: lista di tool disponibili.
    """

    name = "tools"

    def __init__(
        self,
        store: Any,
        llm: Any,
        tools: Optional[List[Any]] = None,
    ) -> None:
        self._store = store
        self._llm = llm
        self._tools = tools or []

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[GraphSearchResult]:
        # Fase 1C: implementazione semplificata
        # In futuro, l'LLM selezionerà il tool appropriato
        logger.warning("ToolsRetriever: implementazione base, usa vector come fallback")
        return []


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #


class RetrieverFactory:
    """Factory per retriever su grafo.

    Crea il retriever appropriato in base alla configurazione TOML.
    """

    _RETRIEVERS = {
        "vector": VectorRetriever,
        "vector_cypher": VectorCypherRetriever,
        "hybrid": HybridRetriever,
        "hybrid_cypher": HybridCypherRetriever,
        "text2cypher": Text2CypherRetriever,
        "tools": ToolsRetriever,
    }

    @classmethod
    def build(
        cls,
        retriever_type: str,
        store: Any,
        embedder: Any = None,
        llm: Any = None,
        retrieval_query: str = "",
        vector_index: str = "chunk-embeddings",
        fulltext_index: str = "chunk-text",
        schema_text: str = "",
        **kwargs: Any,
    ) -> GraphRetriever:
        """Crea il retriever appropriato.

        Args:
            retriever_type: tipo di retriever dalla config TOML.
            store: GraphStore.
            embedder: strategia di embedding (per vector/hybrid).
            llm: strategia LLM (per text2cypher/tools).
            retrieval_query: query Cypher di traversal.
            vector_index: nome indice vettoriale.
            fulltext_index: nome indice full-text.
            schema_text: testo schema (per text2cypher).

        Returns:
            Istanza di ``GraphRetriever``.

        Raises:
            ValueError: se il tipo non è supportato o mancano dipendenze.
        """
        if retriever_type not in cls._RETRIEVERS:
            available = ", ".join(sorted(cls._RETRIEVERS))
            raise ValueError(
                f"Retriever '{retriever_type}' non supportato. "
                f"Disponibili: {available}"
            )

        if retriever_type in ("vector", "vector_cypher", "hybrid", "hybrid_cypher"):
            if embedder is None:
                raise ValueError(
                    f"Retriever '{retriever_type}' richiede un embedder."
                )

        if retriever_type in ("text2cypher", "tools"):
            if llm is None:
                raise ValueError(
                    f"Retriever '{retriever_type}' richiede un LLM."
                )

        if retriever_type == "vector":
            return VectorRetriever(
                store=store,
                embedder=embedder,
                index_name=vector_index,
            )
        if retriever_type == "vector_cypher":
            return VectorCypherRetriever(
                store=store,
                embedder=embedder,
                retrieval_query=retrieval_query,
                index_name=vector_index,
            )
        if retriever_type == "hybrid":
            return HybridRetriever(
                store=store,
                embedder=embedder,
                vector_index=vector_index,
                fulltext_index=fulltext_index,
            )
        if retriever_type == "hybrid_cypher":
            return HybridCypherRetriever(
                store=store,
                embedder=embedder,
                retrieval_query=retrieval_query,
                vector_index=vector_index,
                fulltext_index=fulltext_index,
            )
        if retriever_type == "text2cypher":
            return Text2CypherRetriever(
                store=store,
                llm=llm,
                schema_text=schema_text,
            )
        if retriever_type == "tools":
            return ToolsRetriever(
                store=store,
                llm=llm,
            )

        # Non dovrebbe mai arrivare qui
        raise ValueError(f"Retriever '{retriever_type}' non implementato")
