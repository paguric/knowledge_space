#!/usr/bin/env python3
"""Extract text from generated documents (PDF, DOCX).

Reads documents from documents/ and generates clean .txt/.md files.
The extracted files serve as ground-truth for testing the ingestion pipeline.

Usage:
    python extract.py [--input-dir DIR] [--output-dir DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Optional dependencies for extraction
try:
    import fitz  # pymupdf
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import pymupdf4llm
    HAS_PYMUPDF4LLM = True
except ImportError:
    HAS_PYMUPDF4LLM = False


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF file."""
    if HAS_PYMUPDF:
        doc = fitz.open(str(pdf_path))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    else:
        print(f"  [WARN] pymupdf not available — cannot extract from {pdf_path.name}")
        return ""


def extract_pdf_markdown(pdf_path: Path) -> str:
    """Extract text from a PDF as markdown (using pymupdf4llm if available)."""
    if HAS_PYMUPDF4LLM:
        return pymupdf4llm.to_markdown(str(pdf_path))
    else:
        return extract_pdf_text(pdf_path)


def extract_docx_text(docx_path: Path) -> str:
    """Extract text from a DOCX file."""
    if HAS_DOCX:
        doc = DocxDocument(str(docx_path))
        paragraphs = []
        for para in doc.paragraphs:
            if para.text.strip():
                paragraphs.append(para.text)
        return "\n\n".join(paragraphs)
    else:
        print(f"  [WARN] python-docx not available — cannot extract from {docx_path.name}")
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from legal documents")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("tests/data/synthetic/legal/documents"),
        help="Input directory with documents",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: same as input-dir)",
    )
    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir or input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        print(f"Error: input directory {input_dir} does not exist")
        print("Run fetch.py first to generate the documents.")
        sys.exit(1)

    print(f"Input:  {input_dir}")
    print(f"Output: {output_dir}")

    # Process PDFs
    pdf_files = sorted(input_dir.glob("*.pdf"))
    for pdf_path in pdf_files:
        out_name = pdf_path.stem + "_extracted.txt"
        out_path = output_dir / out_name
        if out_path.exists():
            print(f"  [SKIP] {out_name} already exists")
            continue
        print(f"Extracting: {pdf_path.name} -> {out_name}")
        text = extract_pdf_text(pdf_path)
        if text:
            out_path.write_text(text, encoding="utf-8")

    # Process DOCX files
    docx_files = sorted(input_dir.glob("*.docx"))
    for docx_path in docx_files:
        out_name = docx_path.stem + "_extracted.txt"
        out_path = output_dir / out_name
        if out_path.exists():
            print(f"  [SKIP] {out_name} already exists")
            continue
        print(f"Extracting: {docx_path.name} -> {out_name}")
        text = extract_docx_text(docx_path)
        if text:
            out_path.write_text(text, encoding="utf-8")

    print("\nExtraction complete.")


if __name__ == "__main__":
    main()
