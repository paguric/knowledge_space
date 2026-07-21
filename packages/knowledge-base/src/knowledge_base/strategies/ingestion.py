"""Strategie di ingestion registrate nel registry.

Step 4 implementerà la logica completa di ciascuna strategia; qui si
registrano gli stub minimi affinché il registry sia popolato all'avvio.
"""

from __future__ import annotations

from typing import List

from knowledge_base.strategies import IngestionStrategy, ingestion_registry


class DoclingIngestion:
    """Ingestion via Docling (PDF, profilo ricercatore)."""

    name = "docling"
    supported_extensions: List[str] = [".pdf"]

    def __init__(self, **params) -> None:
        self.params = params

    def convert(self, source_path: str) -> str:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        doc = converter.convert(source_path).document
        return doc.export_to_markdown()


class PyMuPDF4LLMIngestion:
    """Ingestion via PyMuPDF4LLM (PDF, profilo consulente)."""

    name = "pymupdf4llm"
    supported_extensions: List[str] = [".pdf"]

    def __init__(self, **params) -> None:
        self.params = params

    def convert(self, source_path: str) -> str:
        raise NotImplementedError("Step 4 — non ancora implementato")


class MarkItDownIngestion:
    """Ingestion via MarkItDown (PPTX, MD, profilo studente)."""

    name = "markitdown"
    supported_extensions: List[str] = [".pptx", ".md"]

    def __init__(self, **params) -> None:
        self.params = params

    def convert(self, source_path: str) -> str:
        raise NotImplementedError("Step 4 — non ancora implementato")


# Registrazione all'avvio
ingestion_registry.register("docling", DoclingIngestion)
ingestion_registry.register("pymupdf4llm", PyMuPDF4LLMIngestion)
ingestion_registry.register("markitdown", MarkItDownIngestion)
