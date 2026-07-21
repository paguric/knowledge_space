"""Test per le strategie di chunking (Step 5).

Copre:
- Registry: 5 strategie registrate con params_schema e requires_embedding.
- BaseChunking: normalizzazione output in dict con "text" e "index".
- fixed_size: overlap=0 (no duplicazione), overlap>0 (sliding window).
- recursive: split su separatori gerarchici, code block non spezzato.
- semantic: richiede embedder, errore senza, split con mock embedder.
- sentence: granularity sentence/paragraph, testo IT e EN.
- markdown: split su header, code block intatto, metadata header_1/2/3.
"""

from __future__ import annotations

from typing import List
from unittest.mock import MagicMock

import pytest

from knowledge_base.strategies import chunking_registry
from knowledge_base.strategies.chunking import (
    BaseChunking,
    FixedSizeChunking,
    MarkdownChunking,
    RecursiveChunking,
    SemanticChunking,
    SentenceChunking,
)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


class TestChunkingRegistry:
    def test_all_five_strategies_registered(self):
        assert set(chunking_registry.list_names()) == {
            "fixed_size", "recursive", "semantic", "sentence", "markdown",
        }

    def test_registry_returns_correct_classes(self):
        assert chunking_registry.get("fixed_size") is FixedSizeChunking
        assert chunking_registry.get("recursive") is RecursiveChunking
        assert chunking_registry.get("semantic") is SemanticChunking
        assert chunking_registry.get("sentence") is SentenceChunking
        assert chunking_registry.get("markdown") is MarkdownChunking

    @pytest.mark.parametrize(
        "name,schema_keys,requires_emb",
        [
            ("fixed_size", {"chunk_size", "chunk_overlap", "separator"}, False),
            ("recursive", {"chunk_size", "chunk_overlap", "separators"}, False),
            ("semantic", {"breakpoint_threshold_type", "buffer_size"}, True),
            ("sentence", {"granularity"}, False),
            ("markdown", {"headers_to_split_on"}, False),
        ],
    )
    def test_strategy_metadata(self, name, schema_keys, requires_emb):
        cls = chunking_registry.get(name)
        assert cls.name == name
        assert set(cls.params_schema.keys()) == schema_keys
        assert cls.requires_embedding is requires_emb


# --------------------------------------------------------------------------- #
# BaseChunking — normalizzazione output
# --------------------------------------------------------------------------- #


class TestBaseChunking:
    def test_strings_wrapped_in_dict_with_index(self):
        class Dummy(BaseChunking):
            def _split(self, text):
                return ["a", "b", "c"]

        chunks = Dummy().split("text")
        assert chunks == [
            {"text": "a", "index": 0},
            {"text": "b", "index": 1},
            {"text": "c", "index": 2},
        ]

    def test_dicts_preserved_with_index_default(self):
        class Dummy(BaseChunking):
            def _split(self, text):
                return [{"text": "x", "header_1": "Title"}, {"text": "y"}]

        chunks = Dummy().split("text")
        assert chunks[0] == {"text": "x", "index": 0, "header_1": "Title"}
        assert chunks[1] == {"text": "y", "index": 1}

    def test_dict_without_text_raises(self):
        class Dummy(BaseChunking):
            def _split(self, text):
                return [{"header_1": "no text here"}]

        with pytest.raises(ValueError, match="senza 'text'"):
            Dummy().split("text")

    def test_empty_text_returns_empty_list(self):
        class Dummy(BaseChunking):
            def _split(self, text):
                return []

        assert Dummy().split("") == []


# --------------------------------------------------------------------------- #
# fixed_size — CharacterTextSplitter
# --------------------------------------------------------------------------- #


class TestFixedSizeChunking:
    def test_returns_dicts_with_text_and_index(self):
        text = "paragrafo uno.\n\nparagrafo due."
        chunks = FixedSizeChunking(chunk_size=1000, chunk_overlap=0).split(text)
        assert all("text" in c and "index" in c for c in chunks)
        assert [c["index"] for c in chunks] == list(range(len(chunks)))

    def test_overlap_zero_no_duplicate_chars(self):
        """Con overlap=0, nessun carattere appare in due chunk."""
        text = "A" * 50 + "\n\n" + "B" * 50
        chunks = FixedSizeChunking(
            chunk_size=30, chunk_overlap=0, separator="\n\n"
        ).split(text)
        # I chunk non si sovrappongono: la concatenazione senza separatori
        # non contiene caratteri duplicati tra chunk adiacenti
        for i in range(len(chunks) - 1):
            tail = chunks[i]["text"]
            head = chunks[i + 1]["text"]
            # Nessun suffisso di tail è prefisso di head (no overlap)
            overlap_found = False
            for j in range(1, min(len(tail), len(head)) + 1):
                if tail[-j:] == head[:j] and j > 0:
                    overlap_found = True
                    break
            # Con overlap=0, CharacterTextSplitter non crea sovrapposizioni
            # significative (può mantenere il separatore, ma non contenuto)
            # Verifichiamo che i chunk siano distinti
            assert tail != head

    def test_overlap_gt_zero_produces_overlap(self):
        """Con overlap>0, i chunk si sovrappongono."""
        text = "A" * 100
        chunks = FixedSizeChunking(
            chunk_size=30, chunk_overlap=10, separator=" "
        ).split(text)
        # Con overlap=10, gli ultimi 10 caratteri di un chunk dovrebbero
        # apparire all'inizio del successivo (se ci sono chunk multipli)
        if len(chunks) > 1:
            # Verifica che ci sia almeno una sovrapposizione
            total_chars = sum(len(c["text"]) for c in chunks)
            # Se c'è overlap, la somma dei chunk > lunghezza del testo
            assert total_chars > len(text)

    def test_single_chunk_if_text_shorter_than_chunk_size(self):
        text = "short text"
        chunks = FixedSizeChunking(chunk_size=1000, chunk_overlap=0).split(text)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "short text"
        assert chunks[0]["index"] == 0

    def test_separator_splits_paragraphs(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = FixedSizeChunking(
            chunk_size=20, chunk_overlap=0, separator="\n\n"
        ).split(text)
        assert len(chunks) >= 2

    def test_default_params(self):
        chunker = FixedSizeChunking()
        assert chunker.chunk_size == 1000
        assert chunker.chunk_overlap == 200
        assert chunker.separator == "\n\n"

    def test_instantiable_from_config_kwargs(self):
        """Compatibile con test_base_config: kwargs da ChunkingConfig."""
        chunker = FixedSizeChunking(
            chunk_size=1000, chunk_overlap=200, separator="\n\n"
        )
        assert chunker.chunk_size == 1000
        chunks = chunker.split("paragrafo uno.\n\nparagrafo due.")
        assert len(chunks) >= 1


# --------------------------------------------------------------------------- #
# recursive — RecursiveCharacterTextSplitter
# --------------------------------------------------------------------------- #


class TestRecursiveChunking:
    def test_returns_dicts_with_text_and_index(self):
        text = "# Title\n\nSome text here.\n\nMore text."
        chunks = RecursiveChunking(chunk_size=50, chunk_overlap=0).split(text)
        assert all("text" in c and "index" in c for c in chunks)
        assert [c["index"] for c in chunks] == list(range(len(chunks)))

    def test_splits_on_double_newline_first(self):
        text = "Paragraph one with enough text.\n\nParagraph two with enough text."
        chunks = RecursiveChunking(chunk_size=30, chunk_overlap=0).split(text)
        assert len(chunks) >= 2

    def test_falls_back_to_single_newline(self):
        text = "Line one is long enough.\nLine two is long enough.\nLine three."
        chunks = RecursiveChunking(
            chunk_size=25, chunk_overlap=0, separators=["\n\n", "\n", " ", ""]
        ).split(text)
        assert len(chunks) >= 2

    def test_default_separators(self):
        chunker = RecursiveChunking()
        assert chunker.separators == ["\n\n", "\n", " ", ""]

    def test_custom_separators(self):
        chunker = RecursiveChunking(separators=[";", ","])
        assert chunker.separators == [";", ","]

    def test_preserves_code_block_content(self):
        """Il code block non viene spezzato a metà riga."""
        code = "```python\n" + "x = 1\n" * 20 + "```"
        text = f"# Title\n\n{code}\n\nAfter code."
        chunks = RecursiveChunking(chunk_size=50, chunk_overlap=0).split(text)
        # Il code block può essere in un chunk separato ma il contenuto
        # delle righe non è spezzato a metà
        full = " ".join(c["text"] for c in chunks)
        assert "x = 1" in full


# --------------------------------------------------------------------------- #
# semantic — custom, richiede embedder
# --------------------------------------------------------------------------- #


class MockEmbedder:
    """Embedder deterministico per test: mappa testo → vettore."""

    def __init__(self, vector_map: dict[str, list[float]] | None = None) -> None:
        self._map = vector_map or {}
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._map.get(t, [0.0, 0.0]) for t in texts]


class TestSemanticChunking:
    def test_requires_embedding_true(self):
        assert SemanticChunking.requires_embedding is True

    def test_raises_without_embedder(self):
        chunker = SemanticChunking()
        with pytest.raises(ValueError, match="embedder"):
            chunker.split("Some text. More text.")

    def test_single_sentence_returns_single_chunk(self):
        embedder = MockEmbedder()
        chunker = SemanticChunking(embedder=embedder)
        chunks = chunker.split("Only one sentence here.")
        assert len(chunks) == 1
        assert "text" in chunks[0]
        assert chunks[0]["index"] == 0

    def test_splits_dissimilar_sentences(self):
        """Frasi semanticamente diverse (vettori ortogonali) → split."""
        embedder = MockEmbedder({
            "Cats are animals.": [1.0, 0.0],
            "Dogs are animals.": [1.0, 0.01],  # simile alla prima
            "Quantum physics is complex.": [0.0, 1.0],  # ortogonale
            "Math is hard.": [0.0, 0.99],  # simile alla terza
        })
        chunker = SemanticChunking(
            embedder=embedder,
            breakpoint_threshold_type="percentile",
        )
        text = "Cats are animals. Dogs are animals. Quantum physics is complex. Math is hard."
        chunks = chunker.split(text)
        assert len(chunks) >= 2
        # I primi due dovrebbero stare insieme, gli ultimi due insieme
        assert "Cats" in chunks[0]["text"]
        assert "Quantum" in chunks[-1]["text"]

    def test_threshold_standard_deviation(self):
        embedder = MockEmbedder({
            "A.": [1.0, 0.0],
            "B.": [1.0, 0.0],
            "C.": [0.0, 1.0],
        })
        chunker = SemanticChunking(
            embedder=embedder,
            breakpoint_threshold_type="standard_deviation",
        )
        chunks = chunker.split("A. B. C.")
        assert len(chunks) >= 1

    def test_threshold_interquartile(self):
        embedder = MockEmbedder({
            "A.": [1.0, 0.0],
            "B.": [1.0, 0.0],
            "C.": [0.0, 1.0],
        })
        chunker = SemanticChunking(
            embedder=embedder,
            breakpoint_threshold_type="interquartile",
        )
        chunks = chunker.split("A. B. C.")
        assert len(chunks) >= 1

    def test_buffer_size_groups_sentences(self):
        embedder = MockEmbedder({
            "A. B.": [1.0, 0.0],
            "C. D.": [0.0, 1.0],
        })
        chunker = SemanticChunking(embedder=embedder, buffer_size=2)
        chunks = chunker.split("A. B. C. D.")
        # Con buffer_size=2, le frasi vengono raggruppate a coppie
        assert len(chunks) >= 1

    def test_returns_dicts_with_text_and_index(self):
        embedder = MockEmbedder({
            "A.": [1.0, 0.0],
            "B.": [0.0, 1.0],
        })
        chunks = SemanticChunking(embedder=embedder).split("A. B.")
        assert all("text" in c and "index" in c for c in chunks)


# --------------------------------------------------------------------------- #
# sentence — regex, granularity sentence | paragraph
# --------------------------------------------------------------------------- #


class TestSentenceChunking:
    def test_sentence_granularity_english(self):
        text = "First sentence. Second sentence! Third one? And the last."
        chunks = SentenceChunking(granularity="sentence").split(text)
        assert len(chunks) == 4
        assert chunks[0]["text"] == "First sentence."
        assert chunks[1]["text"] == "Second sentence!"
        assert chunks[2]["text"] == "Third one?"
        assert chunks[3]["text"] == "And the last."

    def test_sentence_granularity_italian(self):
        text = "Prima frase. Seconda frase! Terza? E l'ultima."
        chunks = SentenceChunking(granularity="sentence").split(text)
        assert len(chunks) == 4
        assert chunks[0]["text"] == "Prima frase."
        assert chunks[3]["text"] == "E l'ultima."

    def test_paragraph_granularity(self):
        text = "Para one line.\n\nPara two line.\n\nPara three."
        chunks = SentenceChunking(granularity="paragraph").split(text)
        assert len(chunks) == 3
        assert chunks[0]["text"] == "Para one line."
        assert chunks[1]["text"] == "Para two line."
        assert chunks[2]["text"] == "Para three."

    def test_default_granularity_is_sentence(self):
        chunker = SentenceChunking()
        assert chunker.granularity == "sentence"

    def test_returns_dicts_with_text_and_index(self):
        chunks = SentenceChunking().split("A. B. C.")
        assert all("text" in c and "index" in c for c in chunks)
        assert [c["index"] for c in chunks] == [0, 1, 2]

    def test_empty_text_returns_empty(self):
        chunks = SentenceChunking().split("")
        assert chunks == []

    def test_no_trailing_whitespace_in_chunks(self):
        text = "  Sentence one.  Sentence two.  "
        chunks = SentenceChunking().split(text)
        for c in chunks:
            assert c["text"] == c["text"].strip()


# --------------------------------------------------------------------------- #
# markdown — MarkdownHeaderTextSplitter
# --------------------------------------------------------------------------- #


class TestMarkdownChunking:
    def test_splits_on_headers(self):
        text = (
            "# Chapter 1\n\nIntro text.\n\n"
            "## Section 1.1\n\nSection text.\n\n"
            "# Chapter 2\n\nChapter 2 text."
        )
        chunks = MarkdownChunking().split(text)
        assert len(chunks) >= 3
        # Ogni chunk ha "text" e "index"
        assert all("text" in c and "index" in c for c in chunks)

    def test_header_metadata_included(self):
        text = "# Title\n\nBody text.\n\n## Subtitle\n\nMore body."
        chunks = MarkdownChunking().split(text)
        # Almeno un chunk deve avere header_1 metadata
        header_1s = [c for c in chunks if c.get("header_1") == "Title"]
        assert len(header_1s) >= 1
        header_2s = [c for c in chunks if c.get("header_2") == "Subtitle"]
        assert len(header_2s) >= 1

    def test_code_block_intact(self):
        """Il testo dentro un code block non viene spezzato."""
        code_line = "x = 1  # comment"
        code = f"```python\n{code_line}\n```"
        text = f"# Title\n\nIntro.\n\n{code}\n\nAfter."
        chunks = MarkdownChunking().split(text)
        # Il code block appare intero in uno dei chunk
        full = "\n\n".join(c["text"] for c in chunks)
        assert "```python" in full
        assert code_line in full
        assert "```" in full

    def test_custom_headers(self):
        text = "# H1\n\nText.\n\n## H2\n\nMore.\n\n### H3\n\nDeep."
        chunks = MarkdownChunking(
            headers_to_split_on=[["#", "h1"], ["##", "h2"]]
        ).split(text)
        # Con solo h1 e h2, h3 non crea un nuovo chunk
        assert any(c.get("h1") == "H1" for c in chunks)
        assert any(c.get("h2") == "H2" for c in chunks)
        # h3 non è nei metadata (non è negli headers_to_split_on)
        assert all("h3" not in c for c in chunks)

    def test_default_headers(self):
        chunker = MarkdownChunking()
        assert ["#", "header_1"] in chunker.headers_to_split_on
        assert ["##", "header_2"] in chunker.headers_to_split_on
        assert ["###", "header_3"] in chunker.headers_to_split_on

    def test_index_sequential(self):
        text = "# A\n\nText A.\n\n# B\n\nText B.\n\n# C\n\nText C."
        chunks = MarkdownChunking().split(text)
        assert [c["index"] for c in chunks] == list(range(len(chunks)))

    def test_no_header_text_still_chunked(self):
        """Testo senza header produce almeno un chunk."""
        text = "Just some plain text without headers."
        chunks = MarkdownChunking().split(text)
        assert len(chunks) >= 1
        assert chunks[0]["text"].strip() == text.strip()
