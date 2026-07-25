"""Entity resolution: deduplicazione entità estratte.

Quando l'LLM estrae entità da chunk diversi, la stessa entità reale
(es. "Neo4j", "neo4j", "Neo4j Inc.") può comparire con nomi/label
diversi. Il resolver identifica e fonde i duplicati.

Implementazioni:
- ``ExactMatchResolver``: match esatto su nome + label (no dipendenze)
- ``SpaCySemanticMatchResolver``: similarità semantica via spaCy (richiede extra [nlp])

Fallback automatico a ``ExactMatchResolver`` se spaCy non è disponibile.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Protocol, Set, Tuple

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #


class EntityResolver(Protocol):
    """Interfaccia per la risoluzione/merge di entità duplicate.

    Il resolver opera su una lista di entità estratte (con ``id`` locale
    all'estrazione) e produce una mappa ``{local_id: canonical_id}``
    che indica quali entità devono essere fuse.
    """

    def resolve(
        self,
        entities: List[Dict[str, str]],
    ) -> Dict[str, str]:
        """Risolvi entità duplicate.

        Args:
            entities: lista di dict con ``id``, ``label``, ``name``.

        Returns:
            Mappa ``{local_id: canonical_id}``. Le entità con lo stesso
            ``canonical_id`` vanno fuse. Le entità uniche mappano a sé stesse.
        """
        ...


# --------------------------------------------------------------------------- #
# Exact match
# --------------------------------------------------------------------------- #


class ExactMatchResolver:
    """Resolver che fonde entità con lo stesso nome (case-insensitive) e label.

    Nessuna dipendenza esterna. Comportamento conservativo: solo match
    esatti dopo normalizzazione (strip + lowercase).
    """

    def resolve(
        self,
        entities: List[Dict[str, str]],
    ) -> Dict[str, str]:
        """Risolvi per match esatto su (name, label) normalizzato."""
        # Mappa (name_norm, label) → primo id incontrato (canonical)
        seen: Dict[Tuple[str, str], str] = {}
        result: Dict[str, str] = {}

        for entity in entities:
            eid = entity.get("id", "")
            name = entity.get("name", "").strip().lower()
            label = entity.get("label", "").strip().lower()
            key = (name, label)

            if key in seen:
                result[eid] = seen[key]
            else:
                seen[key] = eid
                result[eid] = eid

        return result


# --------------------------------------------------------------------------- #
# SpaCy semantic match
# --------------------------------------------------------------------------- #


class SpaCySemanticMatchResolver:
    """Resolver che usa embeddings spaCy per la similarità semantica.

    Richiede il pacchetto ``spacy`` e un modello con word vectors
    (es. ``it_core_news_md``, ``en_core_web_md``). Se spaCy non è
    disponibile, il chiamante dovrebbe fare fallback a ``ExactMatchResolver``.

    Args:
        model_name: nome del modello spaCy (default ``"en_core_web_md"``).
        threshold: soglia di similarità coseno per considerare un match (0-1).
    """

    def __init__(
        self,
        model_name: str = "en_core_web_md",
        threshold: float = 0.85,
    ) -> None:
        self._model_name = model_name
        self._threshold = threshold
        self._nlp = None

    def _load_model(self):
        """Carica il modello spaCy (lazy)."""
        if self._nlp is None:
            try:
                import spacy
            except ImportError as exc:
                raise ImportError(
                    "Il pacchetto 'spacy' è necessario per "
                    "SpaCySemanticMatchResolver. Installarlo con: "
                    "pip install spacy && python -m spacy download "
                    f"{self._model_name}"
                ) from exc
            try:
                self._nlp = spacy.load(self._model_name)
            except OSError:
                logger.warning(
                    "Modello spaCy '%s' non trovato. "
                    "Provo a usare il vocabolario vuoto.",
                    self._model_name,
                )
                self._nlp = spacy.blank("en")
        return self._nlp

    def resolve(
        self,
        entities: List[Dict[str, str]],
    ) -> Dict[str, str]:
        """Risolvi per similarità semantica via spaCy embeddings."""
        if not entities:
            return {}

        nlp = self._load_model()

        # Calcola embeddings per tutti i nomi
        docs = []
        for entity in entities:
            name = entity.get("name", "")
            doc = nlp(name)
            docs.append(doc)

        # Raggruppa per label (non fondiamo entità di tipo diverso)
        label_groups: Dict[str, List[int]] = {}
        for i, entity in enumerate(entities):
            label = entity.get("label", "").strip().lower()
            if label not in label_groups:
                label_groups[label] = []
            label_groups[label].append(i)

        result: Dict[str, str] = {}
        # Per ogni gruppo di label, trova cluster di entità simili
        for _label, indices in label_groups.items():
            # Union-Find per il clustering
            parent = {i: i for i in indices}

            def find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def union(x: int, y: int) -> None:
                px, py = find(x), find(y)
                if px != py:
                    parent[px] = py

            # Confronta ogni coppia
            for ii in range(len(indices)):
                for jj in range(ii + 1, len(indices)):
                    i, j = indices[ii], indices[jj]
                    doc_i, doc_j = docs[i], docs[j]
                    if doc_i.has_vector and doc_j.has_vector:
                        sim = doc_i.similarity(doc_j)
                        if sim >= self._threshold:
                            union(i, j)

            # Costruisci la mappa: il canonical è il primo del cluster
            cluster_canonical: Dict[int, str] = {}
            for i in indices:
                root = find(i)
                if root not in cluster_canonical:
                    cluster_canonical[root] = entities[i]["id"]
                result[entities[i]["id"]] = cluster_canonical[root]

        return result


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #


def resolver_factory(resolver_type: str = "exact") -> EntityResolver:
    """Factory per istanziare il resolver appropriato.

    Args:
        resolver_type: ``"exact"``, ``"semantic"``, o ``"none"``.

    Returns:
        Istanza di ``EntityResolver``.

    Raises:
        ValueError: se il tipo non è supportato.
    """
    if resolver_type == "none":
        return _NoOpResolver()
    if resolver_type == "exact":
        return ExactMatchResolver()
    if resolver_type == "semantic":
        try:
            return SpaCySemanticMatchResolver()
        except ImportError:
            logger.warning(
                "spaCy non disponibile. Fallback a ExactMatchResolver."
            )
            return ExactMatchResolver()
    raise ValueError(
        f"Resolver '{resolver_type}' non supportato. "
        "Disponibili: exact, semantic, none"
    )


class _NoOpResolver:
    """Resolver che non fonde nulla (ogni entità è canonical sé stessa)."""

    def resolve(
        self,
        entities: List[Dict[str, str]],
    ) -> Dict[str, str]:
        return {e["id"]: e["id"] for e in entities}
