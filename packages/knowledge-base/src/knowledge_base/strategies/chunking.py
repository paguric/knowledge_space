"""Strategie di chunking: suddivisione del testo Markdown in frammenti.

Ogni strategia implementa un algoritmo di split e registra metadati
discoverable (``params_schema``, ``requires_embedding``). Il testo
proviene dall'ingestion; i chunk prodotti vengono scritti su disco
(Step 7) e indicizzati in Chroma.

I parametri sono passati al costruttore (dal ``BaseConfig.chunking``);
``split(text)`` restituisce una lista di dict con almeno ``"text"`` (str)
e ``"index"`` (int). Le strategie avanzate (es. ``markdown``) possono
aggiungere metadata (es. ``"header_1"``).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from knowledge_base.strategies import ChunkingStrategy, chunking_registry

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Classe base
# --------------------------------------------------------------------------- #


class BaseChunking:
    """Base comune: assegna ``index`` a ogni chunk prodotto da ``_split``.

    Le sottoclassi implementano ``_split`` restituendo ``List[str]`` (chunk
    semplici) o ``List[dict]`` (chunk con metadata). Il metodo ``split``
    normalizza tutto in ``List[dict]`` con ``"text"`` e ``"index"``.
    """

    name: str = ""
    params_schema: Dict[str, type] = {}
    requires_embedding: bool = False

    def split(self, text: str) -> List[Dict[str, Any]]:
        raw = self._split(text)
        result: List[Dict[str, Any]] = []
        for i, item in enumerate(raw):
            if isinstance(item, str):
                result.append({"text": item, "index": i})
            elif isinstance(item, dict):
                if "text" not in item:
                    raise ValueError(f"Chunk dict senza 'text': {item}")
                item.setdefault("index", i)
                result.append(item)
            else:
                raise TypeError(f"Tipo chunk non supportato: {type(item)}")
        return result

    def _split(self, text: str) -> List[Any]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# fixed_size — CharacterTextSplitter
# --------------------------------------------------------------------------- #


class FixedSizeChunking(BaseChunking):
    """Chunking a dimensione fissa per caratteri.

    - ``chunk_overlap = 0`` → **no-overlap**: ogni carattere appartiene a
      un solo chunk.
    - ``chunk_overlap > 0`` → **sliding window**: i chunk si sovrappongono
      di ``chunk_overlap`` caratteri.

    Usa ``langchain_text_splitters.CharacterTextSplitter``.
    """

    name = "fixed_size"
    params_schema: Dict[str, type] = {
        "chunk_size": int,
        "chunk_overlap": int,
        "separator": str,
    }
    requires_embedding = False

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        separator: str = "\n\n",
        **params,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator
        self.params = params

    def _split(self, text: str) -> List[str]:
        from langchain_text_splitters import CharacterTextSplitter

        splitter = CharacterTextSplitter(
            separator=self.separator,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )
        pieces = splitter.split_text(text)

        # Safety-net: se un pezzo supera chunk_size (paragrafo monolitico),
        # ri-splittalo con RecursiveCharacterTextSplitter.
        oversized = [p for p in pieces if len(p) > self.chunk_size]
        if oversized:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            fallback = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                length_function=len,
                is_separator_regex=False,
            )
            result: List[str] = []
            for piece in pieces:
                if len(piece) > self.chunk_size:
                    result.extend(fallback.split_text(piece))
                else:
                    result.append(piece)
            return result

        return pieces


# --------------------------------------------------------------------------- #
# recursive — RecursiveCharacterTextSplitter
# --------------------------------------------------------------------------- #


class RecursiveChunking(BaseChunking):
    """Chunking gerarchico con separatori annidati.

    Prova i separatori in ordine: ``"\\n\\n"``, ``"\\n"``, ``" "``, ``""``.
    Ideale per testo generico (Markdown, prosa).

    Usa ``langchain_text_splitters.RecursiveCharacterTextSplitter``.
    """

    name = "recursive"
    params_schema: Dict[str, type] = {
        "chunk_size": int,
        "chunk_overlap": int,
        "separators": list,
    }
    requires_embedding = False

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        separators: Optional[List[str]] = None,
        **params,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = (
            separators if separators is not None else ["\n\n", "\n", " ", ""]
        )
        self.params = params

    def _split(self, text: str) -> List[str]:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            separators=self.separators,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )
        return splitter.split_text(text)


# --------------------------------------------------------------------------- #
# semantic — custom, richiede embedder
# --------------------------------------------------------------------------- #


class SemanticChunking(BaseChunking):
    """Chunking semantico basato su similarità tra frasi adiacenti.

    **Richiede un modello di embedding** (``requires_embedding = True``).
    Ogni frase viene embeddata e il boundary viene posto dove la
    similarità cosine tra embedding consecutivi scende sotto una soglia.

    Implementazione custom (non usa ``langchain_experimental``) per
    integrare direttamente la nostra ``EmbeddingStrategy``: l'embedder
    è passato al costruttore e deve avere un metodo
    ``embed(texts: List[str]) -> List[List[float]]``.
    """

    name = "semantic"
    params_schema: Dict[str, type] = {
        "breakpoint_threshold_type": str,
        "buffer_size": int,
    }
    requires_embedding = True

    def __init__(
        self,
        embedder: Any = None,
        breakpoint_threshold_type: str = "percentile",
        buffer_size: int = 1,
        **params,
    ) -> None:
        self.embedder = embedder
        self.breakpoint_threshold_type = breakpoint_threshold_type
        self.buffer_size = buffer_size
        self.params = params

    def _split(self, text: str) -> List[str]:
        if self.embedder is None:
            raise ValueError(
                "SemanticChunking richiede un embedder. "
                "Passarlo al costruttore come embedder=..."
            )

        import numpy as np

        # 1. Split into sentences
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return sentences

        # 2. Group by buffer_size
        groups = self._group_sentences(sentences, self.buffer_size)
        if len(groups) <= 1:
            return [" ".join(sentences)]

        # 3. Embed each group
        embeddings = np.array(self.embedder.embed(groups))

        # 4. Cosine similarity between adjacent groups
        similarities = [
            self._cosine_similarity(embeddings[i], embeddings[i + 1])
            for i in range(len(embeddings) - 1)
        ]

        # 5. Compute threshold
        threshold = self._compute_threshold(np.array(similarities))

        # 6. Group into chunks: breakpoint where similarity < threshold
        chunks = []
        current = [groups[0]]
        for i, sim in enumerate(similarities):
            if sim < threshold:
                chunks.append(" ".join(current))
                current = [groups[i + 1]]
            else:
                current.append(groups[i + 1])
        if current:
            chunks.append(" ".join(current))

        return chunks

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def _group_sentences(sentences: List[str], buffer_size: int) -> List[str]:
        if buffer_size <= 1:
            return sentences
        groups = []
        for i in range(0, len(sentences), buffer_size):
            groups.append(" ".join(sentences[i : i + buffer_size]))
        return groups

    @staticmethod
    def _cosine_similarity(a, b) -> float:
        import numpy as np

        dot = float(np.dot(a, b))
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _compute_threshold(self, similarities) -> float:
        import numpy as np

        if self.breakpoint_threshold_type == "standard_deviation":
            return float(similarities.mean() - similarities.std())
        elif self.breakpoint_threshold_type == "interquartile":
            q1, q3 = np.percentile(similarities, [25, 75])
            iqr = q3 - q1
            return float(q3 - 1.5 * iqr)
        else:  # "percentile" (default)
            return float(np.percentile(similarities, 95))


# --------------------------------------------------------------------------- #
# sentence — regex, granularity sentence | paragraph
# --------------------------------------------------------------------------- #


class SentenceChunking(BaseChunking):
    """Chunking per confini di frase o paragrafo.

    - ``granularity = "sentence"`` (default): un chunk per frase.
      Boundary su ``.``, ``?``, ``!`` seguiti da whitespace.
    - ``granularity = "paragraph"``: un chunk per paragrafo
      (separati da riga vuota, ``\\n\\n``).

    Usa regex (no NLTK) per il rilevamento dei confini.
    """

    name = "sentence"
    params_schema: Dict[str, type] = {"granularity": str}
    requires_embedding = False

    def __init__(self, granularity: str = "sentence", **params) -> None:
        self.granularity = granularity
        self.params = params

    def _split(self, text: str) -> List[str]:
        if self.granularity == "paragraph":
            paragraphs = re.split(r"\n\s*\n", text.strip())
            return [p.strip() for p in paragraphs if p.strip()]
        # Default: sentence
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]


# --------------------------------------------------------------------------- #
# markdown — MarkdownHeaderTextSplitter
# --------------------------------------------------------------------------- #


class MarkdownChunking(BaseChunking):
    """Chunking basato su header Markdown.

    Usa ``langchain_text_splitters.MarkdownHeaderTextSplitter``: i chunk
    sono delimitati dagli header (``#``, ``##``, ``###``). Il testo
    dentro un code block resta intatto (lo splitter agisce solo sugli
    header).

    I chunk includono metadata con gli header di provenienza
    (``"header_1"``, ``"header_2"``, ``"header_3"``).
    """

    name = "markdown"
    params_schema: Dict[str, type] = {"headers_to_split_on": list}
    requires_embedding = False

    _DEFAULT_HEADERS = [
        ["#", "header_1"],
        ["##", "header_2"],
        ["###", "header_3"],
    ]

    def __init__(
        self,
        headers_to_split_on: Optional[List[List[str]]] = None,
        **params,
    ) -> None:
        self.headers_to_split_on = (
            headers_to_split_on
            if headers_to_split_on is not None
            else [list(h) for h in self._DEFAULT_HEADERS]
        )
        self.params = params

    def _split(self, text: str) -> List[Dict[str, Any]]:
        from langchain_text_splitters import MarkdownHeaderTextSplitter

        splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on,
        )
        documents = splitter.split_text(text)
        result: List[Dict[str, Any]] = []
        for doc in documents:
            entry: Dict[str, Any] = {"text": doc.page_content}
            for k, v in doc.metadata.items():
                if v:
                    entry[k] = v
            result.append(entry)
        return result


# --------------------------------------------------------------------------- #
# Registrazione all'avvio
# --------------------------------------------------------------------------- #

chunking_registry.register("fixed_size", FixedSizeChunking)
chunking_registry.register("recursive", RecursiveChunking)
chunking_registry.register("semantic", SemanticChunking)
chunking_registry.register("sentence", SentenceChunking)
chunking_registry.register("markdown", MarkdownChunking)
