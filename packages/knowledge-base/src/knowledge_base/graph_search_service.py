"""GraphSearchService: ricerca sul grafo rispettando lo stato attivo.

Invariante 2 del refactor-001: la ricerca sul grafo rispetta
domini/basi/file/chunk ATTIVI come la ricerca vettoriale —
pre-retrieval ``active_base_names`` via :func:`is_base_searchable`,
post-retrieval ``filter_active_chunks`` (stessi ``chunk_id``).
"""

from __future__ import annotations

import logging
from typing import Any, List

from knowledge_base.graph.retriever import GraphSearchResult
from knowledge_base.search_service import filter_active_chunks, is_base_searchable

logger = logging.getLogger(__name__)


class GraphSearchService:
    """Ricerca ibrida sul grafo con filtro attivi (CLI ``graph search``,
    MCP ``graph_search``)."""

    def __init__(self, graph_manager: Any) -> None:
        self._graph_manager = graph_manager

    def search(
        self,
        workspace: Any,
        query: str,
        top_k: int = 5,
    ) -> List[GraphSearchResult]:
        """Ricerca sul grafo limitata alle basi searchable.

        Il post-filtro elimina i chunk di file/chunk disattivati
        (``filter_active_chunks`` per base di appartenenza).
        """
        active_base_names = [
            bname
            for bname, kb in workspace.bases.items()
            if is_base_searchable(bname, kb, workspace.domains)
        ]
        if not active_base_names:
            return []

        results = self._graph_manager.search(
            query, top_k=top_k, active_base_names=active_base_names
        )

        # Post-filtro per base: il chunk_id ha formato
        # "{base_name}::{file_id}::{index}".
        filtered: List[GraphSearchResult] = []
        for r in results:
            parts = r.chunk_id.rsplit("::", 2)
            if len(parts) != 3:
                continue
            base_name, _file_id, _index = parts
            kb = workspace.bases.get(base_name)
            if kb is None:
                continue
            kept = filter_active_chunks([r], kb)
            filtered.extend(kept)
        return filtered
