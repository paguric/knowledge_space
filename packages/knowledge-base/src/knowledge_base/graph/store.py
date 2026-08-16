"""Graph store abstraction: Protocol + factory.

``GraphStore`` è l'interfaccia (Protocol) per qualsiasi backend di grafo.
La factory ``graph_store_factory`` istanzia il backend appropriato in base
alla configurazione. In Fase 1C l'unica implementazione concreta è
``Neo4jGraphStore``.

Tutti i driver sono importati lazy (come ``embedding.py``): il modulo si
importa senza neo4j installato.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Protocol, Sequence

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #


class GraphStore(Protocol):
    """Interfaccia per un backend di grafo.

    Operazioni minime per il pipeline GraphRAG:
    - Connessione / chiusura
    - Esecuzione query Cypher
    - Verifica esistenza nodi
    """

    def connect(self) -> None:
        """Apre la connessione al backend."""
        ...

    def close(self) -> None:
        """Chiude la connessione."""
        ...

    def is_connected(self) -> bool:
        """Restituisce True se la connessione è attiva."""
        ...

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Esegue una query Cypher e restituisce i risultati come lista di dict."""
        ...

    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Esegue una query Cypher di scrittura (CREATE/MERGE/SET/DELETE)."""
        ...

    def verify_connectivity(self) -> bool:
        """Verifica che il backend sia raggiungibile."""
        ...

    def schema_info(self) -> Dict[str, Any]:
        """Deriva lo schema dal DB (labels, tipi relazione, proprietà)."""
        ...


# --------------------------------------------------------------------------- #
# Neo4j implementation
# --------------------------------------------------------------------------- #


class Neo4jGraphStore:
    """Implementazione ``GraphStore`` per Neo4j.

    Connessione configurabile via env var:
    - ``NEO4J_URI`` (default ``bolt://localhost:7687``)
    - ``NEO4J_USER`` (default ``neo4j``)
    - ``NEO4J_PASSWORD`` (default ``neo4j``)

    Il driver ``neo4j`` è importato lazy in ``connect()``.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: str = "neo4j",
    ) -> None:
        self._uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.environ.get("NEO4J_USER", "neo4j")
        self._password = password or os.environ.get("NEO4J_PASSWORD", "neo4j")
        self._database = database
        self._driver = None

    def connect(self) -> None:
        """Apre la connessione a Neo4j (lazy import del driver)."""
        if self._driver is not None:
            return
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise ImportError(
                "Il pacchetto 'neo4j' è necessario per Neo4jGraphStore. "
                "Installarlo con: pip install neo4j"
            ) from exc
        self._driver = GraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )
        logger.info("Connesso a Neo4j: %s (database=%s)", self._uri, self._database)

    def close(self) -> None:
        """Chiude il driver Neo4j."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Connessione Neo4j chiusa")

    def is_connected(self) -> bool:
        return self._driver is not None

    def _ensure_connected(self) -> None:
        if self._driver is None:
            self.connect()

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Esegue una query Cypher in modalità read e restituisce i record."""
        self._ensure_connected()
        records, _, _ = self._driver.execute_query(  # type: ignore[union-attr]
            query,
            parameters_=parameters or {},
            database_=self._database,
        )
        return [dict(record) for record in records]

    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Esegue una query Cypher di scrittura."""
        self._ensure_connected()
        self._driver.execute_query(  # type: ignore[union-attr]
            query,
            parameters_=parameters or {},
            database_=self._database,
        )

    def verify_connectivity(self) -> bool:
        """Verifica la raggiungibilità del server Neo4j."""
        self._ensure_connected()
        try:
            self._driver.verify_connectivity()  # type: ignore[union-attr]
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Verifica connessione Neo4j fallita: %s", exc)
            return False

    def schema_info(self) -> Dict[str, Any]:
        """Deriva lo schema dal DB: labels, tipi relazione, proprietà.

        Refactor-001: nessuno schema persistente — si interroga il DB.
        """
        labels = [r.get("label") for r in self.execute_query("CALL db.labels()")]
        rel_types = [
            r.get("relationshipType")
            for r in self.execute_query("CALL db.relationshipTypes()")
        ]
        try:
            node_props = self.execute_query("CALL db.schema.nodeTypeProperties()")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Derivazione proprietà non disponibile: %s", exc)
            node_props = []
        return {
            "labels": labels,
            "relationship_types": rel_types,
            "node_properties": [dict(r) for r in node_props],
        }


# --------------------------------------------------------------------------- #
# Mock per test
# --------------------------------------------------------------------------- #


class MockGraphStore:
    """Mock ``GraphStore`` per test unitari.

    Registra le query eseguite e restituisce risultati configurabili.
    """

    def __init__(self) -> None:
        self.connected = False
        self.executed_queries: List[tuple[str, Dict[str, Any] | None]] = []
        self.write_queries: List[tuple[str, Dict[str, Any] | None]] = []
        self._query_results: List[List[Dict[str, Any]]] = []
        self._result_index = 0
        self.schema_data: Dict[str, Any] = {
            "labels": ["Document", "Chunk", "Entity"],
            "relationship_types": ["HAS_CHUNK", "MENTIONS", "RELATED_TO"],
            "node_properties": [],
        }

    def set_query_results(self, results: List[List[Dict[str, Any]]]) -> None:
        """Configura i risultati da restituire per query successive."""
        self._query_results = results
        self._result_index = 0

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        self.executed_queries.append((query, parameters))
        if self._result_index < len(self._query_results):
            result = self._query_results[self._result_index]
            self._result_index += 1
            return result
        return []

    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.write_queries.append((query, parameters))

    def verify_connectivity(self) -> bool:
        return self.connected

    def schema_info(self) -> Dict[str, Any]:
        """Restituisce ``schema_data`` (configurabile nei test)."""
        return dict(self.schema_data)


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #


def graph_store_factory(
    backend: str = "neo4j",
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    database: str = "neo4j",
) -> GraphStore:
    """Factory per istanziare un ``GraphStore``.

    Args:
        backend: tipo di backend (``"neo4j"`` o ``"mock"``).
        uri: URI Neo4j (default da env ``NEO4J_URI``).
        user: utente Neo4j (default da env ``NEO4J_USER``).
        password: password Neo4j (default da env ``NEO4J_PASSWORD``).
        database: database Neo4j.

    Returns:
        Istanza di ``GraphStore``.

    Raises:
        ValueError: se il backend non è supportato.
    """
    if backend == "neo4j":
        return Neo4jGraphStore(uri=uri, user=user, password=password, database=database)
    if backend == "mock":
        return MockGraphStore()
    raise ValueError(
        f"Backend graph '{backend}' non supportato. Disponibili: neo4j, mock"
    )
