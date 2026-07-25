"""Pytest fixtures for the synthetic legal dataset.

Provides:
- legal_dataset_path: Path to the dataset directory
- golden_queries: Loaded golden queries as list of dicts
- sample_documents: Subset of documents for fast testing
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_DOCS_DIR = _HERE / "documents"
_GOLDEN_FILE = _HERE / "golden_queries.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def legal_dataset_path() -> Path:
    """Path to the root of the synthetic legal dataset."""
    return _HERE


@pytest.fixture(scope="session")
def legal_documents_path() -> Path:
    """Path to the documents directory."""
    return _DOCS_DIR


@pytest.fixture(scope="session")
def golden_queries() -> list[dict]:
    """Load and return all golden queries.

    Returns a list of dicts with keys:
    - query: str — the question
    - expected_answer: str — the expected answer
    - doc_ref: str — comma-separated document references
    - type: str — 'factual', 'definition', or 'cross_document'
    """
    assert _GOLDEN_FILE.exists(), (
        f"Golden queries file not found: {_GOLDEN_FILE}. "
        "Run: python tests/data/synthetic/legal/generate.py"
    )
    with open(_GOLDEN_FILE, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list) and len(data) > 0
    return data


@pytest.fixture(scope="session")
def sample_documents() -> dict[str, str]:
    """Load a sample of text documents for fast testing.

    Returns a dict mapping document stem to text content.
    Only loads .txt and .md files (not PDFs/DOCX).
    """
    texts: dict[str, str] = {}
    for fp in sorted(_DOCS_DIR.glob("*.txt")):
        texts[fp.stem] = fp.read_text(encoding="utf-8")
    for fp in sorted(_DOCS_DIR.glob("*.md")):
        texts[fp.stem] = fp.read_text(encoding="utf-8")
    return texts


@pytest.fixture(scope="session")
def factual_queries(golden_queries: list[dict]) -> list[dict]:
    """Return only factual-type golden queries."""
    return [q for q in golden_queries if q["type"] == "factual"]


@pytest.fixture(scope="session")
def definition_queries(golden_queries: list[dict]) -> list[dict]:
    """Return only definition-type golden queries."""
    return [q for q in golden_queries if q["type"] == "definition"]


@pytest.fixture(scope="session")
def cross_document_queries(golden_queries: list[dict]) -> list[dict]:
    """Return only cross-document-type golden queries."""
    return [q for q in golden_queries if q["type"] == "cross_document"]
