"""KSChunkLoader: carica chunk da disco + embedding da Chroma.

Sostituisce data loader + text splitter + chunk embedder della pipeline
neo4j-graphrag. Legge i chunk già prodotti dalla Fase 1A (su disco) e
recupera gli embedding da Chroma.

Produce ``TextChunk`` ordinati, pronti per l'estrazione entità e la
scrittura su Neo4j.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Modelli
# --------------------------------------------------------------------------- #


class TextChunk(BaseModel):
    """Singolo chunk di testo con metadati per il grafo."""

    chunk_id: str
    text: str
    embedding: Optional[List[float]] = None
    base_name: str = ""
    file_name: str = ""
    file_id: str = ""
    chunk_index: int = 0
    content_hash: Optional[str] = None


class TextChunks(BaseModel):
    """Collezione ordinata di chunk con info sul documento."""

    chunks: List[TextChunk] = Field(default_factory=list)
    document_info: Dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #


class KSChunkLoader:
    """Carica chunk da disco e embedding da Chroma.

    Legge i chunk da ``<base>/.knowledge-space/chunks/<file_id>/`` e
    recupera gli embedding dalla collection Chroma della base.

    Args:
        chunks_dir: path base dei chunk (``<base>/.knowledge-space/chunks``).
        chroma_collection: collection Chroma (opzionale, per embedding).
    """

    def __init__(
        self,
        chunks_dir: Path,
        chroma_collection: Any = None,
    ) -> None:
        self._chunks_dir = Path(chunks_dir)
        self._collection = chroma_collection

    def load_file(
        self,
        file_id: str,
        base_name: str = "",
        file_name: str = "",
    ) -> TextChunks:
        """Carica tutti i chunk di un file.

        Args:
            file_id: UUID del file.
            base_name: nome della base.
            file_name: nome del file sorgente.

        Returns:
            ``TextChunks`` con i chunk ordinati per indice.
        """
        chunks_dir = self._chunks_dir / file_id
        if not chunks_dir.exists():
            logger.warning("Cartella chunk non trovata: %s", chunks_dir)
            return TextChunks(
                document_info={"file_id": file_id, "base_name": base_name, "file_name": file_name}
            )

        # Trova tutti i chunk ordinati per indice
        chunk_files = sorted(
            chunks_dir.glob(f"{file_id}_chunk_*.md"),
            key=lambda p: self._extract_index(p, file_id),
        )

        chunks = []
        for chunk_path in chunk_files:
            index = self._extract_index(chunk_path, file_id)
            text = chunk_path.read_text(encoding="utf-8")
            chunk_id = f"{base_name}::{file_id}::{index}"

            # Recupera embedding da Chroma se disponibile
            embedding = self._get_embedding(base_name, file_id, index)

            chunks.append(TextChunk(
                chunk_id=chunk_id,
                text=text,
                embedding=embedding,
                base_name=base_name,
                file_name=file_name,
                file_id=file_id,
                chunk_index=index,
            ))

        return TextChunks(
            chunks=chunks,
            document_info={
                "file_id": file_id,
                "base_name": base_name,
                "file_name": file_name,
                "path": str(chunks_dir),
            },
        )

    def load_base(self, base_name: str, files: Dict[str, Any]) -> TextChunks:
        """Carica tutti i chunk di una base.

        Args:
            base_name: nome della base.
            files: dict dei FileEntry (da KnowledgeBase.files).

        Returns:
            ``TextChunks`` con tutti i chunk di tutti i file attivi.
        """
        all_chunks = []
        for file_name, entry in files.items():
            if not getattr(entry, "active", True):
                continue
            file_id = getattr(entry, "file_id", None)
            if not file_id:
                continue
            text_chunks = self.load_file(file_id, base_name, file_name)
            all_chunks.extend(text_chunks.chunks)

        return TextChunks(
            chunks=all_chunks,
            document_info={"base_name": base_name, "n_files": len(files)},
        )

    def upsert_chunks(
        self,
        base_name: str,
        file_id: str,
        changed_chunks: List[Dict[str, Any]],
    ) -> TextChunks:
        """Aggiorna chunk specifici (propagazione incrementale).

        Usato per il trigger 1 (content change): solo i chunk cambiati
        vengono ricaricati.

        Args:
            base_name: nome della base.
            file_id: UUID del file.
            changed_chunks: lista di dict con ``index``, ``text``, ``content_hash``.

        Returns:
            ``TextChunks`` con i chunk aggiornati.
        """
        chunks = []
        for chunk_data in changed_chunks:
            index = chunk_data.get("index", 0)
            text = chunk_data.get("text", "")
            content_hash = chunk_data.get("content_hash")
            chunk_id = f"{base_name}::{file_id}::{index}"

            embedding = self._get_embedding(base_name, file_id, index)

            chunks.append(TextChunk(
                chunk_id=chunk_id,
                text=text,
                embedding=embedding,
                base_name=base_name,
                file_id=file_id,
                chunk_index=index,
                content_hash=content_hash,
            ))

        return TextChunks(chunks=chunks)

    # ..................................................................... #
    # Helpers
    # ..................................................................... #

    @staticmethod
    def _extract_index(path: Path, file_id: str) -> int:
        """Estrae l'indice del chunk dal nome del file."""
        name = path.stem  # es. "abc123_chunk_3"
        parts = name.split("_chunk_")
        if len(parts) == 2:
            try:
                return int(parts[1])
            except ValueError:
                pass
        return 0

    def _get_embedding(
        self,
        base_name: str,
        file_id: str,
        chunk_index: int,
    ) -> Optional[List[float]]:
        """Recupera l'embedding da Chroma per un chunk specifico."""
        if self._collection is None:
            return None

        chunk_id = f"{base_name}::{file_id}::{chunk_index}"
        try:
            result = self._collection.get(
                ids=[chunk_id],
                include=["embeddings"],
            )
            if result and result.get("embeddings") is not None:
                embeddings = result["embeddings"]
                if len(embeddings) > 0:
                    return list(embeddings[0])
        except Exception as exc:
            logger.debug("Embedding non trovato per %s: %s", chunk_id, exc)

        return None
