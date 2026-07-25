"""Graph RAG module for Knowledge Space.

Provides entity extraction, graph storage, entity resolution,
chunk loading, writing, and retrieval over a Neo4j knowledge graph.

Pipeline: KSChunkLoader → Schema → EntityRelationExtractor → Neo4jWriter → EntityResolver

All heavy dependencies (neo4j, spacy) are lazy-imported at usage time,
so the module can be imported without them installed.
"""

from knowledge_base.graph.store import GraphStore, graph_store_factory
from knowledge_base.graph.schema import GraphSchema, NodeSchema, EdgeSchema
from knowledge_base.graph.extraction import (
    EntityRelationExtractor,
    GraphExtractionResult,
    ExtractedNode,
    ExtractedEdge,
)
from knowledge_base.graph.resolver import (
    EntityResolver,
    ExactMatchResolver,
    SpaCySemanticMatchResolver,
)
from knowledge_base.graph.writer import Neo4jWriter
from knowledge_base.graph.chunk_loader import KSChunkLoader, TextChunk
from knowledge_base.graph.retriever import GraphRetriever, RetrieverFactory

__all__ = [
    # Store
    "GraphStore",
    "graph_store_factory",
    # Schema
    "GraphSchema",
    "NodeSchema",
    "EdgeSchema",
    # Extraction
    "EntityRelationExtractor",
    "GraphExtractionResult",
    "ExtractedNode",
    "ExtractedEdge",
    # Resolver
    "EntityResolver",
    "ExactMatchResolver",
    "SpaCySemanticMatchResolver",
    # Writer
    "Neo4jWriter",
    # Chunk loader
    "KSChunkLoader",
    "TextChunk",
    # Retriever
    "GraphRetriever",
    "RetrieverFactory",
]
