"""Test per il modulo graph (Step 8-bis — Pipeline GraphRAG, Fase 1C).

Test mock per GraphStore, extraction, resolution, writer, chunk_loader
e retriever. Test integrazione con Neo4j opzionali (marker ``@pytest.mark.neo4j``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from knowledge_base.graph.store import (
    MockGraphStore,
    Neo4jGraphStore,
    graph_store_factory,
)
from knowledge_base.graph.schema import (
    EdgeSchema,
    GraphSchema,
    NodeSchema,
    PropertySchema,
)
from knowledge_base.graph.extraction import (
    EntityRelationExtractor,
    ExtractedEdge,
    ExtractedNode,
    GraphExtractionResult,
)
from knowledge_base.graph.resolver import (
    ExactMatchResolver,
    SpaCySemanticMatchResolver,
    resolver_factory,
)
from knowledge_base.graph.writer import Neo4jWriter
from knowledge_base.graph.chunk_loader import KSChunkLoader, TextChunk, TextChunks
from knowledge_base.graph.retriever import (
    GraphSearchResult,
    HybridCypherRetriever,
    HybridRetriever,
    RetrieverFactory,
    Text2CypherRetriever,
    ToolsRetriever,
    VectorCypherRetriever,
    VectorRetriever,
)
from knowledge_base.strategies.llm import MockEchoLLM, MockFixedLLM
from knowledge_base.strategies import EmbeddingMetadata


# --------------------------------------------------------------------------- #
# Stub embedder per test
# --------------------------------------------------------------------------- #


class StubEmbedder:
    """Embedder fittizio: restituisce vettori deterministici."""

    name = "stub"
    metadata = EmbeddingMetadata(
        model_name="stub",
        languages=["en"],
        dim=4,
        max_context_tokens=512,
        license="MIT",
        requires_api=False,
    )

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Restituisce vettori di dimensione 4 basati sulla lunghezza del testo."""
        return [[float(len(t)), 0.0, 0.0, 1.0] for t in texts]


# --------------------------------------------------------------------------- #
# Test GraphStore
# --------------------------------------------------------------------------- #


class TestGraphStoreFactory:
    """Test per la factory di GraphStore."""

    def test_factory_mock(self):
        store = graph_store_factory(backend="mock")
        assert isinstance(store, MockGraphStore)
        assert not store.is_connected()

    def test_factory_neo4j(self):
        store = graph_store_factory(
            backend="neo4j",
            uri="bolt://localhost:7687",
            user="neo4j",
            password="test",
        )
        assert isinstance(store, Neo4jGraphStore)
        assert not store.is_connected()

    def test_factory_unknown_backend(self):
        with pytest.raises(ValueError, match="non supportato"):
            graph_store_factory(backend="unknown")

    def test_factory_default_backend(self):
        store = graph_store_factory()
        assert isinstance(store, Neo4jGraphStore)


class TestMockGraphStore:
    """Test per MockGraphStore."""

    def test_connect_disconnect(self):
        store = MockGraphStore()
        assert not store.is_connected()
        store.connect()
        assert store.is_connected()
        store.close()
        assert not store.is_connected()

    def test_execute_query_records(self):
        store = MockGraphStore()
        store.connect()
        store.set_query_results([[{"n": 1}, {"n": 2}]])
        result = store.execute_query("MATCH (n) RETURN n")
        assert len(result) == 2
        assert result[0]["n"] == 1
        assert len(store.executed_queries) == 1

    def test_execute_write_records(self):
        store = MockGraphStore()
        store.connect()
        store.execute_write("CREATE (n:Test {name: 'x'})")
        assert len(store.write_queries) == 1

    def test_verify_connectivity(self):
        store = MockGraphStore()
        assert not store.verify_connectivity()
        store.connect()
        assert store.verify_connectivity()


# --------------------------------------------------------------------------- #
# Test GraphSchema
# --------------------------------------------------------------------------- #


class TestGraphSchema:
    """Test per GraphSchema."""

    def test_default_schema(self):
        schema = GraphSchema()
        assert schema.schema_type == "FREE"
        assert schema.nodes == []
        assert schema.edges == []

    def test_free_schema(self):
        schema = GraphSchema.free()
        assert schema.schema_type == "FREE"

    def test_default_lexical_schema(self):
        schema = GraphSchema.default_lexical()
        assert schema.schema_type == "manuale"
        assert "Document" in schema.get_node_labels()
        assert "Chunk" in schema.get_node_labels()
        assert "FROM_DOCUMENT" in schema.get_edge_types()
        assert "NEXT_CHUNK" in schema.get_edge_types()

    def test_save_and_load(self, tmp_path):
        schema = GraphSchema(
            nodes=[
                NodeSchema(label="Person", properties=[
                    PropertySchema(name="name", type="string", required=True)
                ])
            ],
            edges=[
                EdgeSchema(type="KNOWS", source_label="Person", target_label="Person")
            ],
            schema_type="manuale",
        )
        path = tmp_path / "schema.json"
        schema.save(path)

        loaded = GraphSchema.from_file(path)
        assert loaded.schema_type == "manuale"
        assert len(loaded.nodes) == 1
        assert loaded.nodes[0].label == "Person"
        assert len(loaded.edges) == 1
        assert loaded.edges[0].type == "KNOWS"

    def test_from_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            GraphSchema.from_file(tmp_path / "nonexistent.json")

    def test_from_file_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            GraphSchema.from_file(path)

    def test_get_node_schema(self):
        schema = GraphSchema.default_lexical()
        chunk = schema.get_node_schema("Chunk")
        assert chunk is not None
        assert chunk.label == "Chunk"
        assert schema.get_node_schema("NonExistent") is None

    def test_get_edge_schema(self):
        schema = GraphSchema.default_lexical()
        edge = schema.get_edge_schema("FROM_DOCUMENT")
        assert edge is not None
        assert edge.type == "FROM_DOCUMENT"


# --------------------------------------------------------------------------- #
# Test EntityRelationExtractor
# --------------------------------------------------------------------------- #


class TestEntityRelationExtractor:
    """Test per EntityRelationExtractor."""

    def test_extract_empty_text(self):
        llm = MockFixedLLM()
        extractor = EntityRelationExtractor(llm=llm)
        result = extractor.extract("")
        assert result.nodes == []
        assert result.edges == []

    def test_extract_valid_json(self):
        llm = MockFixedLLM()
        # Override generate per restituire JSON valido
        original_generate = llm.generate

        def mock_generate(messages, **kwargs):
            return json.dumps({
                "nodes": [
                    {"id": "n1", "label": "Person", "name": "Alice", "properties": {}},
                    {"id": "n2", "label": "Company", "name": "Acme", "properties": {}},
                ],
                "edges": [
                    {"source_id": "n1", "target_id": "n2", "type": "WORKS_AT", "properties": {}},
                ],
            })

        llm.generate = mock_generate
        extractor = EntityRelationExtractor(llm=llm)
        result = extractor.extract("Alice works at Acme.", chunk_id="base::fid::0")

        assert len(result.nodes) == 2
        assert result.nodes[0].name == "Alice"
        assert result.nodes[0].label == "Person"
        assert result.nodes[0].chunk_id == "base::fid::0"
        assert len(result.edges) == 1
        assert result.edges[0].type == "WORKS_AT"

    def test_extract_json_with_markdown_fences(self):
        llm = MockFixedLLM()

        def mock_generate(messages, **kwargs):
            return '```json\n{"nodes": [{"id": "n1", "label": "Thing", "name": "X", "properties": {}}], "edges": []}\n```'

        llm.generate = mock_generate
        extractor = EntityRelationExtractor(llm=llm)
        result = extractor.extract("Some text")
        assert len(result.nodes) == 1
        assert result.nodes[0].name == "X"

    def test_extract_invalid_json_returns_empty(self):
        llm = MockFixedLLM()

        def mock_generate(messages, **kwargs):
            return "This is not JSON at all"

        llm.generate = mock_generate
        extractor = EntityRelationExtractor(llm=llm)
        result = extractor.extract("Some text")
        # Should return empty result on invalid JSON
        assert result.nodes == []
        assert result.edges == []

    def test_extract_batch(self):
        llm = MockFixedLLM()
        call_count = 0

        def mock_generate(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            return json.dumps({
                "nodes": [{"id": f"n{call_count}", "label": "Thing", "name": f"Entity{call_count}", "properties": {}}],
                "edges": [],
            })

        llm.generate = mock_generate
        extractor = EntityRelationExtractor(llm=llm)
        result = extractor.extract_batch([
            {"text": "Text 1", "chunk_id": "c1"},
            {"text": "Text 2", "chunk_id": "c2"},
        ])
        assert len(result.nodes) == 2
        assert call_count == 2

    def test_merge_results(self):
        r1 = GraphExtractionResult(
            nodes=[ExtractedNode(id="n1", label="A", name="X")],
            edges=[],
        )
        r2 = GraphExtractionResult(
            nodes=[ExtractedNode(id="n2", label="B", name="Y")],
            edges=[ExtractedEdge(source_id="n1", target_id="n2", type="REL")],
        )
        merged = r1.merge(r2)
        assert len(merged.nodes) == 2
        assert len(merged.edges) == 1

    def test_extract_json_from_text(self):
        # Test the static _extract_json helper
        text = 'Some text ```json\n{"nodes": [], "edges": []}\n``` more text'
        result = EntityRelationExtractor._extract_json(text)
        assert '"nodes"' in result

    def test_extract_json_object_from_text(self):
        text = 'Here is the result: {"nodes": [], "edges": []} done.'
        result = EntityRelationExtractor._extract_json(text)
        assert result.startswith("{")


# --------------------------------------------------------------------------- #
# Test Entity Resolution
# --------------------------------------------------------------------------- #


class TestExactMatchResolver:
    """Test per ExactMatchResolver."""

    def test_no_duplicates(self):
        resolver = ExactMatchResolver()
        entities = [
            {"id": "n1", "label": "Person", "name": "Alice"},
            {"id": "n2", "label": "Person", "name": "Bob"},
        ]
        result = resolver.resolve(entities)
        assert result["n1"] == "n1"
        assert result["n2"] == "n2"

    def test_exact_duplicate(self):
        resolver = ExactMatchResolver()
        entities = [
            {"id": "n1", "label": "Person", "name": "Alice"},
            {"id": "n2", "label": "Person", "name": "Alice"},
        ]
        result = resolver.resolve(entities)
        assert result["n1"] == result["n2"]  # Same canonical

    def test_case_insensitive(self):
        resolver = ExactMatchResolver()
        entities = [
            {"id": "n1", "label": "Person", "name": "Alice"},
            {"id": "n2", "label": "Person", "name": "alice"},
        ]
        result = resolver.resolve(entities)
        assert result["n1"] == result["n2"]

    def test_different_labels_not_merged(self):
        resolver = ExactMatchResolver()
        entities = [
            {"id": "n1", "label": "Person", "name": "Neo4j"},
            {"id": "n2", "label": "Company", "name": "Neo4j"},
        ]
        result = resolver.resolve(entities)
        assert result["n1"] != result["n2"]

    def test_empty_entities(self):
        resolver = ExactMatchResolver()
        result = resolver.resolve([])
        assert result == {}


class TestSpaCySemanticMatchResolver:
    """Test per SpaCySemanticMatchResolver (mock)."""

    def test_resolve_basic(self):
        # SpaCySemanticMatchResolver may not be available, test fallback
        try:
            resolver = SpaCySemanticMatchResolver()
            entities = [
                {"id": "n1", "label": "Person", "name": "Alice"},
                {"id": "n2", "label": "Person", "name": "Alice Smith"},
            ]
            result = resolver.resolve(entities)
            assert "n1" in result
            assert "n2" in result
        except ImportError:
            pytest.skip("spaCy non disponibile")


class TestResolverFactory:
    """Test per la factory dei resolver."""

    def test_factory_exact(self):
        resolver = resolver_factory("exact")
        assert isinstance(resolver, ExactMatchResolver)

    def test_factory_none(self):
        resolver = resolver_factory("none")
        result = resolver.resolve([{"id": "n1", "label": "X", "name": "Y"}])
        assert result["n1"] == "n1"

    def test_factory_unknown(self):
        with pytest.raises(ValueError, match="non supportato"):
            resolver_factory("unknown")

    def test_factory_semantic_fallback(self):
        # Se spaCy non è disponibile, dovrebbe fare fallback a exact
        try:
            resolver = resolver_factory("semantic")
            assert isinstance(resolver, (ExactMatchResolver, SpaCySemanticMatchResolver))
        except ImportError:
            pytest.skip("spaCy non disponibile")


# --------------------------------------------------------------------------- #
# Test Neo4jWriter
# --------------------------------------------------------------------------- #


class TestNeo4jWriter:
    """Test per Neo4jWriter con MockGraphStore."""

    def test_write_nodes(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)

        nodes = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        count = writer.write_nodes(nodes, label="Person")
        assert count == 2
        assert len(store.write_queries) == 1
        assert "UNWIND" in store.write_queries[0][0]
        assert "Person" in store.write_queries[0][0]

    def test_write_nodes_empty(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)
        count = writer.write_nodes([], label="Person")
        assert count == 0
        assert len(store.write_queries) == 0

    def test_write_edges(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)

        edges = [
            {"source_name": "Alice", "target_name": "Acme", "properties": {"since": 2020}},
        ]
        count = writer.write_edges(
            edges,
            source_label="Person",
            target_label="Company",
            edge_type="WORKS_AT",
        )
        assert count == 1
        assert len(store.write_queries) == 1
        assert "WORKS_AT" in store.write_queries[0][0]

    def test_delete_chunks(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)

        count = writer.delete_chunks(["base::fid::0", "base::fid::1"])
        assert count == 2
        assert len(store.write_queries) == 1
        assert "DETACH DELETE" in store.write_queries[0][0]

    def test_delete_chunks_empty(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)
        count = writer.delete_chunks([])
        assert count == 0

    def test_delete_file_nodes(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)
        writer.delete_file_nodes("abc-123")
        assert len(store.write_queries) == 1

    def test_update_chunk_file_name(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)
        writer.update_chunk_file_name("file-id", "new_name.md")
        assert len(store.write_queries) == 1
        assert "file_name" in store.write_queries[0][0]

    def test_update_chunk_embeddings(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)
        writer.update_chunk_embeddings([
            {"chunk_id": "base::fid::0", "embedding": [0.1, 0.2]},
            {"chunk_id": "base::fid::1", "embedding": [0.3, 0.4]},
        ])
        assert len(store.write_queries) == 1

    def test_update_chunk_embeddings_empty(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)
        writer.update_chunk_embeddings([])
        assert len(store.write_queries) == 0

    def test_create_vector_index(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)
        writer.create_vector_index(index_name="test-idx", dimensions=768)
        assert len(store.write_queries) == 1
        assert "VECTOR INDEX" in store.write_queries[0][0]

    def test_create_fulltext_index(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)
        writer.create_fulltext_index(index_name="test-ft", label="Chunk")
        assert len(store.write_queries) == 1
        assert "FULLTEXT INDEX" in store.write_queries[0][0]

    def test_update_properties(self):
        store = MockGraphStore()
        store.connect()
        writer = Neo4jWriter(store)
        writer.update_properties("Person", "name", "Alice", {"age": 31})
        assert len(store.write_queries) == 1


# --------------------------------------------------------------------------- #
# Test KSChunkLoader
# --------------------------------------------------------------------------- #


class TestKSChunkLoader:
    """Test per KSChunkLoader."""

    def test_load_file_empty_dir(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        loader = KSChunkLoader(chunks_dir=chunks_dir)
        result = loader.load_file("nonexistent-id", base_name="test")
        assert result.chunks == []

    def test_load_file_with_chunks(self, tmp_path):
        # Crea chunk su disco
        chunks_dir = tmp_path / "chunks"
        file_id = "abc123"
        chunk_dir = chunks_dir / file_id
        chunk_dir.mkdir(parents=True)

        (chunk_dir / f"{file_id}_chunk_0.md").write_text("First chunk")
        (chunk_dir / f"{file_id}_chunk_1.md").write_text("Second chunk")
        (chunk_dir / f"{file_id}_chunk_2.md").write_text("Third chunk")

        loader = KSChunkLoader(chunks_dir=chunks_dir)
        result = loader.load_file(file_id, base_name="mybase", file_name="doc.md")

        assert len(result.chunks) == 3
        assert result.chunks[0].text == "First chunk"
        assert result.chunks[0].chunk_id == "mybase::abc123::0"
        assert result.chunks[0].chunk_index == 0
        assert result.chunks[1].text == "Second chunk"
        assert result.chunks[1].chunk_id == "mybase::abc123::1"
        assert result.chunks[2].text == "Third chunk"
        assert result.document_info["file_id"] == file_id
        assert result.document_info["base_name"] == "mybase"

    def test_load_file_ordering(self, tmp_path):
        """Verifica che i chunk siano ordinati per indice."""
        chunks_dir = tmp_path / "chunks"
        file_id = "xyz"
        chunk_dir = chunks_dir / file_id
        chunk_dir.mkdir(parents=True)

        # Crea fuori ordine
        (chunk_dir / f"{file_id}_chunk_2.md").write_text("C")
        (chunk_dir / f"{file_id}_chunk_0.md").write_text("A")
        (chunk_dir / f"{file_id}_chunk_1.md").write_text("B")

        loader = KSChunkLoader(chunks_dir=chunks_dir)
        result = loader.load_file(file_id, base_name="base")

        assert result.chunks[0].text == "A"
        assert result.chunks[1].text == "B"
        assert result.chunks[2].text == "C"

    def test_load_file_with_embedding_collection(self, tmp_path):
        """Test caricamento con embedding da collection mockata."""
        chunks_dir = tmp_path / "chunks"
        file_id = "fid1"
        chunk_dir = chunks_dir / file_id
        chunk_dir.mkdir(parents=True)
        (chunk_dir / f"{file_id}_chunk_0.md").write_text("Hello")

        # Mock collection
        class MockCollection:
            def get(self, ids, include=None):
                return {"embeddings": [[0.1, 0.2, 0.3]]}

        loader = KSChunkLoader(chunks_dir=chunks_dir, chroma_collection=MockCollection())
        result = loader.load_file(file_id, base_name="base")
        assert result.chunks[0].embedding == [0.1, 0.2, 0.3]

    def test_upsert_chunks(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        loader = KSChunkLoader(chunks_dir=chunks_dir)

        changed = [
            {"index": 0, "text": "Updated chunk 0", "content_hash": "h0"},
            {"index": 2, "text": "New chunk 2", "content_hash": "h2"},
        ]
        result = loader.upsert_chunks("base", "file-id", changed)
        assert len(result.chunks) == 2
        assert result.chunks[0].chunk_id == "base::file-id::0"
        assert result.chunks[0].text == "Updated chunk 0"
        assert result.chunks[1].chunk_id == "base::file-id::2"

    def test_load_base(self, tmp_path):
        """Test caricamento di un'intera base."""
        chunks_dir = tmp_path / "chunks"

        # Crea chunk per 2 file
        for fid in ["f1", "f2"]:
            d = chunks_dir / fid
            d.mkdir(parents=True)
            (d / f"{fid}_chunk_0.md").write_text(f"Chunk 0 of {fid}")

        # Mock FileEntry
        class MockFileEntry:
            def __init__(self, fid, active=True):
                self.file_id = fid
                self.active = active

        files = {
            "doc1.md": MockFileEntry("f1"),
            "doc2.md": MockFileEntry("f2"),
            "inactive.md": MockFileEntry("f3", active=False),
        }

        loader = KSChunkLoader(chunks_dir=chunks_dir)
        result = loader.load_base("mybase", files)
        assert len(result.chunks) == 2  # f3 is inactive

    def test_text_chunk_model(self):
        chunk = TextChunk(
            chunk_id="base::fid::0",
            text="Hello",
            base_name="base",
            file_name="doc.md",
            file_id="fid",
            chunk_index=0,
        )
        assert chunk.chunk_id == "base::fid::0"
        assert chunk.text == "Hello"

    def test_text_chunks_model(self):
        tc = TextChunks(
            chunks=[TextChunk(chunk_id="c1", text="t1")],
            document_info={"file_id": "f1"},
        )
        assert len(tc.chunks) == 1
        assert tc.document_info["file_id"] == "f1"


# --------------------------------------------------------------------------- #
# Test GraphRetriever
# --------------------------------------------------------------------------- #


class TestVectorRetriever:
    """Test per VectorRetriever."""

    def test_search(self):
        store = MockGraphStore()
        store.connect()
        store.set_query_results([
            [
                {"node.chunk_id": "c1", "node.text": "text1", "score": 0.9},
                {"node.chunk_id": "c2", "node.text": "text2", "score": 0.8},
            ]
        ])

        embedder = StubEmbedder()
        retriever = VectorRetriever(store=store, embedder=embedder)
        results = retriever.search("query", top_k=2)

        assert len(results) == 2
        assert results[0].chunk_id == "c1"
        assert results[0].score == 0.9
        assert results[1].chunk_id == "c2"

    def test_name(self):
        store = MockGraphStore()
        embedder = StubEmbedder()
        retriever = VectorRetriever(store=store, embedder=embedder)
        assert retriever.name == "vector"


class TestVectorCypherRetriever:
    """Test per VectorCypherRetriever."""

    def test_search(self):
        store = MockGraphStore()
        store.connect()
        store.set_query_results([
            [
                {"chunk_id": "c1", "text": "text1", "score": 0.9, "entities": ["Neo4j"]},
            ]
        ])

        embedder = StubEmbedder()
        retriever = VectorCypherRetriever(store=store, embedder=embedder)
        results = retriever.search("query", top_k=1)

        assert len(results) == 1
        assert results[0].metadata.get("entities") == ["Neo4j"]

    def test_name(self):
        assert VectorCypherRetriever.__init__.__code__.co_varnames  # Just verify it exists
        store = MockGraphStore()
        embedder = StubEmbedder()
        retriever = VectorCypherRetriever(store=store, embedder=embedder)
        assert retriever.name == "vector_cypher"


class TestHybridRetriever:
    """Test per HybridRetriever."""

    def test_search(self):
        store = MockGraphStore()
        store.connect()
        store.set_query_results([
            [{"chunk_id": "c1", "text": "text1", "score": 1.5}],
        ])

        embedder = StubEmbedder()
        retriever = HybridRetriever(store=store, embedder=embedder)
        results = retriever.search("query")
        assert len(results) == 1

    def test_name(self):
        store = MockGraphStore()
        embedder = StubEmbedder()
        retriever = HybridRetriever(store=store, embedder=embedder)
        assert retriever.name == "hybrid"


class TestHybridCypherRetriever:
    """Test per HybridCypherRetriever."""

    def test_search(self):
        store = MockGraphStore()
        store.connect()
        store.set_query_results([
            [{"chunk_id": "c1", "text": "text1", "score": 1.5, "entities": ["E1"]}],
        ])

        embedder = StubEmbedder()
        retriever = HybridCypherRetriever(store=store, embedder=embedder)
        results = retriever.search("query")
        assert len(results) == 1

    def test_name(self):
        store = MockGraphStore()
        embedder = StubEmbedder()
        retriever = HybridCypherRetriever(store=store, embedder=embedder)
        assert retriever.name == "hybrid_cypher"


class TestText2CypherRetriever:
    """Test per Text2CypherRetriever."""

    def test_search(self):
        store = MockGraphStore()
        store.connect()
        llm = MockFixedLLM()

        def mock_generate(messages, **kwargs):
            return "MATCH (c:Chunk) RETURN c.chunk_id AS chunk_id, c.text AS text, 1.0 AS score LIMIT 5"

        llm.generate = mock_generate
        store.set_query_results([
            [{"chunk_id": "c1", "text": "text1", "score": 1.0}],
        ])

        retriever = Text2CypherRetriever(store=store, llm=llm)
        results = retriever.search("What is Neo4j?")
        assert len(results) == 1

    def test_name(self):
        store = MockGraphStore()
        llm = MockFixedLLM()
        retriever = Text2CypherRetriever(store=store, llm=llm)
        assert retriever.name == "text2cypher"


class TestToolsRetriever:
    """Test per ToolsRetriever."""

    def test_search_returns_empty(self):
        store = MockGraphStore()
        llm = MockFixedLLM()
        retriever = ToolsRetriever(store=store, llm=llm)
        results = retriever.search("query")
        assert results == []

    def test_name(self):
        store = MockGraphStore()
        llm = MockFixedLLM()
        retriever = ToolsRetriever(store=store, llm=llm)
        assert retriever.name == "tools"


class TestGraphSearchResult:
    """Test per GraphSearchResult."""

    def test_repr(self):
        r = GraphSearchResult(chunk_id="c1", text="hello world", score=0.95)
        assert "c1" in repr(r)
        assert "0.9500" in repr(r)

    def test_eq(self):
        r1 = GraphSearchResult(chunk_id="c1", text="t", score=0.9)
        r2 = GraphSearchResult(chunk_id="c1", text="t", score=0.9)
        r3 = GraphSearchResult(chunk_id="c2", text="t", score=0.9)
        assert r1 == r2
        assert r1 != r3
        assert r1 != "not a result"

    def test_hash(self):
        r1 = GraphSearchResult(chunk_id="c1", text="t", score=0.9)
        r2 = GraphSearchResult(chunk_id="c1", text="t", score=0.9)
        assert hash(r1) == hash(r2)


class TestRetrieverFactory:
    """Test per RetrieverFactory."""

    def test_build_vector(self):
        store = MockGraphStore()
        embedder = StubEmbedder()
        retriever = RetrieverFactory.build("vector", store=store, embedder=embedder)
        assert isinstance(retriever, VectorRetriever)

    def test_build_vector_cypher(self):
        store = MockGraphStore()
        embedder = StubEmbedder()
        retriever = RetrieverFactory.build("vector_cypher", store=store, embedder=embedder)
        assert isinstance(retriever, VectorCypherRetriever)

    def test_build_hybrid(self):
        store = MockGraphStore()
        embedder = StubEmbedder()
        retriever = RetrieverFactory.build("hybrid", store=store, embedder=embedder)
        assert isinstance(retriever, HybridRetriever)

    def test_build_hybrid_cypher(self):
        store = MockGraphStore()
        embedder = StubEmbedder()
        retriever = RetrieverFactory.build("hybrid_cypher", store=store, embedder=embedder)
        assert isinstance(retriever, HybridCypherRetriever)

    def test_build_text2cypher(self):
        store = MockGraphStore()
        llm = MockFixedLLM()
        retriever = RetrieverFactory.build("text2cypher", store=store, llm=llm)
        assert isinstance(retriever, Text2CypherRetriever)

    def test_build_tools(self):
        store = MockGraphStore()
        llm = MockFixedLLM()
        retriever = RetrieverFactory.build("tools", store=store, llm=llm)
        assert isinstance(retriever, ToolsRetriever)

    def test_build_unknown(self):
        store = MockGraphStore()
        with pytest.raises(ValueError, match="non supportato"):
            RetrieverFactory.build("unknown", store=store)

    def test_build_vector_requires_embedder(self):
        store = MockGraphStore()
        with pytest.raises(ValueError, match="embedder"):
            RetrieverFactory.build("vector", store=store, embedder=None)

    def test_build_text2cypher_requires_llm(self):
        store = MockGraphStore()
        embedder = StubEmbedder()
        with pytest.raises(ValueError, match="LLM"):
            RetrieverFactory.build("text2cypher", store=store, embedder=embedder, llm=None)


# --------------------------------------------------------------------------- #
# Test BaseConfig con GraphConfig
# --------------------------------------------------------------------------- #


class TestGraphConfig:
    """Test per GraphConfig in BaseConfig."""

    def test_default_graph_config(self):
        from knowledge_base.base_config import BaseConfig, GraphConfig

        config = BaseConfig()
        assert config.graph.enabled is False
        assert config.graph.on_chunk_change == "lazy"
        assert config.graph.retriever == "hybrid_cypher"
        assert config.graph.schema_mode == "FREE"
        assert config.graph.resolver == "exact"
        assert config.graph.extraction_model is None

    def test_graph_config_from_toml(self):
        from knowledge_base.base_config import BaseConfig

        data = {
            "graph": {
                "enabled": True,
                "on_chunk_change": "eager",
                "retriever": "hybrid",
                "schema": "EXTRACTED",
                "extraction_model": "mock/fixed",
            }
        }
        config = BaseConfig.from_toml(data)
        assert config.graph.enabled is True
        assert config.graph.on_chunk_change == "eager"
        assert config.graph.retriever == "hybrid"
        assert config.graph.schema_mode == "EXTRACTED"
        assert config.graph.extraction_model == "mock/fixed"

    def test_graph_config_override(self):
        from knowledge_base.base_config import BaseConfig

        base = BaseConfig()
        override_data = {"graph": {"enabled": True, "retriever": "vector"}}
        override = BaseConfig.from_toml(override_data)
        merged = base.override(override)
        assert merged.graph.enabled is True
        assert merged.graph.retriever == "vector"
        # Non-overridden fields keep default
        assert merged.graph.on_chunk_change == "lazy"

    def test_graph_config_unknown_fields_ignored(self, caplog):
        from knowledge_base.base_config import BaseConfig

        data = {"graph": {"unknown_field": "value", "enabled": True}}
        config = BaseConfig.from_toml(data)
        assert config.graph.enabled is True

    def test_graph_config_roundtrip_json(self):
        from knowledge_base.base_config import GraphConfig

        config = GraphConfig(
            enabled=True,
            on_chunk_change="eager",
            retriever="hybrid",
            extraction_model="openai/gpt-4o",
        )
        json_str = config.model_dump_json()
        loaded = GraphConfig.model_validate_json(json_str)
        assert loaded.enabled is True
        assert loaded.retriever == "hybrid"
        assert loaded.extraction_model == "openai/gpt-4o"


# --------------------------------------------------------------------------- #
# Test integrazione Neo4j (opzionale)
# --------------------------------------------------------------------------- #


@pytest.mark.neo4j
class TestNeo4jIntegration:
    """Test di integrazione con Neo4j reale.

    Richiede un'istanza Neo4j in esecuzione. Eseguire con:
        pytest -m neo4j
    """

    def test_connectivity(self):
        store = graph_store_factory(backend="neo4j")
        try:
            store.connect()
            assert store.verify_connectivity()
        except Exception:
            pytest.skip("Neo4j non raggiungibile")
        finally:
            store.close()

    def test_write_and_query(self):
        store = graph_store_factory(backend="neo4j")
        try:
            store.connect()
        except Exception:
            pytest.skip("Neo4j non raggiungibile")

        writer = Neo4jWriter(store)
        try:
            # Write
            writer.write_nodes(
                [{"name": "TestNode", "test_prop": "hello"}],
                label="TestLabel",
            )
            # Query
            results = store.execute_query(
                "MATCH (n:TestLabel {name: $name}) RETURN n.name AS name",
                {"name": "TestNode"},
            )
            assert len(results) == 1
            assert results[0]["name"] == "TestNode"
        finally:
            # Cleanup
            store.execute_write("MATCH (n:TestLabel) DETACH DELETE n")
            store.close()
