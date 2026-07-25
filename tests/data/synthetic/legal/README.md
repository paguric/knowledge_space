# Synthetic Legal Dataset

Synthetic dataset for end-to-end testing of the Knowledge Space pipeline, focused on Swiss and EU law.

## Overview

This dataset contains real legal text excerpts and fictional legal documents, designed to test:
- Multi-language ingestion (IT, DE, EN)
- Multi-format handling (TXT, MD, PDF, DOCX)
- Cross-document retrieval
- Golden query evaluation

## Documents

| # | File | Format | Language | Description |
|---|------|--------|----------|-------------|
| 1 | `ch_constitution_it.txt` | TXT | IT | Swiss Federal Constitution — selected articles (Italian) |
| 2 | `ch_constitution_it.pdf` | PDF | IT | Same content as PDF |
| 3 | `ch_constitution_de.pdf` | PDF | DE | Swiss Federal Constitution — same articles (German) |
| 4 | `swiss_obligations_en.txt` | TXT | EN | Swiss Code of Obligations, Art. 319-362 (Employment) |
| 5 | `swiss_obligations_en.pdf` | PDF | EN | Same content as PDF |
| 6 | `gdpr_en.txt` | TXT | EN | GDPR — Articles 1-49 (English) |
| 7 | `gdpr_en.pdf` | PDF | EN | Same content as PDF |
| 8 | `gdpr_it.txt` | TXT | IT | GDPR — Articles 1-20 (Italian) |
| 9 | `gdpr.docx` | DOCX | IT+EN | GDPR combined (English + Italian) |
| 10 | `sentenza_tf.md` | MD | IT | Fictional Federal Tribunal judgment (non-competition clause) |
| 11 | `contratto_lavoro.docx` | DOCX | IT | Fictional employment contract (TechVision SA) |
| 12 | `eu_ai_act_en.txt` | TXT | EN | EU AI Act — Titles I-V (English) |
| 13 | `eu_ai_act_en.pdf` | PDF | EN | Same content as PDF |

### Document Sources

- **Public documents** (Constitution, GDPR, AI Act, Swiss CO): Real legal text from official sources
- **Fictional documents** (sentenza, contratto): Programmatically generated, plausible legal documents in Italian

## Golden Queries

File: `golden_queries.json`

Format:
```json
{
  "query": "What is the definition of 'personal data' under Article 4(1) of the GDPR?",
  "expected_answer": "'Personal data' means any information relating to an identified or identifiable natural person...",
  "doc_ref": "gdpr_en",
  "type": "definition"
}
```

### Query Types

| Type | Description | Example |
|------|-------------|---------|
| `factual` | Asks for a specific data point | "What is the salary in the employment contract?" |
| `definition` | Asks for a concept definition | "What is the definition of 'personal data' in the GDPR?" |
| `cross_document` | Links information from multiple sources | "Compare data protection in Swiss Constitution and GDPR" |

### Query Statistics

- Total queries: ~30
- Per document: 2-4
- Types: factual, definition, cross-document

## Usage

### 1. Generate Documents

```bash
# Generate all documents (idempotent — skips existing files)
python tests/data/synthetic/legal/fetch.py

# Extract text from PDFs/DOCX (optional — for verification)
python tests/data/synthetic/legal/extract.py
```

### 2. Generate Golden Queries

```bash
python tests/data/synthetic/legal/generate.py
```

### 3. Validate Dataset

```bash
# Run all validation tests
uv run pytest tests/data/synthetic/legal/validate.py -v

# Run only document existence tests
uv run pytest tests/data/synthetic/legal/validate.py::TestDocumentExistence -v

# Run only golden query tests
uv run pytest tests/data/synthetic/legal/validate.py::TestGoldenQueries -v
```

### 4. Use in Tests

```python
import pytest

def test_retrieval(legal_dataset_path, golden_queries, sample_documents):
    """Example test using the legal dataset fixtures."""
    # Load a specific document
    doc_text = sample_documents["gdpr_en"]
    assert "personal data" in doc_text.lower()

    # Use a golden query
    for q in golden_queries:
        if q["type"] == "factual":
            # Test your retrieval pipeline
            result = retrieve(q["query"])
            assert q["expected_answer"][:50] in result
            break
```

## Directory Structure

```
tests/data/synthetic/legal/
├── README.md              # This file
├── fetch.py               # Generate/fetch all documents
├── extract.py             # Extract text from PDFs/DOCX
├── generate.py            # Generate golden queries
├── validate.py            # Validation tests
├── conftest.py            # Pytest fixtures
├── golden_queries.json    # Golden queries (generated)
└── documents/             # All documents
    ├── ch_constitution_it.txt
    ├── ch_constitution_it.pdf
    ├── ch_constitution_de.pdf
    ├── swiss_obligations_en.txt
    ├── swiss_obligations_en.pdf
    ├── gdpr_en.txt
    ├── gdpr_en.pdf
    ├── gdpr_it.txt
    ├── gdpr.docx
    ├── sentenza_tf.md
    ├── contratto_lavoro.docx
    ├── eu_ai_act_en.txt
    └── eu_ai_act_en.pdf
```

## Dependencies

The scripts use these Python libraries (install via `pip` or `uv pip`):
- `fpdf2` — PDF generation
- `python-docx` — DOCX generation
- `pymupdf` (optional) — PDF text extraction
- `pymupdf4llm` (optional) — PDF to markdown extraction

## Notes

- All documents are self-contained (no external dependencies at runtime)
- PDF generation requires `fpdf2` with a Unicode font (DejaVu)
- DOCX generation requires `python-docx`
- The dataset is idempotent: re-running `fetch.py` skips existing files
- Golden queries reference documents by stem name (without extension)
