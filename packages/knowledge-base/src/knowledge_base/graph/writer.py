"""Neo4j writer: scrittura idempotente di nodi e archi.

``Neo4jWriter`` fornisce metodi per:
- Scrittura batch di nodi (MERGE su id deterministico)
- Scrittura batch di archi (MERGE)
- Cancellazione nodi/relazioni per chunk_id
- Aggiornamento proprietà (file_name, path, embedding)

Tutte le operazioni sono idempotenti (MERGE anziché CREATE).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Writer
# --------------------------------------------------------------------------- #


class Neo4jWriter:
    """Writer idempotente per Neo4j.

    Opera su un ``GraphStore`` (iniettato). Le query Cypher usano MERGE
    per garantire idempotenza.

    Args:
        store: istanza di ``GraphStore`` (o ``Neo4jGraphStore``).
        database: nome del database Neo4j.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    # ..................................................................... #
    # Nodi
    # ..................................................................... #

    def write_nodes(
        self,
        nodes: List[Dict[str, Any]],
        label: str,
        merge_key: str = "name",
    ) -> int:
        """Scrive batch di nodi con MERGE.

        Args:
            nodes: lista di dict con le proprietà dei nodi.
            label: etichetta Cypher (es. ``"Person"``).
            merge_key: proprietà usata per il MERGE (default ``"name"``).

        Returns:
            Numero di nodi scritti.
        """
        if not nodes:
            return 0

        # Costruisci query Cypher con UNWIND per batch
        query = f"""
        UNWIND $nodes AS node
        MERGE (n:{label} {{ {merge_key}: node.{merge_key} }})
        SET n += node
        """
        try:
            self._store.execute_write(query, {"nodes": nodes})
            logger.debug("Scritti %d nodi %s", len(nodes), label)
        except Exception as exc:
            logger.error("Errore scrittura nodi %s: %s", label, exc)
            raise
        return len(nodes)

    # ..................................................................... #
    # Archi
    # ..................................................................... #

    def write_edges(
        self,
        edges: List[Dict[str, Any]],
        source_label: str,
        target_label: str,
        edge_type: str,
        source_key: str = "name",
        target_key: str = "name",
    ) -> int:
        """Scrive batch di archi con MERGE (idempotente).

        Gli archi riferiscono i nodi per ``source_key``/``target_key``
        (per nome tra Entity; per file_id tra Document e Chunk).
        """
        if not edges:
            return 0

        query = f"""
        UNWIND $edges AS edge
        MATCH (a:{source_label} {{ {source_key}: edge.source_name }})
        MATCH (b:{target_label} {{ {target_key}: edge.target_name }})
        MERGE (a)-[r:{edge_type}]->(b)
        SET r += edge.properties
        """
        try:
            self._store.execute_write(query, {"edges": edges})
            logger.debug("Scritti %d archi %s", len(edges), edge_type)
        except Exception as exc:
            logger.error("Errore scrittura archi %s: %s", edge_type, exc)
            raise
        return len(edges)

    # ..................................................................... #
    # Menzioni e cleanup entità orfane (refactor-001)
    # ..................................................................... #

    def write_mentions(self, chunk_id: str, entity_names: List[str]) -> int:
        """Crea ``(c:Chunk)-[:MENTIONS]->(e:Entity)`` per ogni entità
        estratta dal chunk (relazione strutturale, MERGE idempotente).

        Le entità devono già esistere (``write_nodes`` con label Entity).
        """
        if not entity_names:
            return 0
        query = """
        UNWIND $names AS name
        MATCH (c:Chunk {chunk_id: $chunk_id})
        MATCH (e:Entity {name: name})
        MERGE (c)-[:MENTIONS]->(e)
        """
        try:
            self._store.execute_write(
                query, {"names": entity_names, "chunk_id": chunk_id}
            )
            logger.debug(
                "Scritte %d MENTIONS per chunk %s", len(entity_names), chunk_id
            )
        except Exception as exc:
            logger.error("Errore scrittura MENTIONS: %s", exc)
            raise
        return len(entity_names)

    def delete_orphan_entities(self) -> int:
        """Cancella le Entity senza più alcun MENTIONS in entrata.

        Da eseguire dopo ogni delete (chunk/file/base): le entità
        menzionate solo da ciò che è stato rimosso sparirebbero
        altrimenti mai dal DB.
        """
        query = """
        MATCH (e:Entity)
        WHERE NOT (e)<-[:MENTIONS]-()
        WITH collect(e) AS orphans
        FOREACH (x IN orphans | DELETE x)
        RETURN size(orphans) AS deleted
        """
        try:
            result = self._store.execute_query(query)
            deleted = result[0].get("deleted", 0) if result else 0
            if deleted:
                logger.info("Entità orfane eliminate: %d", deleted)
            return deleted
        except Exception as exc:
            logger.error("Errore eliminazione entità orfane: %s", exc)
            raise

    # ..................................................................... #
    # Cancellazione
    # ..................................................................... #

    def delete_chunks(self, chunk_ids: List[str]) -> int:
        """Cancella nodi Chunk e le loro relazioni per chunk_id.

        Args:
            chunk_ids: lista di chunk_id da cancellare.

        Returns:
            Numero di nodi cancellati.
        """
        if not chunk_ids:
            return 0

        query = """
        UNWIND $chunk_ids AS cid
        MATCH (c:Chunk {chunk_id: cid})
        DETACH DELETE c
        """
        try:
            self._store.execute_write(query, {"chunk_ids": chunk_ids})
            logger.debug("Cancellati %d chunk da Neo4j", len(chunk_ids))
        except Exception as exc:
            logger.error("Errore cancellazione chunk: %s", exc)
            raise
        return len(chunk_ids)

    def delete_file_nodes(self, file_id: str) -> int:
        """Cancella tutti i nodi Document e Chunk associati a un file_id.

        Args:
            file_id: id del file.

        Returns:
            Numero di nodi cancellati.
        """
        query = """
        MATCH (d:Document {file_id: $file_id})
        OPTIONAL MATCH (c:Chunk {file_id: $file_id})
        DETACH DELETE d, c
        """
        try:
            self._store.execute_write(query, {"file_id": file_id})
            logger.debug("Cancellati nodi per file_id=%s", file_id)
        except Exception as exc:
            logger.error("Errore cancellazione nodi file: %s", exc)
            raise
        return 1

    # ..................................................................... #
    # Aggiornamento proprietà
    # ..................................................................... #

    def update_chunk_file_name(self, file_id: str, new_file_name: str) -> None:
        """Aggiorna ``file_name`` su tutti i Chunk e Document di un file.

        Trigger 2 (move/rename): property-only, nessuna re-estrazione.
        """
        query = """
        MATCH (n)
        WHERE (n:Chunk OR n:Document) AND n.file_id = $file_id
        SET n.file_name = $file_name
        """
        try:
            self._store.execute_write(
                query, {"file_id": file_id, "file_name": new_file_name}
            )
            logger.debug("Aggiornato file_name per file_id=%s", file_id)
        except Exception as exc:
            logger.error("Errore aggiornamento file_name: %s", exc)
            raise

    def update_chunk_embeddings(
        self,
        chunk_embeddings: List[Dict[str, Any]],
    ) -> None:
        """Aggiorna gli embedding sui nodi Chunk.

        Trigger 3 (cambio modello): property-only, nessuna re-estrazione.

        Args:
            chunk_embeddings: lista di dict con ``chunk_id`` e ``embedding``.
        """
        if not chunk_embeddings:
            return

        query = """
        UNWIND $items AS item
        MATCH (c:Chunk {chunk_id: item.chunk_id})
        SET c.embedding = item.embedding
        """
        try:
            self._store.execute_write(query, {"items": chunk_embeddings})
            logger.debug("Aggiornati %d embedding su Neo4j", len(chunk_embeddings))
        except Exception as exc:
            logger.error("Errore aggiornamento embedding: %s", exc)
            raise

    # ..................................................................... #
    # Indici
    # ..................................................................... #

    def create_vector_index(
        self,
        index_name: str = "chunk-embeddings",
        label: str = "Chunk",
        property_name: str = "embedding",
        dimensions: int = 1536,
    ) -> None:
        """Crea un indice vettoriale (idempotente).

        Args:
            index_name: nome dell'indice.
            label: etichetta Cypher.
            property_name: proprietà con l'embedding.
            dimensions: dimensionalità del vettore.
        """
        query = f"""
        CREATE VECTOR INDEX `{index_name}` IF NOT EXISTS
        FOR (n:{label})
        ON (n.{property_name})
        OPTIONS {{
            indexConfig: {{
                `vector.dimensions`: {dimensions},
                `vector.similarity_function`: 'cosine'
            }}
        }}
        """
        try:
            self._store.execute_write(query)
            logger.info("Indice vettoriale '%s' creato/verificato", index_name)
        except Exception as exc:
            logger.error("Errore creazione indice vettoriale: %s", exc)
            raise

    def create_fulltext_index(
        self,
        index_name: str = "chunk-text",
        label: str = "Chunk",
        properties: Optional[List[str]] = None,
    ) -> None:
        """Crea un indice full-text (idempotente).

        Args:
            index_name: nome dell'indice.
            label: etichetta Cypher.
            properties: proprietà indicizzate (default ``["text"]``).
        """
        props = properties or ["text"]
        props_str = ", ".join(f"n.{p}" for p in props)
        query = f"""
        CREATE FULLTEXT INDEX `{index_name}` IF NOT EXISTS
        FOR (n:{label})
        ON EACH [{props_str}]
        """
        try:
            self._store.execute_write(query)
            logger.info("Indice full-text '%s' creato/verificato", index_name)
        except Exception as exc:
            logger.error("Errore creazione indice full-text: %s", exc)
            raise
