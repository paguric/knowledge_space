"""GraphManager: orchestrazione del grafo di conoscenza (refactor-001).

Un grafo per workspace (mai per-base): chunk di tutte le basi nello
stesso Neo4j, ``base_name`` come proprietà dei nodi Chunk.

Flusso: ``KSChunkLoader`` → estrazione entità (LLM) → ``Neo4jWriter``
(nodi/archi/MENTIONS idempotenti) → ``ExactMatchResolver`` come rete di
sicurezza. Nessuno schema persistente (derivato dal DB a richiesta).

Gating: senza ``graph.enabled`` o senza ``extraction_model`` il grafo è
INATTIVO (l'estrazione richiede un LLM): ogni operazione è un no-op con
warning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from knowledge_base.graph.chunk_loader import KSChunkLoader
from knowledge_base.graph.extraction import EntityRelationExtractor
from knowledge_base.graph.resolver import ExactMatchResolver
from knowledge_base.graph.retriever import GraphSearchResult, HybridCypherRetriever
from knowledge_base.graph.writer import Neo4jWriter

logger = logging.getLogger(__name__)

# Costanti (nomi indici fissi per workspace — refactor-001).
_VECTOR_INDEX = "chunk-embeddings"
_FULLTEXT_INDEX = "chunk-text"


class GraphManager:
    """Costruisce e sincronizza il grafo di conoscenza del workspace.

    Args:
        workspace: modello ``Workspace`` (basi e domini caricati).
        config_loader: callable ``(base_name) -> BaseConfig`` (cascata TOML).
        graph_store_factory: callable che costruisce un ``GraphStore``
            (``uri``/``user``/``password``/``database`` come kwargs).
        llm_factory: ``(model_name) -> LLMStrategy``.
        embedder_factory: ``(model_name) -> EmbeddingStrategy``.
        chroma_getter: callable ``(base_name) -> collection Chroma | None``
            per il riciclo embedding (opzionale).
    """

    def __init__(
        self,
        workspace: Any,
        config_loader: Callable[[str], Any],
        graph_store_factory: Callable[..., Any],
        llm_factory: Callable[[str], Any],
        embedder_factory: Callable[[str], Any],
        chroma_getter: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._workspace = workspace
        self._config_loader = config_loader
        self._graph_store_factory = graph_store_factory
        self._llm_factory = llm_factory
        self._embedder_factory = embedder_factory
        self._chroma_getter = chroma_getter

        self._conn_path = self._graph_dir() / "graph.json"
        self._conn = self._load_conn()
        self._store = graph_store_factory(**self._conn)
        self._writer = Neo4jWriter(self._store)
        self._resolver = ExactMatchResolver()

        self._embedder_cache: Dict[str, Any] = {}
        self._llm_cache: Dict[str, Any] = {}

    # ..................................................................... #
    # Connessione
    # ..................................................................... #

    def _graph_dir(self) -> Path:
        return self._workspace.path / ".knowledge-space" / "graph"

    def _load_conn(self) -> Dict[str, str]:
        """Connessione da ``graph.json`` (se esiste) o env var."""
        import os

        if self._conn_path.is_file():
            try:
                data = json.loads(self._conn_path.read_text(encoding="utf-8"))
                return {
                    "uri": data.get("bolt_uri", "bolt://localhost:7687"),
                    "user": data.get("user", "neo4j"),
                    "password": data.get("password", ""),
                    "database": data.get("database", "neo4j"),
                }
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("graph.json illeggibile (%s): uso env", exc)
        return {
            "uri": os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            "user": os.environ.get("NEO4J_USER", "neo4j"),
            "password": os.environ.get("NEO4J_PASSWORD", ""),
            "database": os.environ.get("NEO4J_DATABASE", "neo4j"),
        }

    def _save_conn(self) -> None:
        """Persiste la connessione corrente in ``graph.json`` (al primo build)."""
        if self._conn_path.is_file():
            return
        self._conn_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "bolt_uri": self._conn.get("uri", ""),
            "user": self._conn.get("user", "neo4j"),
            "password": self._conn.get("password", ""),
            "database": self._conn.get("database", "neo4j"),
        }
        self._conn_path.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        logger.info("Connessione grafo salvata in %s", self._conn_path)

    # ..................................................................... #
    # Gating e configurazione
    # ..................................................................... #

    def _graph_model(self) -> str:
        """Modello embedding del grafo (config della prima base attiva)."""
        for base_name in self._workspace.bases:
            config = self._config_loader(base_name)
            if config.graph.enabled:
                return config.graph.embedding_model
        # Fallback: defaults del workspace (prima base disponibile).
        for base_name in self._workspace.bases:
            return self._config_loader(base_name).graph.embedding_model
        return "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def _graph_enabled(self) -> List[str]:
        """Nomi delle basi con grafo attivo (enabled + extraction_model)."""
        active: List[str] = []
        for base_name, kb in self._workspace.bases.items():
            if not kb.active:
                continue
            config = self._config_loader(base_name)
            if config.graph.enabled and config.graph.extraction_model:
                active.append(base_name)
        return active

    def _check_active(self) -> List[str]:
        """Basi grafo-attive; warning se il grafo è inattivo ovunque."""
        active = self._graph_enabled()
        if not active:
            logger.warning(
                "Grafo inattivo: graph.enabled=false o extraction_model "
                "non impostato (l'estrazione entità richiede un LLM)"
            )
        return active

    def _graph_embedder(self) -> Any:
        model = self._graph_model()
        if model not in self._embedder_cache:
            self._embedder_cache[model] = self._embedder_factory(model)
        return self._embedder_cache[model]

    def _extractor(self, model_name: str) -> EntityRelationExtractor:
        if model_name not in self._llm_cache:
            self._llm_cache[model_name] = EntityRelationExtractor(
                self._llm_factory(model_name)
            )
        return self._llm_cache[model_name]

    # ..................................................................... #
    # Build / sync / remove
    # ..................................................................... #

    def build_graph(self) -> Dict[str, int]:
        """Full build per ogni base attiva con grafo abilitato.

        Returns:
            Conteggi ``{chunk, document, entity, relation}`` scritti.
        """
        active = self._check_active()
        if not active:
            return {"chunk": 0, "document": 0, "entity": 0, "relation": 0}

        if not self._store.verify_connectivity():
            raise ConnectionError(
                "Neo4j non raggiungibile. Controlla NEO4J_URI/NEO4J_AUTH "
                "o graph.json e che il server sia avviato."
            )
        self._save_conn()

        embedder = self._graph_embedder()
        try:
            dim = embedder.metadata.dim
        except Exception:  # noqa: BLE001
            dim = 384
        self._writer.create_vector_index(dimensions=dim)
        self._writer.create_fulltext_index()

        totals = {"chunk": 0, "document": 0, "entity": 0, "relation": 0}
        for base_name in active:
            counts = self._build_base(base_name, embedder)
            for key in totals:
                totals[key] += counts[key]
        logger.info(
            "Grafo costruito: %d chunk, %d documenti, %d entità, %d relazioni",
            totals["chunk"], totals["document"], totals["entity"], totals["relation"],
        )
        return totals

    def _build_base(self, base_name: str, embedder: Any) -> Dict[str, int]:
        """Costruisce il grafo per una base (nodi, archi, estrazione)."""
        kb = self._workspace.bases[base_name]
        config = self._config_loader(base_name)
        model = config.graph.embedding_model

        counts = {"chunk": 0, "document": 0, "entity": 0, "relation": 0}
        for file_name, entry in kb.files.items():
            if not entry.active or not entry.file_id:
                continue
            counts["document"] += 1
            self._writer.write_nodes(
                [{
                    "file_id": entry.file_id,
                    "file_name": file_name,
                    "base_name": base_name,
                }],
                label="Document",
                merge_key="file_id",
            )
            counts.update(
                self._upsert_file(base_name, kb, entry, model, embedder)
            )
        return counts

    def _make_loader(self, base_name: str, model: str, embedder: Any) -> KSChunkLoader:
        """Loader con riciclo da Chroma se il modello base == modello grafo."""
        kb = self._workspace.bases[base_name]
        base_model = kb.embedding_model
        recompute = base_model != model
        if recompute:
            logger.info(
                "Base %s: modello base (%s) diverso dal grafo (%s) → "
                "ricalcolo embedding col modello del grafo",
                base_name, base_model, model,
            )
        collection = None
        if not recompute and self._chroma_getter is not None:
            try:
                collection = self._chroma_getter(base_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Chroma non disponibile per %s: %s", base_name, exc)
        chunks_dir = kb.path / ".knowledge-space" / "chunks"
        return KSChunkLoader(
            chunks_dir=chunks_dir,
            chroma_collection=collection,
            embedder=embedder,
            recompute=recompute,
        )

    def _upsert_file(
        self,
        base_name: str,
        kb: Any,
        entry: Any,
        model: str,
        embedder: Any,
    ) -> Dict[str, int]:
        """Scrive Chunk + estrazione di un file. Ritorna i conteggi."""
        loader = self._make_loader(base_name, model, embedder)
        text_chunks = loader.load_file(
            entry.file_id, base_name=base_name, file_name=entry.name
        )
        extractor = self._extractor(
            self._config_loader(base_name).graph.extraction_model
        )
        counts = {"chunk": 0, "entity": 0, "relation": 0}

        has_chunk_edges = []
        chunk_nodes = []
        for chunk in text_chunks.chunks:
            chunk_nodes.append({
                "chunk_id": chunk.chunk_id,
                "base_name": base_name,
                "file_id": entry.file_id,
                "file_name": entry.name,
                "index": chunk.chunk_index,
                "text": chunk.text,
                "embedding": chunk.embedding or [],
                "content_hash": chunk.content_hash,
            })
            has_chunk_edges.append({
                "source_name": entry.file_id,
                "target_name": chunk.chunk_id,
                "properties": {},
            })
            counts["chunk"] += 1

        self._writer.write_nodes(chunk_nodes, label="Chunk", merge_key="chunk_id")
        self._writer.write_edges(
            has_chunk_edges,
            source_label="Document",
            target_label="Chunk",
            edge_type="HAS_CHUNK",
            source_key="file_id",
            target_key="chunk_id",
        )

        # Estrazione entità per-chunk + risoluzione.
        for chunk in text_chunks.chunks:
            result = extractor.extract(chunk.text, chunk_id=chunk.chunk_id)
            nodes, edges = self._resolver.resolve(
                [n.model_dump() for n in result.nodes],
                [e.model_dump() for e in result.edges],
            )
            if nodes:
                self._writer.write_nodes(nodes, label="Entity", merge_key="name")
                self._writer.write_mentions(
                    chunk.chunk_id, [n["name"] for n in nodes]
                )
                counts["entity"] += len(nodes)
            if edges:
                self._writer.write_edges(
                    edges,
                    source_label="Entity",
                    target_label="Entity",
                    edge_type="RELATED_TO",
                    source_key="name",
                    target_key="name",
                )
                counts["relation"] += len(edges)
        return counts

    def sync_base(self, base_name: Optional[str] = None) -> Dict[str, int]:
        """Propagazione incrementale: ri-estrae solo i chunk nuovi/modificati.

        Il diff è per ``content_hash``: si interroga il grafo per i chunk
        presenti del file e si ri-estraggono solo quelli mancanti o con
        hash diverso. Dopo i delete → ``delete_orphan_entities``.
        """
        targets = [base_name] if base_name else self._check_active()
        totals = {"chunk": 0, "entity": 0, "relation": 0}
        for bname in targets:
            if bname not in self._workspace.bases:
                logger.warning("Base non trovata nel workspace: %s", bname)
                continue
            kb = self._workspace.bases[bname]
            config = self._config_loader(bname)
            if not (config.graph.enabled and config.graph.extraction_model):
                logger.warning("Grafo inattivo per la base %s: skip", bname)
                continue
            embedder = self._graph_embedder()
            counts = self._sync_base(bname, kb, config, embedder)
            for key in totals:
                totals[key] += counts[key]
        return totals

    def _sync_base(self, base_name: str, kb: Any, config: Any, embedder: Any) -> Dict[str, int]:
        counts = {"chunk": 0, "entity": 0, "relation": 0}
        for file_name, entry in kb.files.items():
            if not entry.active or not entry.file_id:
                continue
            # Chunk presenti nel grafo per questo file.
            existing = {}
            try:
                rows = self._store.execute_query(
                    "MATCH (c:Chunk {file_id: $file_id}) "
                    "RETURN c.chunk_id AS chunk_id, c.content_hash AS content_hash",
                    {"file_id": entry.file_id},
                )
                existing = {
                    r["chunk_id"]: r.get("content_hash")
                    for r in rows
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("Lettura chunk dal grafo fallita: %s", exc)

            expected_ids = {
                f"{base_name}::{entry.file_id}::{c.index}"
                for c in entry.chunks
                if c.active
            }
            changed_ids = [
                cid for cid in expected_ids
                if cid not in existing
                or existing[cid] != _content_hash_for(entry, cid.rsplit("::", 1)[-1])
            ]
            if changed_ids:
                self._writer.delete_chunks(changed_ids)
                # Riscrittura dei soli chunk cambiati: più semplice e
                # idempotente ri-scrivere il file intero (MERGE).
                counts.update(self._upsert_file(base_name, kb, entry, config.graph.embedding_model, embedder))
        # Cleanup entità orfane dopo i delete.
        try:
            self._writer.delete_orphan_entities()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cleanup entità orfane fallito: %s", exc)
        return counts

    def remove_base(self, base_name: str) -> None:
        """Rimuove Document/Chunk della base dal grafo + entità orfane."""
        kb = self._workspace.bases.get(base_name)
        if kb is None:
            logger.warning("Base non trovata nel modello: %s", base_name)
            return
        for entry in kb.files.values():
            if entry.file_id:
                try:
                    self._writer.delete_file_nodes(entry.file_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Rimozione file %s dal grafo fallita: %s", entry.file_id, exc)
        try:
            self._writer.delete_orphan_entities()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cleanup entità orfane fallito: %s", exc)

    # ..................................................................... #
    # Stato e ricerca
    # ..................................................................... #

    def status(self) -> Dict[str, Any]:
        """Conteggi dal DB + connettività."""
        connected = self._store.verify_connectivity()
        if not connected:
            return {"connected": False}
        counts: Dict[str, Any] = {"connected": True}
        try:
            for label in ("Document", "Chunk", "Entity"):
                rows = self._store.execute_query(
                    f"MATCH (n:{label}) RETURN count(n) AS c"
                )
                counts[label.lower()] = rows[0]["c"] if rows else 0
            rows = self._store.execute_query(
                "MATCH ()-[r:RELATED_TO]->() RETURN count(r) AS c"
            )
            counts["relations"] = rows[0]["c"] if rows else 0
            rows = self._store.execute_query(
                "MATCH (c:Chunk) RETURN DISTINCT c.base_name AS b ORDER BY b"
            )
            counts["bases"] = [r["b"] for r in rows]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lettura conteggi dal grafo fallita: %s", exc)
            counts["error"] = str(exc)
        return counts

    def search(
        self,
        query: str,
        top_k: int = 5,
        active_base_names: Optional[List[str]] = None,
    ) -> List[GraphSearchResult]:
        """Ricerca ibrida; ``active_base_names=None`` → nessun filtro."""
        embedder = self._graph_embedder()
        retriever = HybridCypherRetriever(self._store, embedder)
        try:
            return retriever.search(
                query, top_k=top_k, active_base_names=active_base_names
            )
        except Exception as exc:  # noqa: BLE001
            # Es. indici vettoriali/full-text mai creati.
            raise ConnectionError(
                f"Ricerca sul grafo fallita (esegui 'ks graph init' per "
                f"creare gli indici): {exc}"
            ) from exc


def _content_hash_for(entry: Any, index_str: str) -> Optional[str]:
    """content_hash registrato per un indice chunk di un FileEntry."""
    try:
        idx = int(index_str)
    except ValueError:
        return None
    if 0 <= idx < len(entry.chunks):
        return entry.chunks[idx].content_hash
    return None
