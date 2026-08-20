"""Strategie di ingestion: conversione file sorgente → Markdown.

Ogni strategia incapsula una libreria di conversione e ne espone i parametri
configurabili via TOML (``[ingestion].params``). I parametri sono passati al
costruttore e memorizzati nell'istanza; :meth:`convert` riceve solo il path.

Le librerie pesanti (docling) e multi-formato (markitdown) sono importate
lazy dentro :meth:`convert` e sono **opzionali** (extra uv ``docling`` e
``markitdown``): se non installate, al primo utilizzo sollevano un errore
chiaro con il comando di installazione. ``pymupdf4llm`` è dipendenza hard
(default).

Parametro globale ``use_gpu`` (default ``false``): letto da ``params``.
Docling lo usa per OCR/table model (CUDA); PyMuPDF4LLM e markitdown non
beneficiano di GPU e lo ignorano.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from knowledge_base.strategies import IngestionStrategy, ingestion_registry

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Eccezioni
# --------------------------------------------------------------------------- #


class UnsupportedFormatError(ValueError):
    """Sollevata quando l'estensione del file non è supportata dalla
    strategia di ingestion scelta per la base. Il messaggio include il
    nome della library configurata (feat-011)."""

    def __init__(self, source_path: Path, supported: List[str], library: str) -> None:
        self.source_path = source_path
        self.supported = supported
        self.library = library
        ext = source_path.suffix.lower()
        super().__init__(
            f"Formato '{ext}' non supportato da {library or 'library configurata'}. "
            f"Estensioni ammesse: {', '.join(supported) or '(nessuna)'}. "
            f"File: {source_path}"
        )


class MissingLibraryError(RuntimeError):
    """Sollevata quando una libreria di conversione opzionale non è
    installata. Il messaggio include il comando di installazione."""

    def __init__(self, library: str, extra: str) -> None:
        self.library = library
        self.extra = extra
        super().__init__(
            f"Libreria '{library}' non installata. "
            f"Installa con: uv sync --extra {extra} "
            f"(poi: uv tool install --editable --force --refresh "
            f'".[{extra}]" dal root del repo)'
        )


# --------------------------------------------------------------------------- #
# Classe base
# --------------------------------------------------------------------------- #


class BaseIngestion:
    """Base comune: valida l'estensione prima di delegare a ``_convert``.

    Le sottoclassi implementano :meth:`_convert` con la logica specifica
    della libreria. Il costruttore riceve i ``params`` dal TOML.
    """

    name: str = ""
    library: str = ""
    supported_extensions: List[str] = []

    def __init__(self, **params) -> None:
        self.params = params

    def convert(self, source_path: Path) -> str:
        source_path = Path(source_path)
        ext = source_path.suffix.lower()
        if ext not in self.supported_extensions:
            raise UnsupportedFormatError(
                source_path, self.supported_extensions, self.library
            )
        return self._convert(source_path)

    def _convert(self, source_path: Path) -> str:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Identity — lettura diretta per MD/TXT (nessuna libreria)
# --------------------------------------------------------------------------- #


class IdentityIngestion(BaseIngestion):
    """Lettura diretta del file come testo. Per ``.md`` e ``.txt``.

    Nessuna conversione: il contenuto del file è già Markdown (o testo
    plain che viene trattato come Markdown). Parametri ignorati.
    """

    name = "identity"
    library = "built-in"
    supported_extensions = [".md", ".txt"]

    def _convert(self, source_path: Path) -> str:
        return source_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Docling — PDF, DOCX, PPTX, HTML (profilo ricercatore)
# --------------------------------------------------------------------------- #


class DoclingIngestion(BaseIngestion):
    """Ingestion via Docling (IBM / DS4SD).

    Profilo **ricercatore**: paper accademici, layout complesso, tabelle,
    OCR. Supporta PDF, DOCX, PPTX, HTML, immagini.

    Parametri TOML (in ``[ingestion].params``):

    - ``use_gpu`` (bool, default ``false``): usa CUDA per OCR/table model.
    - ``do_ocr`` (bool, default ``false``): OCR su immagini incorporate.
    - ``do_table_structure`` (bool, default ``true``): riconoscimento tabelle.
    - ``table_mode`` (``"accurate"`` | ``"fast"``, default ``"accurate"``).
    - ``generate_page_images`` (bool, default ``false``).
    - ``image_export`` (``"reference"`` | ``"embedded"`` | ``"none"``,
      default ``"reference"``): ``"none"`` disattiva le immagini incorporate;
      gli altri valori le attivano (l'embedding base64 è gestito in
      post-processing, qui si abilita solo l'estrazione).
    """

    name = "docling"
    library = "docling"
    supported_extensions = [".pdf", ".docx", ".pptx", ".html", ".xhtml"]

    def _convert(self, source_path: Path) -> str:
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (
                AcceleratorDevice,
                AcceleratorOptions,
                PdfPipelineOptions,
                TableFormerMode,
                TableStructureOptions,
            )
        except ImportError as exc:
            raise MissingLibraryError("docling", "docling") from exc

        use_gpu = bool(self.params.get("use_gpu", False))
        do_ocr = bool(self.params.get("do_ocr", False))
        do_table_structure = bool(self.params.get("do_table_structure", True))
        table_mode = str(self.params.get("table_mode", "accurate"))
        generate_page_images = bool(self.params.get("generate_page_images", False))
        image_export = str(self.params.get("image_export", "reference"))

        mode = (
            TableFormerMode.ACCURATE
            if table_mode == "accurate"
            else TableFormerMode.FAST
        )
        pipeline_options = PdfPipelineOptions(
            do_ocr=do_ocr,
            do_table_structure=do_table_structure,
            table_structure_options=TableStructureOptions(mode=mode),
            generate_page_images=generate_page_images,
            generate_picture_images=image_export != "none",
            accelerator_options=AcceleratorOptions(
                device=AcceleratorDevice.CUDA if use_gpu else AcceleratorDevice.AUTO
            ),
        )

        format_options = {
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
        converter = DocumentConverter(format_options=format_options)
        doc = converter.convert(source_path).document
        return doc.export_to_markdown()


# --------------------------------------------------------------------------- #
# PyMuPDF4LLM — PDF veloce multi-colonna (profilo consulente)
# --------------------------------------------------------------------------- #


class PyMuPDF4LLMIngestion(BaseIngestion):
    """Ingestion via PyMuPDF4LLM (Artifex / PyMuPDF).

    Profilo **consulente**: PDF lunghi a capitoli, multi-colonna, testi
    normativi. Molto veloce (C extension). Licenza AGPL-3.0 (PyMuPDF).

    Parametri TOML (in ``[ingestion].params``):

    - ``page_chunks`` (bool, default ``false``): output come lista pagine.
    - ``write_images`` (bool, default ``false``): estrai immagini su file.
    - ``extract_mode`` (``"standard"`` | ``"multicolumn"``, default
      ``"standard"``).
    - ``margins`` (int, default ``5``): margini in px per rilevamento colonne.
    - ``show_progress`` (bool, default ``false``).

    ``use_gpu`` è ignorato (PyMuPDF4LLM non beneficia di GPU).
    """

    name = "pymupdf4llm"
    library = "pymupdf4llm"
    supported_extensions = [".pdf"]

    def _convert(self, source_path: Path) -> str:
        try:
            import pymupdf4llm
        except ImportError as exc:
            raise MissingLibraryError("pymupdf4llm", "pymupdf4llm") from exc

        if self.params.get("use_gpu", False):
            logger.debug(
                "pymupdf4llm ignora use_gpu (nessun beneficio da CUDA)"
            )

        kwargs = {
            "page_chunks": bool(self.params.get("page_chunks", False)),
            "write_images": bool(self.params.get("write_images", False)),
            "extract_mode": str(self.params.get("extract_mode", "standard")),
            "margins": int(self.params.get("margins", 5)),
            "show_progress": bool(self.params.get("show_progress", False)),
        }
        result = pymupdf4llm.to_markdown(str(source_path), **kwargs)
        if isinstance(result, list):
            return "\n\n".join(str(p) for p in result)
        return str(result)


# --------------------------------------------------------------------------- #
# MarkItDown — PPTX, MD, DOCX, multi-formato light (profilo studente)
# --------------------------------------------------------------------------- #


class MarkItDownIngestion(BaseIngestion):
    """Ingestion via MarkItDown (Microsoft).

    Profilo **studente**: slide PPTX, appunti Markdown, documenti Office,
    formati eterogenei. Leggero e veloce. Extra opzionale
    (``uv sync --extra markitdown``): al primo utilizzo senza la libreria
    solleva :class:`MissingLibraryError`.

    Parametri TOML (in ``[ingestion].params``):

    - ``plugins`` (list[str], default ``[]``): percorsi a plugin custom.

    ``use_gpu`` è ignorato (markitdown non beneficia di GPU).
    """

    name = "markitdown"
    library = "markitdown"
    supported_extensions = [
        ".pptx", ".docx", ".pdf", ".xlsx", ".xls",
        ".html", ".txt", ".csv", ".json", ".xml", ".md",
    ]

    def _convert(self, source_path: Path) -> str:
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise MissingLibraryError("markitdown", "markitdown") from exc

        if self.params.get("use_gpu", False):
            logger.debug("markitdown ignora use_gpu (nessun beneficio da CUDA)")

        plugins = self.params.get("plugins", [])
        md = MarkItDown(plugins=list(plugins) if plugins else None)
        result = md.convert(str(source_path))
        return result.text_content


# --------------------------------------------------------------------------- #
# Registrazione all'avvio
# --------------------------------------------------------------------------- #

ingestion_registry.register("identity", IdentityIngestion)
ingestion_registry.register("docling", DoclingIngestion)
ingestion_registry.register("pymupdf4llm", PyMuPDF4LLMIngestion)
ingestion_registry.register("markitdown", MarkItDownIngestion)
