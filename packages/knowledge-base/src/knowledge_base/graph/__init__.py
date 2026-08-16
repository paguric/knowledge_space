"""Graph RAG module for Knowledge Space (refactor-001).

Pipeline: KSChunkLoader → EntityRelationExtractor (LLM) → Neo4jWriter →
ExactMatchResolver. Un solo retriever (HybridCypher), nessuno schema
persistente (derivato dal DB), dipendenze heavy (neo4j) lazy-importate.
"""

from knowledge_base.graph.store import (
    GraphStore,
    MockGraphStore,
    Neo4jGraphStore,
    graph_store_factory,
)
from knowledge_base.graph.schema import derive_schema_info, format_schema
from knowledge_base.graph.extraction import (
    EntityRelationExtractor,
    GraphExtractionResult,
    ExtractedNode,
    ExtractedEdge,
)
from knowledge_base.graph.resolver import ExactMatchResolver
from knowledge_base.graph.writer import Neo4jWriter
from knowledge_base.graph.chunk_loader import KSChunkLoader, TextChunk
from knowledge_base.graph.retriever import (
    GraphRetriever,
    GraphSearchResult,
    HybridCypherRetriever,
)

__all__ = [
    # Store
    "GraphStore",
    "MockGraphStore",
    "Neo4jGraphStore",
    "graph_store_factory",
    # Schema derivato
    "derive_schema_info",
    "format_schema",
    # Extraction
    "EntityRelationExtractor",
    "GraphExtractionResult",
    "ExtractedNode",
    "ExtractedEdge",
    # Resolver
    "ExactMatchResolver",
    # Writer
    "Neo4jWriter",
    # Chunk loader
    "KSChunkLoader",
    "TextChunk",
    # Retriever
    "GraphRetriever",
    "GraphSearchResult",
    "HybridCypherRetriever",
]
