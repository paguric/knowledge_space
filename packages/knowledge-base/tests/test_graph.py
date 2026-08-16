"""Test per il componente grafo (refactor-001).

Copre: store (+schema derivato), estrazione per-name, resolver unico,
writer (mentions/orfane), chunk loader (riciclo/ricalcolo), retriever
unico con filtro attivi, GraphManager (build/sync/remove/status/search,
gating) e GraphSearchService (filtro domini/basi/file/chunk attivi).

Tutto mock: nessun Neo4j reale, nessun download di modelli.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from knowledge_base.base_config import BaseConfig, GraphConfig
from knowledge_base.graph.store import (
    MockGraphStore,
    Neo4jGraphStore,
    graph_store_factory,
)
from knowledge_base.graph.schema import derive_schema_info, format_schema
from knowledge_base.graph.extraction import (
    EntityRelationExtractor,
    ExtractedEdge,
    ExtractedNode,
    GraphExtractionResult,
)
from knowledge_base.graph.resolver import ExactMatchResolver
from knowledge_base.graph.writer import Neo4jWriter
from knowledge_base.graph.chunk_loader import KSChunkLoader, TextChunk, TextChunks
from knowledge_base.graph.retriever import (
    GraphSearchResult,
    HybridCypherRetriever,
)
from knowledge_base.graph_manager import GraphManager
from knowledge_base.graph_search_service import GraphSearchService
from knowledge_base.models import ChunkRef, FileEntry, KnowledgeBase, Workspace
from knowledge_base.strategies.llm import MockFixedLLM
from knowledge_base.strategies import EmbeddingMetadata


# --------------------------------------------------------------------------- #
# Stub embedder
# --------------------------------------------------------------------------- #


class StubEmbedder:
    """Embedder fittizio: vettori deterministici di dimensione 4."""

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
        return [[float(len(t)), 0.0, 0.0, 1.0] for t in texts]


# --------------------------------------------------------------------------- #
# Test store
# --------------------------------------------------------------------------- #


class TestGraphStoreFactory:
    def test_factory_mock(self):
        store = graph_store_factory("mock")
        assert isinstance(store, MockGraphStore)

    def test_factory_neo4j(self, monkeypatch):
        monkeypatch.setenv("NEO4J_URI", "bolt://x:1")
        store = graph_store_factory("neo4j", uri="bolt://y:2", user="u", password="p")
        assert isinstance(store, Neo4jGraphStore)
        assert store._uri == "bolt://y:2"

    def test_factory_unknown_backend(self):
        with pytest.raises(ValueError):
            graph_store_factory("unknown")


class TestMockGraphStore:
    def test_connect_disconnect(self):
        store = MockGraphStore()
        store.connect()
        assert store.is_connected()
        store.close()
        assert not store.is_connected()

    def test_execute_query_records(self):
        store = MockGraphStore()
        store.set_query_results([[{"a": 1}]])
        result = store.execute_query("MATCH (n) RETURN n", {"x": 1})
        assert result == [{"a": 1}]
        assert store.executed_queries[0][0] == "MATCH (n) RETURN n"

    def test_execute_write_records(self):
        store = MockGraphStore()
        store.execute_write("CREATE (n)", {"a": 1})
        assert store.write_queries[0][0] == "CREATE (n)"

    def test_verify_connectivity(self):
        store = MockGraphStore()
        assert not store.verify_connectivity()
        store.connect()
        assert store.verify_connectivity()

    def test_schema_info(self):
        store = MockGraphStore()
        info = store.schema_info()
        assert "Entity" in info["labels"]
        assert "MENTIONS" in info["relationship_types"]


# --------------------------------------------------------------------------- #
# Test schema derivato dal DB
# --------------------------------------------------------------------------- #


class TestDerivedSchema:
    def test_derive_schema_info(self):
        store = MockGraphStore()
        info = derive_schema_info(store)
        assert info["labels"] == ["Document", "Chunk", "Entity"]

    def test_format_schema(self):
        store = MockGraphStore()
        store.schema_data = {
            "labels": ["Chunk", "Entity"],
            "relationship_types": ["MENTIONS"],
            "node_properties": [
                {"nodeLabels": ["Chunk"], "propertyName": "text"}
            ],
        }
        text = format_schema(store)
        assert "Schema del grafo (derivato dal DB)" in text
        assert "Chunk: text" in text
        assert "MENTIONS" in text


# --------------------------------------------------------------------------- #
# Test estrazione (riferimenti per nome)
# --------------------------------------------------------------------------- #


class TestEntityRelationExtractor:
    def test_extract_empty_text(self):
        extractor = EntityRelationExtractor(llm=MockFixedLLM())
        result = extractor.extract("")
        assert result.nodes == []
        assert result.edges == []

    def test_extract_valid_json_by_name(self):
        llm = MockFixedLLM()

        def mock_generate(messages, **kwargs):
            return json.dumps({
                "nodes": [
                    {"name": "Alice", "label": "Persona", "properties": {}},
                    {"name": "Acme", "label": "Organizzazione", "properties": {}},
                ],
                "edges": [
                    {"source": "Alice", "target": "Acme", "type": "LAVORA_PER", "properties": {}},
                ],
            })

        llm.generate = mock_generate
        extractor = EntityRelationExtractor(llm=llm)
        result = extractor.extract("Alice works at Acme.", chunk_id="b::f::0")

        assert len(result.nodes) == 2
        assert result.nodes[0].name == "Alice"
        assert result.nodes[0].label == "Persona"
        assert result.nodes[0].chunk_id == "b::f::0"
        assert len(result.edges) == 1
        assert result.edges[0].source == "Alice"
        assert result.edges[0].target == "Acme"
        assert result.edges[0].type == "LAVORA_PER"

    def test_extract_json_with_markdown_fences(self):
        llm = MockFixedLLM()

        def mock_generate(messages, **kwargs):
            return '```json\n{"nodes": [{"name": "X", "label": "Concetto"}], "edges": []}\n```'

        llm.generate = mock_generate
        extractor = EntityRelationExtractor(llm=llm)
        result = extractor.extract("Some text")
        assert result.nodes[0].name == "X"

    def test_extract_invalid_json_returns_empty(self):
        llm = MockFixedLLM()

        def mock_generate(messages, **kwargs):
            return "This is not JSON at all"

        llm.generate = mock_generate
        extractor = EntityRelationExtractor(llm=llm)
        result = extractor.extract("Some text")
        assert result.nodes == []
        assert result.edges == []

    def test_extract_batch(self):
        llm = MockFixedLLM()
        call_count = 0

        def mock_generate(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            return json.dumps({
                "nodes": [{"name": f"Entity{call_count}", "label": "Concetto"}],
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
        r1 = GraphExtractionResult(nodes=[ExtractedNode(name="X", label="A")], edges=[])
        r2 = GraphExtractionResult(
            nodes=[ExtractedNode(name="Y", label="B")],
            edges=[ExtractedEdge(source="X", target="Y", type="REL")],
        )
        merged = r1.merge(r2)
        assert len(merged.nodes) == 2
        assert len(merged.edges) == 1


# --------------------------------------------------------------------------- #
# Test resolver unico
# --------------------------------------------------------------------------- #


class TestExactMatchResolver:
    def test_no_duplicates(self):
        resolver = ExactMatchResolver()
        nodes = [
            {"name": "Alice", "label": "Persona"},
            {"name": "Acme", "label": "Organizzazione"},
        ]
        deduped, edges = resolver.resolve(nodes, [])
        assert len(deduped) == 2

    def test_exact_duplicate_merged(self):
        resolver = ExactMatchResolver()
        nodes = [
            {"name": "Alice", "label": "Persona"},
            {"name": "alice", "label": "Persona"},
        ]
        edges = [{"source": "alice", "target": "Alice", "type": "X"}]
        deduped, remapped = resolver.resolve(nodes, edges)
        assert len(deduped) == 1
        assert deduped[0]["name"] == "Alice"
        # L'arco è rimappato al canonical
        assert remapped[0]["source"] == "Alice"
        assert remapped[0]["target"] == "Alice"

    def test_different_labels_not_merged(self):
        resolver = ExactMatchResolver()
        nodes = [
            {"name": "Roma", "label": "Luogo"},
            {"name": "Roma", "label": "Squadra"},
        ]
        deduped, _ = resolver.resolve(nodes, [])
        assert len(deduped) == 2

    def test_empty(self):
        resolver = ExactMatchResolver()
        deduped, edges = resolver.resolve([], [])
        assert deduped == []
        assert edges == []


# --------------------------------------------------------------------------- #
# Test writer
# --------------------------------------------------------------------------- #


class TestNeo4jWriter:
    def test_write_nodes(self):
        store = MockGraphStore()
        writer = Neo4jWriter(store)
        n = writer.write_nodes([{"name": "Alice", "label": "Persona"}], "Entity")
        assert n == 1
        assert "MERGE" in store.write_queries[0][0]

    def test_write_edges(self):
        store = MockGraphStore()
        writer = Neo4jWriter(store)
        n = writer.write_edges(
            [{"source_name": "A", "target_name": "B", "properties": {}}],
            "Entity", "Entity", "RELATED_TO",
        )
        assert n == 1

    def test_write_mentions(self):
        store = MockGraphStore()
        writer = Neo4jWriter(store)
        n = writer.write_mentions("b::f::0", ["Alice", "Acme"])
        assert n == 2
        query = store.write_queries[0][0]
        assert "MENTIONS" in query

    def test_write_mentions_empty(self):
        store = MockGraphStore()
        writer = Neo4jWriter(store)
        assert writer.write_mentions("c", []) == 0
        assert store.write_queries == []

    def test_delete_orphan_entities(self):
        store = MockGraphStore()
        store.set_query_results([[{"deleted": 3}]])
        writer = Neo4jWriter(store)
        n = writer.delete_orphan_entities()
        assert n == 3
        assert "WHERE NOT (e)<-[:MENTIONS]-()" in store.executed_queries[0][0]

    def test_delete_chunks(self):
        store = MockGraphStore()
        writer = Neo4jWriter(store)
        assert writer.delete_chunks(["a", "b"]) == 2
        assert "DETACH DELETE" in store.write_queries[0][0]

    def test_delete_file_nodes(self):
        store = MockGraphStore()
        writer = Neo4jWriter(store)
        writer.delete_file_nodes("fid")
        assert "file_id" in store.write_queries[0][0]

    def test_update_chunk_file_name(self):
        store = MockGraphStore()
        writer = Neo4jWriter(store)
        writer.update_chunk_file_name("fid", "nuovo.pdf")
        assert "file_name" in store.write_queries[0][0]

    def test_update_chunk_embeddings(self):
        store = MockGraphStore()
        writer = Neo4jWriter(store)
        writer.update_chunk_embeddings([{"chunk_id": "c", "embedding": [1.0]}])
        assert "embedding" in store.write_queries[0][0]

    def test_create_indexes(self):
        store = MockGraphStore()
        writer = Neo4jWriter(store)
        writer.create_vector_index(dimensions=4)
        writer.create_fulltext_index()
        assert "VECTOR INDEX" in store.write_queries[0][0]
        assert "FULLTEXT INDEX" in store.write_queries[1][0]


# --------------------------------------------------------------------------- #
# Test chunk loader
# --------------------------------------------------------------------------- #


def _write_chunk(chunks_dir: Path, file_id: str, index: int, text: str) -> None:
    d = chunks_dir / file_id
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{file_id}_chunk_{index}.md").write_text(text, encoding="utf-8")


class TestKSChunkLoader:
    def test_load_file_empty_dir(self, tmp_path):
        loader = KSChunkLoader(tmp_path / "chunks")
        result = loader.load_file("missing", "kb1", "doc.md")
        assert result.chunks == []

    def test_load_file_with_chunks(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        _write_chunk(chunks_dir, "fid", 0, "primo chunk")
        _write_chunk(chunks_dir, "fid", 1, "secondo chunk")
        loader = KSChunkLoader(chunks_dir)
        result = loader.load_file("fid", "kb1", "doc.md")
        assert len(result.chunks) == 2
        assert result.chunks[0].chunk_id == "kb1::fid::0"
        assert result.chunks[0].text == "primo chunk"

    def test_load_file_ordering(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        for i in (2, 0, 1):
            _write_chunk(chunks_dir, "fid", i, f"c{i}")
        loader = KSChunkLoader(chunks_dir)
        result = loader.load_file("fid", "kb1", "doc.md")
        assert [c.chunk_index for c in result.chunks] == [0, 1, 2]

    def test_recycle_embedding_from_chroma(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        _write_chunk(chunks_dir, "fid", 0, "testo")

        class FakeCollection:
            def get(self, ids, include):
                return {"embeddings": [[0.5, 0.5, 0.5, 0.5]]}

        loader = KSChunkLoader(chunks_dir, chroma_collection=FakeCollection())
        result = loader.load_file("fid", "kb1", "doc.md")
        assert result.chunks[0].embedding == [0.5, 0.5, 0.5, 0.5]

    def test_recompute_embedding_with_graph_embedder(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        _write_chunk(chunks_dir, "fid", 0, "testo")
        loader = KSChunkLoader(chunks_dir, embedder=StubEmbedder(), recompute=True)
        result = loader.load_file("fid", "kb1", "doc.md")
        assert result.chunks[0].embedding == [5.0, 0.0, 0.0, 1.0]

    def test_recompute_without_embedder_warns(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        _write_chunk(chunks_dir, "fid", 0, "testo")
        loader = KSChunkLoader(chunks_dir, recompute=True)
        result = loader.load_file("fid", "kb1", "doc.md")
        assert result.chunks[0].embedding is None


# --------------------------------------------------------------------------- #
# Test retriever unico
# --------------------------------------------------------------------------- #


class TestHybridCypherRetriever:
    def _store_with_results(self, rows):
        store = MockGraphStore()
        store.set_query_results([rows])
        return store

    def test_search(self):
        store = self._store_with_results([
            {"chunk_id": "kb1::f::0", "text": "testo", "score": 0.9,
             "entities": ["Alice"]},
        ])
        retriever = HybridCypherRetriever(store, StubEmbedder())
        results = retriever.search("query", top_k=3)
        assert len(results) == 1
        assert results[0].chunk_id == "kb1::f::0"
        assert results[0].metadata["entities"] == ["Alice"]

    def test_search_with_active_base_filter(self):
        store = self._store_with_results([])
        retriever = HybridCypherRetriever(store, StubEmbedder())
        retriever.search("q", top_k=3, active_base_names=["kb1", "kb2"])
        query, params = store.executed_queries[0]
        assert "WHERE base IN $active_base_names" in query
        assert params["active_base_names"] == ["kb1", "kb2"]

    def test_search_without_filter(self):
        store = self._store_with_results([])
        retriever = HybridCypherRetriever(store, StubEmbedder())
        retriever.search("q", top_k=3)
        query, params = store.executed_queries[0]
        assert "active_base_names" not in query
        assert "active_base_names" not in params


# --------------------------------------------------------------------------- #
# Helpers per GraphManager
# --------------------------------------------------------------------------- #


def _make_workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(path=tmp_path / "ws")
    (ws.path / "kb1").mkdir(parents=True)
    return ws


def _make_entry(file_id: str, name: str, n_chunks: int) -> FileEntry:
    return FileEntry(
        mtime=1.0,
        added="2026-01-01T00:00:00",
        file_id=file_id,
        name=name,
        content_hash="hash-file",
        chunks=[ChunkRef(index=i, content_hash=f"h{i}") for i in range(n_chunks)],
    )


def _add_base(ws: Workspace, base_name: str, entry: FileEntry, texts: List[str]) -> None:
    kb = KnowledgeBase(
        name=base_name,
        path=ws.path / base_name,
        embedding_model="stub",
        files={entry.name: entry},
    )
    ws.bases[base_name] = kb
    chunks_dir = kb.path / ".knowledge-space" / "chunks"
    for i, text in enumerate(texts):
        _write_chunk(chunks_dir, entry.file_id, i, text)


def _graph_config(**kwargs: Any) -> BaseConfig:
    g = GraphConfig(enabled=True, extraction_model="mock/llm", embedding_model="stub")
    for k, v in kwargs.items():
        setattr(g, k, v)
    return BaseConfig(graph=g)


def _llm_with_nodes(nodes: List[Dict[str, str]], edges: List[Dict[str, str]]):
    llm = MockFixedLLM()

    def mock_generate(messages, **kwargs):
        return json.dumps({"nodes": nodes, "edges": edges})

    llm.generate = mock_generate
    return llm


def _make_graph_manager(ws: Workspace, config: BaseConfig, store: MockGraphStore) -> GraphManager:
    store.connect()

    def config_loader(base_name: str) -> BaseConfig:
        return config

    return GraphManager(
        workspace=ws,
        config_loader=config_loader,
        graph_store_factory=lambda **kw: store,
        llm_factory=lambda name: _llm_with_nodes(
            [{"name": "Alice", "label": "Persona"}],
            [],
        ),
        embedder_factory=lambda name: StubEmbedder(),
        chroma_getter=None,
    )


# --------------------------------------------------------------------------- #
# Test GraphManager
# --------------------------------------------------------------------------- #


class TestGraphManager:
    def test_gating_disabled_returns_empty(self, tmp_path):
        ws = _make_workspace(tmp_path)
        _add_base(ws, "kb1", _make_entry("fid", "doc.md", 1), ["testo"])
        config = _graph_config(enabled=False)
        store = MockGraphStore()
        gm = _make_graph_manager(ws, config, store)
        counts = gm.build_graph()
        assert counts == {"chunk": 0, "document": 0, "entity": 0, "relation": 0}

    def test_gating_no_extraction_model(self, tmp_path):
        ws = _make_workspace(tmp_path)
        _add_base(ws, "kb1", _make_entry("fid", "doc.md", 1), ["testo"])
        config = _graph_config(extraction_model=None)
        store = MockGraphStore()
        gm = _make_graph_manager(ws, config, store)
        counts = gm.build_graph()
        assert counts["chunk"] == 0

    def test_build_graph(self, tmp_path):
        ws = _make_workspace(tmp_path)
        _add_base(ws, "kb1", _make_entry("fid", "doc.md", 2), ["uno", "due"])
        config = _graph_config()
        store = MockGraphStore()
        gm = _make_graph_manager(ws, config, store)
        counts = gm.build_graph()
        assert counts["document"] == 1
        assert counts["chunk"] == 2
        assert counts["entity"] == 2  # Alice menzionata in 2 chunk
        # Indici creati
        queries = " ".join(q for q, _ in store.write_queries)
        assert "VECTOR INDEX" in queries
        assert "FULLTEXT INDEX" in queries
        # MENTIONS scritte
        assert any("MENTIONS" in q for q, _ in store.write_queries)
        # HAS_CHUNK scritto
        assert any("HAS_CHUNK" in q for q, _ in store.write_queries)

    def test_build_connection_error(self, tmp_path):
        ws = _make_workspace(tmp_path)
        _add_base(ws, "kb1", _make_entry("fid", "doc.md", 1), ["testo"])
        config = _graph_config()
        store = MockGraphStore()  # NOT connected
        gm = _make_graph_manager(ws, config, store)
        store.close()  # simula Neo4j giù
        with pytest.raises(ConnectionError):
            gm.build_graph()

    def test_sync_base_detects_changed_chunks(self, tmp_path):
        ws = _make_workspace(tmp_path)
        _add_base(ws, "kb1", _make_entry("fid", "doc.md", 1), ["testo"])
        config = _graph_config()
        store = MockGraphStore()
        gm = _make_graph_manager(ws, config, store)
        # Chunk presente nel grafo con hash DIVERSO → da ri-estrarre.
        store.set_query_results(
            [[{"chunk_id": "kb1::fid::0", "content_hash": "hash-diverso"}]]
        )
        counts = gm.sync_base("kb1")
        assert counts["chunk"] == 1
        # delete_chunks + riscrittura
        assert any("DETACH DELETE" in q for q, _ in store.write_queries)
        # cleanup orfane eseguito
        assert any("WHERE NOT (e)<-[:MENTIONS]-()" in q for q, _ in store.executed_queries)

    def test_sync_base_unchanged_skips(self, tmp_path):
        ws = _make_workspace(tmp_path)
        _add_base(ws, "kb1", _make_entry("fid", "doc.md", 1), ["testo"])
        config = _graph_config()
        store = MockGraphStore()
        gm = _make_graph_manager(ws, config, store)
        # content_hash coincide → nessun chunk cambiato.
        store.set_query_results(
            [[{"chunk_id": "kb1::fid::0", "content_hash": "h0"}]]
        )
        counts = gm.sync_base("kb1")
        assert counts["chunk"] == 0

    def test_remove_base(self, tmp_path):
        ws = _make_workspace(tmp_path)
        _add_base(ws, "kb1", _make_entry("fid", "doc.md", 1), ["testo"])
        config = _graph_config()
        store = MockGraphStore()
        gm = _make_graph_manager(ws, config, store)
        gm.remove_base("kb1")
        assert any("file_id" in q for q, _ in store.write_queries)

    def test_status(self, tmp_path):
        ws = _make_workspace(tmp_path)
        _add_base(ws, "kb1", _make_entry("fid", "doc.md", 1), ["testo"])
        config = _graph_config()
        store = MockGraphStore()
        gm = _make_graph_manager(ws, config, store)
        store.set_query_results([
            [{"c": 1}],  # Document
            [{"c": 2}],  # Chunk
            [{"c": 3}],  # Entity
            [{"c": 4}],  # relazioni
            [{"b": "kb1"}],  # basi
        ])
        info = gm.status()
        assert info["connected"] is True
        assert info["document"] == 1
        assert info["chunk"] == 2
        assert info["entity"] == 3
        assert info["relations"] == 4
        assert info["bases"] == ["kb1"]

    def test_search(self, tmp_path):
        ws = _make_workspace(tmp_path)
        _add_base(ws, "kb1", _make_entry("fid", "doc.md", 1), ["testo"])
        config = _graph_config()
        store = MockGraphStore()
        gm = _make_graph_manager(ws, config, store)
        store.set_query_results([
            [{"chunk_id": "kb1::fid::0", "text": "t", "score": 0.8, "entities": []}]
        ])
        results = gm.search("q", top_k=3, active_base_names=["kb1"])
        assert len(results) == 1
        assert results[0].chunk_id == "kb1::fid::0"


# --------------------------------------------------------------------------- #
# Test GraphSearchService (filtro attivi)
# --------------------------------------------------------------------------- #


class TestGraphSearchService:
    def _workspace_with_results(self, tmp_path: Path, active: bool):
        ws = _make_workspace(tmp_path)
        entry = _make_entry("fid", "doc.md", 1)
        entry.chunks[0].active = active
        entry.active = active
        kb = KnowledgeBase(
            name="kb1", path=ws.path / "kb1", embedding_model="stub",
            files={"doc.md": entry},
        )
        kb.active = active
        ws.bases["kb1"] = kb
        return ws

    def test_search_filters_inactive_base(self, tmp_path):
        ws = self._workspace_with_results(tmp_path, active=False)

        class FakeGM:
            def __init__(self):
                self.called_with = None

            def search(self, query, top_k=5, active_base_names=None):
                self.called_with = active_base_names
                return [
                    GraphSearchResult("kb1::fid::0", "testo", 0.9,
                                      metadata={"entities": []})
                ]

        gm = FakeGM()
        service = GraphSearchService(gm)
        results = service.search(ws, "q")
        # La base inattiva non è searchable → nessun filtro attivo, 0 risultati.
        assert results == []

    def test_search_keeps_active_base(self, tmp_path):
        ws = self._workspace_with_results(tmp_path, active=True)

        class FakeGM:
            def search(self, query, top_k=5, active_base_names=None):
                assert active_base_names == ["kb1"]
                return [
                    GraphSearchResult("kb1::fid::0", "testo", 0.9,
                                      metadata={"entities": []})
                ]

        service = GraphSearchService(FakeGM())
        results = service.search(ws, "q")
        assert len(results) == 1
        assert results[0].chunk_id == "kb1::fid::0"

    def test_search_filters_inactive_chunk(self, tmp_path):
        ws = _make_workspace(tmp_path)
        entry = _make_entry("fid", "doc.md", 2)
        entry.chunks[1].active = False
        kb = KnowledgeBase(
            name="kb1", path=ws.path / "kb1", embedding_model="stub",
            files={"doc.md": entry},
        )
        ws.bases["kb1"] = kb

        class FakeGM:
            def search(self, query, top_k=5, active_base_names=None):
                return [
                    GraphSearchResult("kb1::fid::0", "attivo", 0.9),
                    GraphSearchResult("kb1::fid::1", "inattivo", 0.8),
                ]

        service = GraphSearchService(FakeGM())
        results = service.search(ws, "q")
        assert len(results) == 1
        assert results[0].chunk_id == "kb1::fid::0"
