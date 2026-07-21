"""Strategie di chunking registrate nel registry.

Step 5 implementerà la logica completa di ciascuna strategia; qui si
registrano gli stub minimi affinché il registry sia popolato all'avvio.
"""

from __future__ import annotations

from typing import List

from knowledge_base.strategies import ChunkingStrategy, chunking_registry


class FixedSizeChunking:
    """Chunking a dimensione fissa (overlap=0 no-overlap, >0 sliding window)."""

    name = "fixed_size"
    requires_embedding = False

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200, separator: str = "\n\n", **params) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator
        self.params = params

    def split(self, text: str) -> List[str]:
        from langchain_text_splitters import CharacterTextSplitter

        splitter = CharacterTextSplitter(
            separator=self.separator,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )
        return splitter.split_text(text)


class RecursiveChunking:
    """Chunking ricorsivo con separatori gerarchici."""

    name = "recursive"
    requires_embedding = False

    def __init__(self, **params) -> None:
        self.params = params

    def split(self, text: str) -> List[str]:
        raise NotImplementedError("Step 5 — non ancora implementato")


class SemanticChunking:
    """Chunking semantico (richiede embedding)."""

    name = "semantic"
    requires_embedding = True

    def __init__(self, **params) -> None:
        self.params = params

    def split(self, text: str) -> List[str]:
        raise NotImplementedError("Step 5 — non ancora implementato")


class SentenceChunking:
    """Chunking per frase/paragrafo."""

    name = "sentence"
    requires_embedding = False

    def __init__(self, **params) -> None:
        self.params = params

    def split(self, text: str) -> List[str]:
        raise NotImplementedError("Step 5 — non ancora implementato")


class MarkdownChunking:
    """Chunking basato su header Markdown."""

    name = "markdown"
    requires_embedding = False

    def __init__(self, **params) -> None:
        self.params = params

    def split(self, text: str) -> List[str]:
        raise NotImplementedError("Step 5 — non ancora implementato")


# Registrazione all'avvio
chunking_registry.register("fixed_size", FixedSizeChunking)
chunking_registry.register("recursive", RecursiveChunking)
chunking_registry.register("semantic", SemanticChunking)
chunking_registry.register("sentence", SentenceChunking)
chunking_registry.register("markdown", MarkdownChunking)
