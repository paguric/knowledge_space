"""Graph schema: Pydantic models + loading from file.

Il grafo ha uno schema che definisce i tipi di nodi, archi e vincoli.
Viene caricato da ``<workspace>/.knowledge-space/graph/schema.json`` se
esiste; altrimenti viene estratto/costruito la prima volta.

``GraphSchema`` è un modello Pydantic serializzabile in JSON.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Pydantic models
# --------------------------------------------------------------------------- #


class PropertySchema(BaseModel):
    """Schema di una proprietà di un nodo o arco."""

    name: str
    type: str = "string"  # "string", "integer", "float", "boolean", "list"
    required: bool = False
    description: Optional[str] = None


class NodeSchema(BaseModel):
    """Schema di un tipo di nodo del grafo."""

    label: str
    description: Optional[str] = None
    properties: List[PropertySchema] = Field(default_factory=list)


class EdgeSchema(BaseModel):
    """Schema di un tipo di arco (relazione) del grafo."""

    type: str
    source_label: Optional[str] = None
    target_label: Optional[str] = None
    description: Optional[str] = None
    properties: List[PropertySchema] = Field(default_factory=list)


class GraphSchema(BaseModel):
    """Schema completo del grafo della conoscenza.

    Definisce i tipi di nodi, archi e vincoli. Può essere:
    - Caricato da file JSON (``schema.json``)
    - Estratto da LLM (``EXTRACTED``)
    - Costruito manualmente (``manuale``)
    - Assente (``FREE``: nessuno schema)
    """

    nodes: List[NodeSchema] = Field(default_factory=list)
    edges: List[EdgeSchema] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    schema_type: str = "FREE"  # "FREE", "EXTRACTED", "manuale"

    # ..................................................................... #
    # Serializzazione
    # ..................................................................... #

    @classmethod
    def from_file(cls, path: Path) -> "GraphSchema":
        """Carica lo schema da un file JSON.

        Args:
            path: percorso del file ``schema.json``.

        Returns:
            Istanza di ``GraphSchema``.

        Raises:
            FileNotFoundError: se il file non esiste.
            json.JSONDecodeError: se il file non è JSON valido.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File schema non trovato: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        schema = cls.model_validate(data)
        logger.info("Schema caricato da %s (%d nodi, %d archi)", p, len(schema.nodes), len(schema.edges))
        return schema

    def save(self, path: Path) -> None:
        """Salva lo schema su un file JSON.

        Args:
            path: percorso del file ``schema.json``.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))
        logger.info("Schema salvato in %s", p)

    @classmethod
    def free(cls) -> "GraphSchema":
        """Crea uno schema FREE (nessun vincolo)."""
        return cls(schema_type="FREE")

    @classmethod
    def default_lexical(cls) -> "GraphSchema":
        """Crea uno schema di default per il lexical graph.

        Include i nodi Document e Chunk che ``LLMEntityRelationExtractor``
        crea autonomamente con ``create_lexical_graph=True``.
        """
        return cls(
            nodes=[
                NodeSchema(
                    label="Document",
                    description="Documento sorgente",
                    properties=[
                        PropertySchema(name="path", type="string", required=True),
                        PropertySchema(name="file_name", type="string"),
                    ],
                ),
                NodeSchema(
                    label="Chunk",
                    description="Frammento di testo",
                    properties=[
                        PropertySchema(name="chunk_id", type="string", required=True),
                        PropertySchema(name="text", type="string"),
                        PropertySchema(name="embedding", type="list"),
                        PropertySchema(name="base_name", type="string"),
                        PropertySchema(name="file_name", type="string"),
                        PropertySchema(name="file_id", type="string"),
                        PropertySchema(name="chunk_index", type="integer"),
                        PropertySchema(name="content_hash", type="string"),
                    ],
                ),
            ],
            edges=[
                EdgeSchema(type="FROM_DOCUMENT", source_label="Chunk", target_label="Document"),
                EdgeSchema(type="NEXT_CHUNK", source_label="Chunk", target_label="Chunk"),
            ],
            schema_type="manuale",
        )

    # ..................................................................... #
    # Utility
    # ..................................................................... #

    def get_node_labels(self) -> List[str]:
        """Restituisce le etichette dei nodi definiti nello schema."""
        return [n.label for n in self.nodes]

    def get_edge_types(self) -> List[str]:
        """Restituisce i tipi degli archi definiti nello schema."""
        return [e.type for e in self.edges]

    def get_node_schema(self, label: str) -> Optional[NodeSchema]:
        """Restituisce lo schema di un nodo per etichetta, o None."""
        for n in self.nodes:
            if n.label == label:
                return n
        return None

    def get_edge_schema(self, edge_type: str) -> Optional[EdgeSchema]:
        """Restituisce lo schema di un arco per tipo, o None."""
        for e in self.edges:
            if e.type == edge_type:
                return e
        return None
