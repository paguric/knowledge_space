"""Entity and relation extraction from text chunks via LLM.

``EntityRelationExtractor`` usa un LLM per estrarre entità e relazioni
dai chunk di testo. Produce un ``GraphExtractionResult`` con nodi, archi
e proprietà.

Il prompt di estrazione è configurabile; il default estrae:
- Entità con tipo (label), nome e proprietà
- Relazioni con tipo, source e target

L'LLM è iniettato come ``LLMStrategy`` (lazy import del modulo strategies).
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
    """Nodo estratto da un chunk."""

    id: str  # identificatore univoco nell'estrazione (transiente)
    label: str  # tipo di entità (es. "Person", "Organization")
    name: str  # nome dell'entità
    properties: Dict[str, Any] = Field(default_factory=dict)
    chunk_id: Optional[str] = None  # chunk sorgente


class ExtractedEdge(BaseModel):
    """Arco estratto da un chunk."""

    source_id: str  # id del nodo sorgente (nell'estrazione)
    target_id: str  # id del nodo target (nell'estrazione)
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
# Prompt default
# --------------------------------------------------------------------------- #

_DEFAULT_SYSTEM_PROMPT = """You are an expert at extracting entities and relationships from text.

Given a text, extract:
1. Entities (nodes): people, organizations, locations, concepts, events, etc.
2. Relationships (edges): connections between entities.

Output a JSON object with this exact structure:
{
  "nodes": [
    {"id": "n1", "label": "Person", "name": "John Doe", "properties": {}}
  ],
  "edges": [
    {"source_id": "n1", "target_id": "n2", "type": "WORKS_AT", "properties": {}}
  ]
}

Rules:
- Use meaningful entity labels (Person, Organization, Location, Concept, Event, etc.)
- Use UPPER_SNAKE_CASE for relationship types
- Include all relevant properties on nodes and edges
- IDs are local to this extraction (n1, n2, etc.)
- If no entities/relationships found, return empty arrays
- Output ONLY valid JSON, no markdown fences"""

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

    Usa un LLM (iniettato come ``LLMStrategy``) per analizzare il testo
    e produrre un grafo di entità e relazioni.

    Args:
        llm: strategia LLM per l'estrazione.
        system_prompt: prompt di sistema (opzionale, usa default).
    """

    def __init__(
        self,
        llm: Any,  # LLMStrategy — Any per evitare import circolari
        system_prompt: Optional[str] = None,
    ) -> None:
        self._llm = llm
        self._system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT

    def extract(self, text: str, chunk_id: Optional[str] = None) -> GraphExtractionResult:
        """Estrae entità e relazioni da un singolo chunk.

        Args:
            text: testo del chunk.
            chunk_id: id del chunk sorgente (opzionale, propagato ai nodi/archi).

        Returns:
            ``GraphExtractionResult`` con nodi e archi estratti.

        Raises:
            ExtractionError: se l'LLM non restituisce JSON valido.
        """
        if not text.strip():
            return GraphExtractionResult()

        user_prompt = _USER_PROMPT_TEMPLATE.format(text=text)
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            raw_response = self._llm.generate(messages, max_tokens=4096, temperature=0.0)
        except Exception as exc:
            raise ExtractionError(f"Errore nella chiamata LLM: {exc}") from exc

        return self._parse_response(raw_response, chunk_id)

    def extract_batch(
        self,
        chunks: List[Dict[str, Any]],
    ) -> GraphExtractionResult:
        """Estrae entità e relazioni da una lista di chunk.

        Args:
            chunks: lista di dict con almeno ``"text"`` e opzionalmente ``"chunk_id"``.

        Returns:
            ``GraphExtractionResult`` fuso da tutti i chunk.
        """
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
        # Tenta di estrarre JSON dalla risposta (potrebbe contenere markdown fences)
        cleaned = self._extract_json(raw)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Risposta LLM non è JSON valido: %s", exc)
            # Fallback: ritorna risultato vuoto
            return GraphExtractionResult()

        nodes = []
        for n in data.get("nodes", []):
            nodes.append(ExtractedNode(
                id=n.get("id", ""),
                label=n.get("label", "Unknown"),
                name=n.get("name", ""),
                properties=n.get("properties", {}),
                chunk_id=chunk_id,
            ))

        edges = []
        for e in data.get("edges", []):
            edges.append(ExtractedEdge(
                source_id=e.get("source_id", ""),
                target_id=e.get("target_id", ""),
                type=e.get("type", "RELATED_TO"),
                properties=e.get("properties", {}),
                chunk_id=chunk_id,
            ))

        return GraphExtractionResult(nodes=nodes, edges=edges)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Estrae JSON da una risposta che potrebbe contenere markdown fences."""
        # Prova a trovare blocco JSON tra ```json ... ``` o ``` ... ```
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Prova a trovare un oggetto JSON { ... }
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)

        # Restituisce il testo così com'è
        return text.strip()
