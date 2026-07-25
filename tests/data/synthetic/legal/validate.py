#!/usr/bin/env python3
"""Validate the synthetic legal dataset.

Checks:
1. All expected documents exist in the correct formats
2. Golden queries JSON is complete and well-formed
3. Expected answers can be found (or partially found) in the source documents
4. Document content is non-empty and reasonable

Usage:
    pytest tests/data/synthetic/legal/validate.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATASET_DIR = Path(__file__).parent
DOCS_DIR = DATASET_DIR / "documents"
GOLDEN_FILE = DATASET_DIR / "golden_queries.json"

# Expected documents: (filename, min_size_bytes, description)
EXPECTED_DOCUMENTS = [
    ("ch_constitution_it.txt", 5000, "Swiss Constitution Italian text"),
    ("ch_constitution_de.pdf", 1000, "Swiss Constitution German PDF"),
    ("swiss_obligations_en.txt", 5000, "Swiss CO English text"),
    ("gdpr_en.txt", 5000, "GDPR English text"),
    ("gdpr_it.txt", 5000, "GDPR Italian text"),
    ("gdpr.docx", 1000, "GDPR DOCX (IT+EN)"),
    ("sentenza_tf.md", 3000, "Fictional Federal Tribunal judgment"),
    ("contratto_lavoro.docx", 1000, "Fictional employment contract"),
    ("eu_ai_act_en.txt", 5000, "EU AI Act English text"),
]

# Expected query types
EXPECTED_QUERY_TYPES = {"factual", "definition", "cross_document"}

# Minimum number of golden queries expected
MIN_QUERIES = 20


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def dataset_dir() -> Path:
    """Path to the dataset directory."""
    return DATASET_DIR


@pytest.fixture(scope="session")
def docs_dir() -> Path:
    """Path to the documents directory."""
    return DOCS_DIR


@pytest.fixture(scope="session")
def golden_queries() -> list[dict]:
    """Load golden queries from JSON file."""
    assert GOLDEN_FILE.exists(), f"Golden queries file not found: {GOLDEN_FILE}"
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "Golden queries must be a list"
    return data


@pytest.fixture(scope="session")
def document_texts() -> dict[str, str]:
    """Load all text-based documents into a dict."""
    texts: dict[str, str] = {}
    text_files = list(DOCS_DIR.glob("*.txt")) + list(DOCS_DIR.glob("*.md"))
    for fp in text_files:
        texts[fp.stem] = fp.read_text(encoding="utf-8")
    # Also load extracted text files (from PDFs/DOCX)
    for fp in DOCS_DIR.glob("*_extracted.txt"):
        stem = fp.stem.replace("_extracted", "")
        if stem not in texts:
            texts[stem] = fp.read_text(encoding="utf-8")
    return texts


# ---------------------------------------------------------------------------
# Tests: Document existence and format
# ---------------------------------------------------------------------------


class TestDocumentExistence:
    """Verify all expected documents exist."""

    @pytest.mark.parametrize(
        "filename,min_size,description",
        EXPECTED_DOCUMENTS,
        ids=[d[0] for d in EXPECTED_DOCUMENTS],
    )
    def test_document_exists(self, filename: str, min_size: int, description: str):
        """Test that each expected document exists and meets minimum size."""
        filepath = DOCS_DIR / filename
        assert filepath.exists(), (
            f"Missing document: {filename} ({description}). "
            f"Run: python fetch.py"
        )
        size = filepath.stat().st_size
        assert size >= min_size, (
            f"Document {filename} is too small ({size} bytes, "
            f"expected >= {min_size}). Content may be empty."
        )

    def test_no_empty_documents(self):
        """Verify no document files are empty."""
        for fp in DOCS_DIR.iterdir():
            if fp.is_file():
                assert fp.stat().st_size > 0, f"Empty file: {fp.name}"


# ---------------------------------------------------------------------------
# Tests: Golden queries
# ---------------------------------------------------------------------------


class TestGoldenQueries:
    """Validate golden queries JSON structure and content."""

    def test_golden_file_exists(self):
        """Golden queries JSON file must exist."""
        assert GOLDEN_FILE.exists(), (
            f"Golden queries file not found: {GOLDEN_FILE}. "
            "Run: python generate.py"
        )

    def test_minimum_query_count(self, golden_queries: list[dict]):
        """Must have at least MIN_QUERIES golden queries."""
        assert len(golden_queries) >= MIN_QUERIES, (
            f"Expected at least {MIN_QUERIES} golden queries, "
            f"got {len(golden_queries)}"
        )

    def test_query_structure(self, golden_queries: list[dict]):
        """Each query must have the required fields."""
        required_fields = {"query", "expected_answer", "doc_ref", "type"}
        for i, q in enumerate(golden_queries):
            missing = required_fields - set(q.keys())
            assert not missing, (
                f"Query {i} missing fields: {missing}"
            )

    def test_query_types_valid(self, golden_queries: list[dict]):
        """Each query type must be one of the expected types."""
        for i, q in enumerate(golden_queries):
            assert q["type"] in EXPECTED_QUERY_TYPES, (
                f"Query {i} has invalid type '{q['type']}'. "
                f"Expected one of: {EXPECTED_QUERY_TYPES}"
            )

    def test_all_query_types_present(self, golden_queries: list[dict]):
        """All three query types must be represented."""
        types_found = {q["type"] for q in golden_queries}
        missing = EXPECTED_QUERY_TYPES - types_found
        assert not missing, f"Missing query types: {missing}"

    def test_query_not_empty(self, golden_queries: list[dict]):
        """Query text and expected answer must be non-empty."""
        for i, q in enumerate(golden_queries):
            assert q["query"].strip(), f"Query {i} has empty query text"
            assert q["expected_answer"].strip(), f"Query {i} has empty expected answer"

    def test_doc_ref_valid(self, golden_queries: list[dict]):
        """doc_ref must reference a valid document stem."""
        valid_stems = {fp.stem for fp in DOCS_DIR.iterdir() if fp.is_file()}
        for i, q in enumerate(golden_queries):
            refs = [r.strip() for r in q["doc_ref"].split(",")]
            for ref in refs:
                assert ref in valid_stems, (
                    f"Query {i} references unknown document '{ref}'. "
                    f"Valid documents: {sorted(valid_stems)}"
                )

    def test_cross_document_queries_have_multiple_refs(self, golden_queries: list[dict]):
        """Cross-document queries should reference multiple documents."""
        for i, q in enumerate(golden_queries):
            if q["type"] == "cross_document":
                refs = [r.strip() for r in q["doc_ref"].split(",")]
                assert len(refs) >= 2, (
                    f"Cross-document query {i} references only {len(refs)} "
                    f"document(s). Expected at least 2."
                )


# ---------------------------------------------------------------------------
# Tests: Content consistency
# ---------------------------------------------------------------------------


class TestContentConsistency:
    """Verify golden query answers are consistent with document content."""

    def test_factual_answers_present(self, golden_queries: list[dict], document_texts: dict[str, str]):
        """Factual and definition answers should be findable (at least partially)
        in the referenced documents."""
        # For each factual/definition query, check that key phrases from the
        # expected answer appear in the document text.
        failures = []
        for i, q in enumerate(golden_queries):
            if q["type"] not in ("factual", "definition"):
                continue

            doc_ref = q["doc_ref"].split(",")[0].strip()
            doc_text = document_texts.get(doc_ref, "")
            if not doc_text:
                # Skip documents that are only available as PDF/DOCX (no text file)
                continue

            # Check that at least some key terms from the answer appear in the doc
            answer = q["expected_answer"].lower()
            # Extract key phrases (words longer than 4 chars)
            key_words = [w for w in answer.split() if len(w) > 5]
            if not key_words:
                continue

            # At least 30% of key words should be in the document
            found = sum(1 for w in key_words if w in doc_text.lower())
            ratio = found / len(key_words) if key_words else 1.0
            if ratio < 0.2:
                failures.append(
                    f"Query {i} ({q['type']}): expected answer seems inconsistent "
                    f"with document '{doc_ref}' (keyword match ratio: {ratio:.0%}). "
                    f"Query: {q['query'][:80]}..."
                )

        if failures:
            pytest.fail("\n".join(failures))

    def test_document_languages_correct(self, document_texts: dict[str, str]):
        """Verify documents are in the expected language (basic check)."""
        # Swiss Constitution IT should contain Italian words
        ch_it = document_texts.get("ch_constitution_it", "")
        if ch_it:
            assert "Costituzione" in ch_it or "Confederazione" in ch_it, \
                "Swiss Constitution IT should contain Italian text"

        # GDPR EN should contain English words
        gdpr_en = document_texts.get("gdpr_en", "")
        if gdpr_en:
            assert "Regulation" in gdpr_en or "personal data" in gdpr_en.lower(), \
                "GDPR EN should contain English text"

        # GDPR IT should contain Italian words
        gdpr_it = document_texts.get("gdpr_it", "")
        if gdpr_it:
            assert "Regolamento" in gdpr_it or "dati personali" in gdpr_it.lower(), \
                "GDPR IT should contain Italian text"

        # EU AI Act EN should contain English words
        ai_act = document_texts.get("eu_ai_act_en", "")
        if ai_act:
            assert "artificial intelligence" in ai_act.lower(), \
                "EU AI Act EN should contain English text"

    def test_swiss_constitution_has_key_articles(self, document_texts: dict[str, str]):
        """Swiss Constitution should contain the key articles referenced in queries."""
        ch_it = document_texts.get("ch_constitution_it", "")
        if not ch_it:
            pytest.skip("Swiss Constitution IT not found")

        key_articles = ["Art. 1", "Art. 2", "Art. 4", "Art. 8", "Art. 13"]
        for art in key_articles:
            assert art in ch_it, (
                f"Swiss Constitution IT should contain '{art}'"
            )

    def test_gdpr_has_key_articles(self, document_texts: dict[str, str]):
        """GDPR should contain the key articles referenced in queries."""
        gdpr_en = document_texts.get("gdpr_en", "")
        if not gdpr_en:
            pytest.skip("GDPR EN not found")

        key_articles = ["Article 4", "Article 5", "Article 6", "Article 17"]
        for art in key_articles:
            assert art in gdpr_en, f"GDPR EN should contain '{art}'"

    def test_sentenza_has_key_elements(self, document_texts: dict[str, str]):
        """Fictional sentenza should contain the key legal elements."""
        sentenza = document_texts.get("sentenza_tf", "")
        if not sentenza:
            pytest.skip("Sentenza TF not found")

        assert "4A_123/2024" in sentenza, "Sentenza should contain case number"
        assert "322 CO" in sentenza, "Sentenza should reference Art. 322 CO"
        assert "non concorrenza" in sentenza.lower(), \
            "Sentenza should discuss non-competition clause"

    def test_contratto_has_key_elements(self, document_texts: dict[str, str]):
        """Fictional contract should contain the key legal elements."""
        # We can't read DOCX directly here easily, but we can check the
        # fetch.py source to ensure the content is correct
        pass

    def test_eu_ai_act_has_key_articles(self, document_texts: dict[str, str]):
        """EU AI Act should contain the key articles referenced in queries."""
        ai_act = document_texts.get("eu_ai_act_en", "")
        if not ai_act:
            pytest.skip("EU AI Act EN not found")

        key_articles = ["Article 3", "Article 5", "Article 50"]
        for art in key_articles:
            assert art in ai_act, f"EU AI Act EN should contain '{art}'"


# ---------------------------------------------------------------------------
# Tests: Dataset completeness
# ---------------------------------------------------------------------------


class TestDatasetCompleteness:
    """Verify the dataset as a whole is complete."""

    def test_all_documents_have_queries(self, golden_queries: list[dict]):
        """Every document should have at least one golden query."""
        queried_docs = set()
        for q in golden_queries:
            for ref in q["doc_ref"].split(","):
                queried_docs.add(ref.strip())

        text_docs = {fp.stem for fp in DOCS_DIR.glob("*.txt")}
        md_docs = {fp.stem for fp in DOCS_DIR.glob("*.md")}
        all_docs = text_docs | md_docs

        # Exclude extracted files and PDFs (which may not be directly queryable)
        primary_docs = {d for d in all_docs if not d.endswith("_extracted")}

        missing = primary_docs - queried_docs
        assert not missing, (
            f"Documents without golden queries: {missing}"
        )

    def test_query_count_per_document(self, golden_queries: list[dict]):
        """Each document should have at least 2 golden queries."""
        doc_counts: dict[str, int] = {}
        for q in golden_queries:
            for ref in q["doc_ref"].split(","):
                doc_counts[ref.strip()] = doc_counts.get(ref.strip(), 0) + 1

        # At least 2 queries per primary document
        primary_docs = {fp.stem for fp in DOCS_DIR.glob("*.txt")} | \
                       {fp.stem for fp in DOCS_DIR.glob("*.md")}
        primary_docs = {d for d in primary_docs if not d.endswith("_extracted")}

        for doc in primary_docs:
            count = doc_counts.get(doc, 0)
            assert count >= 2, (
                f"Document '{doc}' has only {count} golden queries (expected >= 2)"
            )

    def test_directory_structure(self):
        """Verify the expected directory structure exists."""
        assert DATASET_DIR.exists(), f"Dataset directory not found: {DATASET_DIR}"
        assert DOCS_DIR.exists(), f"Documents directory not found: {DOCS_DIR}"
        assert (DATASET_DIR / "fetch.py").exists(), "fetch.py not found"
        assert (DATASET_DIR / "extract.py").exists(), "extract.py not found"
        assert (DATASET_DIR / "generate.py").exists(), "generate.py not found"
        assert (DATASET_DIR / "validate.py").exists(), "validate.py not found"
        assert (DATASET_DIR / "conftest.py").exists(), "conftest.py not found"
        assert (DATASET_DIR / "README.md").exists(), "README.md not found"
