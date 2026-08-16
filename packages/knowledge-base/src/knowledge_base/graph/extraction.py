"""Estrazione entità e relazioni dai chunk via LLM.

``EntityRelationExtractor`` usa un LLM per estrarre entità e relazioni
da un chunk di testo. Riferimenti **per nome** (nessun id locale):
nodi ``{name, label}``, archi ``{source, target, type}`` — il resolver
(ExactMatch) è solo una rete di sicurezza, la dedup vera la fa il prompt.

L'LLM è iniettato come ``LLMStrategy``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Modelli di estrazione
# --------------------------------------------------------------------------- #


class ExtractedNode(BaseModel):
    """Nodo estratto da un chunk (riferimento per nome)."""

    name: str  # nome dell'entità
    label: str  # tipo di entità (es. "Persona", "Organizzazione")
    properties: Dict[str, Any] = Field(default_factory=dict)
    chunk_id: Optional[str] = None  # chunk sorgente


class ExtractedEdge(BaseModel):
    """Arco estratto da un chunk (source/target per nome)."""

    source: str  # nome del nodo sorgente
    target: str  # nome del nodo target
    type: str  # tipo di relazione
    properties: Dict[str, Any] = Field(default_factory=dict)
    chunk_id: Optional[str] = None  # chunk sorgente


class GraphExtractionResult(BaseModel):
    """Risultato dell'estrazione entità-relazioni da uno o più chunk."""

    nodes: List[ExtractedNode] = Field(default_factory=list)
    edges: List[ExtractedEdge] = Field(default_factory=list)

    def merge(self, other: "GraphExtractionResult") -> "GraphExtractionResult":
        """Fonde due risultati di estrazione."""
        return GraphExtractionResult(
            nodes=self.nodes + other.nodes,
            edges=self.edges + other.edges,
        )


# --------------------------------------------------------------------------- #
# Prompt (fisso, unico)
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = """You are an expert at extracting entities and relationships from text.

Given a text, extract:
1. Entities (nodes): people, organizations, locations, concepts, events, documents, laws, etc.
2. Relationships (edges): connections between entities.

Output a JSON object with this exact structure:
{
  "nodes": [
    {"name": "Mario Rossi", "label": "Persona", "properties": {}}
  ],
  "edges": [
    {"source": "Mario Rossi", "target": "Acme SRL", "type": "LAVORA_PER", "properties": {}}
  ]
}

Rules:
- Reference nodes BY NAME in edges (source/target are the exact node names).
- Use the same name for the same entity everywhere (deduplicate in your head before output).
- Labels are semantic (Italian or English): "Persona", "Organizzazione", "Luogo", "Concetto", "Evento", "Legge", etc.
- Relationship types in UPPER_SNAKE_CASE.
- If no entities/relationships found, return empty arrays.
- Output ONLY valid JSON, no markdown fences."""

_USER_PROMPT_TEMPLATE = """Extract entities and relationships from this text:

---BEGIN TEXT---
{text}
---END TEXT---

Output JSON:"""


# --------------------------------------------------------------------------- #
# Eccezioni
# --------------------------------------------------------------------------- #


class ExtractionError(RuntimeError):
    """Errore durante l'estrazione entità-relazioni."""


# --------------------------------------------------------------------------- #
# Extractor
# --------------------------------------------------------------------------- #


class EntityRelationExtractor:
    """Estrattore di entità e relazioni da chunk di testo.

    Args:
        llm: strategia LLM per l'estrazione.
    """

    def __init__(self, llm: Any) -> None:  # LLMStrategy — Any per evitare import circolari
        self._llm = llm

    def extract(
        self,
        text: str,
        chunk_id: Optional[str] = None,
    ) -> GraphExtractionResult:
        """Estrae entità e relazioni da un singolo chunk.

        JSON invalido → warning + risultato vuoto (mai un errore bloccante).
        """
        if not text.strip():
            return GraphExtractionResult()

        user_prompt = _USER_PROMPT_TEMPLATE.format(text=text)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            raw_response = self._llm.generate(
                messages, max_tokens=4096, temperature=0.0
            )
        except Exception as exc:
            raise ExtractionError(f"Errore nella chiamata LLM: {exc}") from exc

        return self._parse_response(raw_response, chunk_id)

    def extract_batch(
        self,
        chunks: List[Dict[str, Any]],
    ) -> GraphExtractionResult:
        """Estrae da una lista di chunk (per-chunk, aggregato)."""
        combined = GraphExtractionResult()
        for chunk in chunks:
            text = chunk.get("text", "")
            chunk_id = chunk.get("chunk_id")
            result = self.extract(text, chunk_id=chunk_id)
            combined = combined.merge(result)
        return combined

    def _parse_response(
        self,
        raw: str,
        chunk_id: Optional[str] = None,
    ) -> GraphExtractionResult:
        """Parse la risposta JSON dell'LLM in un ``GraphExtractionResult``."""
        cleaned = self._extract_json(raw)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Risposta LLM non è JSON valido: %s", exc)
            return GraphExtractionResult()

        nodes = []
        for n in data.get("nodes", []):
            nodes.append(ExtractedNode(
                name=n.get("name", ""),
                label=n.get("label", "Entità"),
                properties=n.get("properties", {}),
                chunk_id=chunk_id,
            ))

        edges = []
        for e in data.get("edges", []):
            edges.append(ExtractedEdge(
                source=e.get("source", ""),
                target=e.get("target", ""),
                type=e.get("type", "RELATED_TO"),
                properties=e.get("properties", {}),
                chunk_id=chunk_id,
            ))

        return GraphExtractionResult(nodes=nodes, edges=edges)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Estrae JSON da una risposta che potrebbe contenere markdown fences."""
        # Blocco JSON tra ```json ... ``` o ``` ... ```
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Oggetto JSON { ... }
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)

        return text.strip()
