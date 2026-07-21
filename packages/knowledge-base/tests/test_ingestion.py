"""Test per le strategie di ingestion (Step 4).

Copre:
- IdentityIngestion: lettura diretta di .md/.txt (test reali con tmp_path).
- DoclingIngestion: parametri passati a PdfPipelineOptions; mock del converter.
- PyMuPDF4LLMIngestion: parametri passati a to_markdown; mock del modulo.
- MarkItDownIngestion: parametri passati a MarkItDown; mock del modulo.
- Validazione estensioni: UnsupportedFormatError per formato non ammesso.
- Registry: tutte le strategie registrate con i metadati corretti.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from knowledge_base.strategies import ingestion_registry
from knowledge_base.strategies.ingestion import (
    DoclingIngestion,
    IdentityIngestion,
    MarkItDownIngestion,
    PyMuPDF4LLMIngestion,
    UnsupportedFormatError,
)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


class TestIngestionRegistry:
    def test_all_four_strategies_registered(self):
        assert set(ingestion_registry.list_names()) == {
            "identity", "docling", "pymupdf4llm", "markitdown",
        }

    def test_registry_returns_correct_classes(self):
        assert ingestion_registry.get("identity") is IdentityIngestion
        assert ingestion_registry.get("docling") is DoclingIngestion
        assert ingestion_registry.get("pymupdf4llm") is PyMuPDF4LLMIngestion
        assert ingestion_registry.get("markitdown") is MarkItDownIngestion

    def test_registry_unknown_name_raises(self):
        with pytest.raises(KeyError, match="non trovata"):
            ingestion_registry.get("nonexistent")

    def test_strategy_metadata_attributes(self):
        for name in ingestion_registry.list_names():
            cls = ingestion_registry.get(name)
            inst = cls()
            assert inst.name == name
            assert isinstance(inst.library, str) and inst.library
            assert isinstance(inst.supported_extensions, list)
            assert all(e.startswith(".") for e in inst.supported_extensions)


# --------------------------------------------------------------------------- #
# IdentityIngestion — test reali (nessuna libreria esterna)
# --------------------------------------------------------------------------- #


class TestIdentityIngestion:
    def test_convert_markdown(self, tmp_path):
        f = tmp_path / "notes.md"
        f.write_text("# Title\n\nSome **markdown**.", encoding="utf-8")
        strategy = IdentityIngestion()
        assert strategy.convert(f) == "# Title\n\nSome **markdown**."

    def test_convert_txt(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Plain text content.", encoding="utf-8")
        strategy = IdentityIngestion()
        assert strategy.convert(f) == "Plain text content."

    def test_unsupported_extension_raises(self, tmp_path):
        f = tmp_path / "file.pdf"
        f.write_bytes(b"%PDF-1.4")
        strategy = IdentityIngestion()
        with pytest.raises(UnsupportedFormatError, match="\\.pdf"):
            strategy.convert(f)

    def test_params_ignored(self, tmp_path):
        f = tmp_path / "x.md"
        f.write_text("content", encoding="utf-8")
        strategy = IdentityIngestion(use_gpu=True, do_ocr=True)
        assert strategy.convert(f) == "content"

    def test_case_insensitive_extension(self, tmp_path):
        f = tmp_path / "UPPER.MD"
        f.write_text("ci content", encoding="utf-8")
        assert IdentityIngestion().convert(f) == "ci content"


# --------------------------------------------------------------------------- #
# DoclingIngestion — mock del converter, PdfPipelineOptions reale
# --------------------------------------------------------------------------- #


def _make_fake_docling_converter(markdown: str = "# Doc\n\nBody"):
    """Costruisce un mock di DocumentConverter che restituisce markdown."""
    fake_doc = MagicMock()
    fake_doc.export_to_markdown.return_value = markdown
    fake_result = MagicMock()
    fake_result.document = fake_doc
    fake_converter = MagicMock()
    fake_converter.convert.return_value = fake_result
    return fake_converter


class TestDoclingIngestion:
    def test_convert_returns_markdown(self, tmp_path):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        fake = _make_fake_docling_converter("# Paper\n\nAbstract")
        with patch(
            "docling.document_converter.DocumentConverter",
            return_value=fake,
        ) as mock_cls:
            result = DoclingIngestion().convert(pdf)
        assert result == "# Paper\n\nAbstract"
        mock_cls.assert_called_once()
        fake.convert.assert_called_once_with(pdf)

    def test_default_params(self, tmp_path):
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF")
        fake = _make_fake_docling_converter()
        with patch(
            "docling.document_converter.DocumentConverter",
            return_value=fake,
        ) as mock_cls:
            DoclingIngestion().convert(pdf)
        kwargs = mock_cls.call_args.kwargs
        from docling.datamodel.base_models import InputFormat
        opts = kwargs["format_options"][InputFormat.PDF].pipeline_options
        assert opts.do_ocr is False
        assert opts.do_table_structure is True
        assert opts.table_structure_options.mode.value == "accurate"
        assert opts.generate_page_images is False
        assert opts.generate_picture_images is True  # image_export default "reference"

    def test_custom_params(self, tmp_path):
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF")
        fake = _make_fake_docling_converter()
        with patch(
            "docling.document_converter.DocumentConverter",
            return_value=fake,
        ) as mock_cls:
            DoclingIngestion(
                do_ocr=True,
                do_table_structure=False,
                table_mode="fast",
                generate_page_images=True,
                image_export="none",
            ).convert(pdf)
        from docling.datamodel.base_models import InputFormat
        opts = mock_cls.call_args.kwargs["format_options"][InputFormat.PDF].pipeline_options
        assert opts.do_ocr is True
        assert opts.do_table_structure is False
        assert opts.table_structure_options.mode.value == "fast"
        assert opts.generate_page_images is True
        assert opts.generate_picture_images is False  # image_export="none"

    def test_use_gpu_sets_cuda_device(self, tmp_path):
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF")
        fake = _make_fake_docling_converter()
        with patch(
            "docling.document_converter.DocumentConverter",
            return_value=fake,
        ) as mock_cls:
            DoclingIngestion(use_gpu=True).convert(pdf)
        from docling.datamodel.base_models import InputFormat
        opts = mock_cls.call_args.kwargs["format_options"][InputFormat.PDF].pipeline_options
        assert opts.accelerator_options.device.value == "cuda"

    def test_use_gpu_false_keeps_auto(self, tmp_path):
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF")
        fake = _make_fake_docling_converter()
        with patch(
            "docling.document_converter.DocumentConverter",
            return_value=fake,
        ) as mock_cls:
            DoclingIngestion(use_gpu=False).convert(pdf)
        from docling.datamodel.base_models import InputFormat
        opts = mock_cls.call_args.kwargs["format_options"][InputFormat.PDF].pipeline_options
        assert opts.accelerator_options.device.value == "auto"

    def test_unsupported_extension_raises(self, tmp_path):
        f = tmp_path / "file.xyz"
        f.write_text("nope")
        with pytest.raises(UnsupportedFormatError, match="\\.xyz"):
            DoclingIngestion().convert(f)

    def test_supported_docx(self, tmp_path):
        docx = tmp_path / "contract.docx"
        docx.write_bytes(b"PK fake docx")
        fake = _make_fake_docling_converter("# Contract")
        with patch(
            "docling.document_converter.DocumentConverter",
            return_value=fake,
        ):
            assert DoclingIngestion().convert(docx) == "# Contract"


# --------------------------------------------------------------------------- #
# PyMuPDF4LLMIngestion — mock del modulo (non installato)
# --------------------------------------------------------------------------- #


class TestPyMuPDF4LLMIngestion:
    def test_convert_returns_markdown(self, tmp_path):
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF")
        fake_mod = MagicMock()
        fake_mod.to_markdown.return_value = "# Book\n\nChapter 1"
        with patch.dict(sys.modules, {"pymupdf4llm": fake_mod}):
            result = PyMuPDF4LLMIngestion().convert(pdf)
        assert result == "# Book\n\nChapter 1"
        fake_mod.to_markdown.assert_called_once()

    def test_params_passed_to_to_markdown(self, tmp_path):
        pdf = tmp_path / "b.pdf"
        pdf.write_bytes(b"%PDF")
        fake_mod = MagicMock()
        fake_mod.to_markdown.return_value = "md"
        with patch.dict(sys.modules, {"pymupdf4llm": fake_mod}):
            PyMuPDF4LLMIngestion(
                page_chunks=True,
                write_images=True,
                extract_mode="multicolumn",
                margins=10,
                show_progress=True,
            ).convert(pdf)
        kwargs = fake_mod.to_markdown.call_args.kwargs
        assert kwargs["page_chunks"] is True
        assert kwargs["write_images"] is True
        assert kwargs["extract_mode"] == "multicolumn"
        assert kwargs["margins"] == 10
        assert kwargs["show_progress"] is True

    def test_default_params(self, tmp_path):
        pdf = tmp_path / "b.pdf"
        pdf.write_bytes(b"%PDF")
        fake_mod = MagicMock()
        fake_mod.to_markdown.return_value = "md"
        with patch.dict(sys.modules, {"pymupdf4llm": fake_mod}):
            PyMuPDF4LLMIngestion().convert(pdf)
        kwargs = fake_mod.to_markdown.call_args.kwargs
        assert kwargs["page_chunks"] is False
        assert kwargs["write_images"] is False
        assert kwargs["extract_mode"] == "standard"
        assert kwargs["margins"] == 5
        assert kwargs["show_progress"] is False

    def test_page_chunks_list_result_joined(self, tmp_path):
        pdf = tmp_path / "b.pdf"
        pdf.write_bytes(b"%PDF")
        fake_mod = MagicMock()
        fake_mod.to_markdown.return_value = ["Page 1", "Page 2", "Page 3"]
        with patch.dict(sys.modules, {"pymupdf4llm": fake_mod}):
            result = PyMuPDF4LLMIngestion(page_chunks=True).convert(pdf)
        assert result == "Page 1\n\nPage 2\n\nPage 3"

    def test_use_gpu_ignored(self, tmp_path):
        pdf = tmp_path / "b.pdf"
        pdf.write_bytes(b"%PDF")
        fake_mod = MagicMock()
        fake_mod.to_markdown.return_value = "md"
        with patch.dict(sys.modules, {"pymupdf4llm": fake_mod}):
            result = PyMuPDF4LLMIngestion(use_gpu=True).convert(pdf)
        assert result == "md"

    def test_unsupported_extension_raises(self, tmp_path):
        f = tmp_path / "file.pptx"
        f.write_bytes(b"PK")
        with pytest.raises(UnsupportedFormatError, match="\\.pptx"):
            PyMuPDF4LLMIngestion().convert(f)


# --------------------------------------------------------------------------- #
# MarkItDownIngestion — mock del modulo (non installato)
# --------------------------------------------------------------------------- #


class TestMarkItDownIngestion:
    def test_convert_returns_text_content(self, tmp_path):
        pptx = tmp_path / "slides.pptx"
        pptx.write_bytes(b"PK fake pptx")
        fake_mod = MagicMock()
        fake_md = MagicMock()
        fake_md.convert.return_value = MagicMock(text_content="# Slides")
        fake_mod.MarkItDown.return_value = fake_md
        with patch.dict(sys.modules, {"markitdown": fake_mod}):
            result = MarkItDownIngestion().convert(pptx)
        assert result == "# Slides"
        fake_mod.MarkItDown.assert_called_once()
        fake_md.convert.assert_called_once_with(str(pptx))

    def test_plugins_passed(self, tmp_path):
        pptx = tmp_path / "s.pptx"
        pptx.write_bytes(b"PK")
        fake_mod = MagicMock()
        fake_md = MagicMock()
        fake_md.convert.return_value = MagicMock(text_content="x")
        fake_mod.MarkItDown.return_value = fake_md
        with patch.dict(sys.modules, {"markitdown": fake_mod}):
            MarkItDownIngestion(plugins=["/path/plugin.py"]).convert(pptx)
        fake_mod.MarkItDown.assert_called_once_with(plugins=["/path/plugin.py"])

    def test_no_plugins_passes_none(self, tmp_path):
        pptx = tmp_path / "s.pptx"
        pptx.write_bytes(b"PK")
        fake_mod = MagicMock()
        fake_md = MagicMock()
        fake_md.convert.return_value = MagicMock(text_content="x")
        fake_mod.MarkItDown.return_value = fake_md
        with patch.dict(sys.modules, {"markitdown": fake_mod}):
            MarkItDownIngestion().convert(pptx)
        fake_mod.MarkItDown.assert_called_once_with(plugins=None)

    def test_use_gpu_ignored(self, tmp_path):
        pptx = tmp_path / "s.pptx"
        pptx.write_bytes(b"PK")
        fake_mod = MagicMock()
        fake_md = MagicMock()
        fake_md.convert.return_value = MagicMock(text_content="x")
        fake_mod.MarkItDown.return_value = fake_md
        with patch.dict(sys.modules, {"markitdown": fake_mod}):
            result = MarkItDownIngestion(use_gpu=True).convert(pptx)
        assert result == "x"

    def test_unsupported_extension_raises(self, tmp_path):
        f = tmp_path / "file.xyz"
        f.write_text("nope")
        with pytest.raises(UnsupportedFormatError, match="\\.xyz"):
            MarkItDownIngestion().convert(f)

    def test_supported_md(self, tmp_path):
        md = tmp_path / "notes.md"
        md.write_text("# Notes")
        fake_mod = MagicMock()
        fake_md = MagicMock()
        fake_md.convert.return_value = MagicMock(text_content="# Notes")
        fake_mod.MarkItDown.return_value = fake_md
        with patch.dict(sys.modules, {"markitdown": fake_mod}):
            assert MarkItDownIngestion().convert(md) == "# Notes"


# --------------------------------------------------------------------------- #
# Estensione maiuscola (case-insensitive) per tutte le strategy
# --------------------------------------------------------------------------- #


class TestCaseInsensitiveExtensions:
    def test_docling_uppercase_pdf(self, tmp_path):
        pdf = tmp_path / "PAPER.PDF"
        pdf.write_bytes(b"%PDF")
        fake = _make_fake_docling_converter("# ok")
        with patch("docling.document_converter.DocumentConverter", return_value=fake):
            assert DoclingIngestion().convert(pdf) == "# ok"

    def test_pymupdf4llm_uppercase_pdf(self, tmp_path):
        pdf = tmp_path / "B.PDF"
        pdf.write_bytes(b"%PDF")
        fake_mod = MagicMock()
        fake_mod.to_markdown.return_value = "ok"
        with patch.dict(sys.modules, {"pymupdf4llm": fake_mod}):
            assert PyMuPDF4LLMIngestion().convert(pdf) == "ok"
