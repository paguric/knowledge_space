"""Derivazione schema dal DB (refactor-001).

Nessuno schema persistente: lo schema si deriva a richiesta dal DB
(``CALL db.labels()``, ``db.relationshipTypes()``,
``db.schema.nodeTypeProperties()``) — sempre allineato al corpus.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def derive_schema_info(store: Any) -> Dict[str, Any]:
    """Interroga lo store e restituisce labels/relazioni/proprietà."""
    return store.schema_info()


def format_schema(store: Any) -> str:
    """Formatta lo schema derivato dal DB come testo leggibile."""
    info = derive_schema_info(store)
    labels = info.get("labels", [])
    rel_types = info.get("relationship_types", [])
    node_props = info.get("node_properties", [])

    lines = ["Schema del grafo (derivato dal DB):", ""]
    lines.append("Label nodi:")
    for label in sorted(labels):
        props = [
            p.get("propertyName")
            for p in node_props
            if p.get("nodeLabels") == [label] and p.get("propertyName")
        ]
        if props:
            lines.append(f"  {label}: {', '.join(sorted(props))}")
        else:
            lines.append(f"  {label}")
    lines.append("")
    lines.append("Tipi relazione:")
    for rel in sorted(rel_types):
        lines.append(f"  {rel}")
    return "\n".join(lines)
