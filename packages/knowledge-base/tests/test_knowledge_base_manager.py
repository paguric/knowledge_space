"""Test per ``KnowledgeBaseManager`` (Step 7).

Copia dalla spec ``docs/91a-roadmap-fase1-ingestione.md`` § Step 7:

- ingestion (pipeline add_file);
- rimozione file (chroma + disco);
- sync mtime (file modificato → marcate per re-index; file scomparso → cleanup);
- diff incrementale via ``content_hash`` (solo chunk cambiati re-embeddati);
- move/rename senza recompute (chunk_id immutato, metadati Chroma aggiornati);
- errore ``max_context_tokens``;
- idempotenza (add_file × 2 con stesso contenuto → no-op);
- blocco cambio config (trigger 3/4/5): errore esplicito se collection non
  vuota e model/method/library differiscono.

Tutte le strategie (ingestion, chunking, embedding) sono iniettate come
**stub** nel manager: niente download di modelli né parsing pesante.
Chroma usa una cartella temporanea (``tmp_path``) con ``PersistentClient``
reale (verifica end-to-end dell'incapsulamento).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from knowledge_base.base_config import BaseConfig, ConfigChangeBlockedError
from knowledge_base.knowledge_base_manager import (
    BaseNotFoundError,
    ChunkPersistError,
    KnowledgeBaseManager,
)
from knowledge_base.models import (
    ChunkRef,
    FileEntry,
    KnowledgeBase,
    Workspace,
)
from knowledge_base.strategies import EmbeddingMetadata, EmbeddingStrategy
from knowledge_base.strategies.embedding import ChunkTooLongError


# --------------------------------------------------------------------------- #
# Stub: ingestion / chunking / embedding
# --------------------------------------------------------------------------- #


class StubIngestion:
    """Ingestion fitta: restituisce il contenuto UTF-8 del file sorgente."""

    name = "stub"
    library = "stub"
    supported_extensions: List[str] = [".md", ".txt"]

    def __init__(self, **params: Any) -> None:
        self.params = params

    def convert(self, source_path: Path) -> str:
        return Path(source_path).read_text(encoding="utf-8")


class StubChunker:
    """Chunker fitto: split su ``\\n\\n`` (paragraph).	es pagine."""

    name = "stub"
    params_schema: Dict[str, type] = {}
    requires_embedding = False

    def __init__(self, **params: Any) -> None:
        self.params = params

    def split(self, text: str) -> List[Dict[str, Any]]:
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        return [{"text": p, "index": i} for i, p in enumerate(parts)]


class StubChunkerLarge:
    """Chunker fitto: produce un chunk enorme per testare max_context_tokens."""

    name = "stub_large"
    requires_embedding = False

    def __init__(self, **params: Any) -> None:
        self.params = params

    def split(self, text: str) -> List[Dict[str, Any]]:
        # 2000 caratteri → stimati 500 token > 384 del modello finto.
        return [{"text": "a" * 2000, "index": 0}]


class StubEmbedder:
    """Embedder fitto: vettori deterministici, dim fissa, max_ctx 384."""

    name = "stub-embedder"

    def __init__(self) -> None:
        self.metadata = EmbeddingMetadata(
            model_name="stub-embedder",
            languages=["en"],
            dim=8,
            max_context_tokens=384,
            license="test",
            requires_api=False,
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        # vettore deterministico: somma degli codice con lunghezza mod dim
        return [
            [float((len(t) + i) % 10) / 10.0 for i in range(self.metadata.dim)]
            for t in texts
        ]


# Factory iniettate nel manager


def _stub_ingestion_factory(config: BaseConfig) -> StubIngestion:
    return StubIngestion(**(config.ingestion.params or {}))


def _stub_chunking_factory(config: BaseConfig, embedder: Any) -> StubChunker:
    return StubChunker()


def _stub_chunking_factory_large(config: BaseConfig, embedder: Any) -> StubChunkerLarge:
    return StubChunkerLarge()


def _stub_embedder_factory(_model_name: str) -> StubEmbedder:
    return StubEmbedder()


# --------------------------------------------------------------------------- #
# Fixture
# --------------------------------------------------------------------------- #


def _make_config(embedding_model: str = "stub-embedder") -> BaseConfig:
    return BaseConfig()


def _make_config_loader(model: str = "stub-embedder", method: str = "stub", library: str = "stub"):
    """Loader finto: restituisce sempre la stessa BaseConfig."""
    def _loader(_base_name: str) -> BaseConfig:
        cfg = BaseConfig()
        cfg.embedding.model = model
        cfg.chunking.method = method
        cfg.ingestion.library = library
        return cfg
    return _loader


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    base_path = ws_path / "kb1"
    base_path.mkdir()
    return Workspace(path=ws_path)


@pytest.fixture
def manager(workspace: Workspace, tmp_path: Path) -> KnowledgeBaseManager:
    # Chroma in tmp_path per isolamento
    chroma_path = tmp_path / "chroma"
    config_loader = _make_config_loader()

    def _config_path_for(ws_path: Path) -> Path:
        return Path(ws_path) / ".knowledge-space" / "config.json"

    # Inizializza il config.json di default se non esiste
    cfg_path = _config_path_for(workspace.path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    return KnowledgeBaseManager(
        workspace=workspace,
        config_loader=config_loader,
        config_path_for=_config_path_for,
        chroma_path=chroma_path,
        ingestion_factory=_stub_ingestion_factory,
        chunking_factory=_stub_chunking_factory,
        embedder_factory=_stub_embedder_factory,
    )


def _write_source(base_path: Path, name: str, content: str) -> Path:
    p = base_path / name
    p.write_text(content, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# Setup base + pipeline add_file
# --------------------------------------------------------------------------- #


class TestAddBase:
    def test_add_registers_base(self, manager: KnowledgeBaseManager, workspace: Workspace):
        kb = manager.add(workspace.path / "kb1")
        assert isinstance(kb, KnowledgeBase)
        assert "kb1" in workspace.bases

    def test_add_missing_dir_raises(self, manager: KnowledgeBaseManager, workspace: Workspace):
        with pytest.raises(ValueError, match="non esiste"):
            manager.add(workspace.path / "nope")

    def test_add_duplicate_raises(self, manager: KnowledgeBaseManager, workspace: Workspace):
        manager.add(workspace.path / "kb1")
        with pytest.raises(ValueError, match="già registrata"):
            manager.add(workspace.path / "kb1")

    def test_remove_drops_collection_and_state(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        assert manager.remove("kb1") is True
        assert "kb1" not in workspace.bases
        # idempotent
        assert manager.remove("kb1") is False


class TestAddFilePipeline:
    def test_add_file_creates_file_entry_with_file_id(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "paragrafo 1\n\nparagrafo 2")
        entry = manager.add_file("kb1", src)

        assert entry.file_id is not None
        assert len(entry.file_id) == 32  # uuid4 hex
        assert entry.name == "doc.md"
        assert entry.content_hash is not None
        assert len(entry.chunks) == 2
        # ChunkRef.content_hash popolato
        assert all(c.content_hash is not None for c in entry.chunks)
        # Modelli registrati (per blocco config futuro)
        kb = workspace.bases["kb1"]
        assert kb.embedding_model == "stub-embedder"
        assert kb.chunking_method == "stub"
        assert kb.ingestion_library == "stub"

    def test_add_file_persists_chunks_to_disk(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2\n\np3")
        entry = manager.add_file("kb1", src)

        chunks_dir = (workspace.path / "kb1" / ".knowledge-space" / "chunks" / entry.file_id)
        assert chunks_dir.is_dir()
        chunk_files = sorted(chunks_dir.iterdir())
        assert len(chunk_files) == 3
        # Contenuto del chunk 0 = "p1"
        assert chunk_files[0].read_text(encoding="utf-8") == "p1"

    def test_add_file_upserts_chroma_records(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        entry = manager.add_file("kb1", src)

        col = manager._chroma_client().get_collection(name="ks_kb1")
        assert col.count() == 2
        # Verifica metadati
        rec = col.get(ids=[f"kb1::{entry.file_id}::0"])
        assert rec["metadatas"][0]["file_name"] == "doc.md"
        assert rec["metadatas"][0]["base_name"] == "kb1"
        assert rec["metadatas"][0]["chunk_index"] == 0
        assert rec["metadatas"][0]["content_hash"] is not None
        # Documento corrisponde al testo del chunk
        assert rec["documents"][0] == "p1"

    def test_add_file_unknown_base_raises(self, manager: KnowledgeBaseManager):
        with pytest.raises(BaseNotFoundError):
            manager.add_file("nope", Path("/dev/null"))

    def test_add_file_missing_source_raises(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        with pytest.raises(FileNotFoundError):
            manager.add_file("kb1", workspace.path / "kb1" / "ghost.md")


# --------------------------------------------------------------------------- #
# Idempotenza
# --------------------------------------------------------------------------- #


class TestIdempotency:
    def test_add_file_twice_same_content_is_noop(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        entry1 = manager.add_file("kb1", src)
        entry2 = manager.add_file("kb1", src)
        assert entry1 is entry2  # stesso FileEntry
        assert entry1.file_id == entry2.file_id
        # Chroma invariato
        col = manager._chroma_client().get_collection(name="ks_kb1")
        assert col.count() == 2

    def test_add_file_same_file_id_preserved_across_calls(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        entry1 = manager.add_file("kb1", src)
        file_id_first = entry1.file_id
        # Modifica il file sorgente → entrata diversa ma stesso file_id
        _write_source(workspace.path / "kb1", "doc.md", "p1 UPDATED\n\np2\n\np3")
        entry2 = manager.add_file("kb1", src)
        assert entry2.file_id == file_id_first


# --------------------------------------------------------------------------- #
# Diff incrementale (content change)
# --------------------------------------------------------------------------- #


class TestIncrementalDiff:
    def test_content_change_reembeds_only_changed_chunks(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2\n\np3")
        entry1 = manager.add_file("kb1", src)

        old_chunk0_hash = entry1.chunks[0].content_hash
        old_chunk1_hash = entry1.chunks[1].content_hash
        old_chunk2_hash = entry1.chunks[2].content_hash

        # Modifica solo il primo paragrafo (p1 → p1 NEW)
        _write_source(workspace.path / "kb1", "doc.md", "p1 NEW\n\np2\n\np3")
        entry2 = manager.add_file("kb1", src)

        # chunk 0 hash cambia; chunk 1, 2 invariati
        assert entry2.chunks[0].content_hash != old_chunk0_hash
        assert entry2.chunks[1].content_hash == old_chunk1_hash
        assert entry2.chunks[2].content_hash == old_chunk2_hash

    def test_content_truncation_removes_extra_chunks(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2\n\np3")
        entry1 = manager.add_file("kb1", src)
        file_id = entry1.file_id
        # Chroma ha 3 chunk
        col = manager._chroma_client().get_collection(name="ks_kb1")
        assert col.count() == 3

        # Tronca a 1 paragrafo
        _write_source(workspace.path / "kb1", "doc.md", "p1")
        entry2 = manager.add_file("kb1", src)
        assert len(entry2.chunks) == 1
        # Chroma ha 1 chunk
        assert col.count() == 1
        # File .md per chunk 1 e 2 sono cancellati
        chunks_dir = (workspace.path / "kb1" / ".knowledge-space" / "chunks" / file_id)
        chunk_files = sorted(chunks_dir.iterdir())
        assert len(chunk_files) == 1

    def test_content_insert_in_middle_approccio_b(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        """Approccio B: insert in mezzo → shift accettato, re-embed da
        quel punto in poi."""
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2\n\np3")
        entry1 = manager.add_file("kb1", src)
        old_c0 = entry1.chunks[0].content_hash
        old_c1 = entry1.chunks[1].content_hash

        # Inserisce in mezzo: chunk 1 ora è "p1.5", chunk 2 era "p2", chunk 3 era "p3"
        _write_source(workspace.path / "kb1", "doc.md", "p1\n\np1.5\n\np2\n\np3")
        entry2 = manager.add_file("kb1", src)

        # c0 invariato (p1), c1 shiftato (vecchio p2 -> nuovo p1.5, hash diverso)
        assert entry2.chunks[0].content_hash == old_c0
        assert entry2.chunks[1].content_hash != old_c1
        assert len(entry2.chunks) == 4
        # Chroma aggiornato
        col = manager._chroma_client().get_collection(name="ks_kb1")
        assert col.count() == 4


# --------------------------------------------------------------------------- #
# Rimozione file
# --------------------------------------------------------------------------- #


class TestRemoveFile:
    def test_remove_file_cleans_chroma_and_disk(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        entry = manager.add_file("kb1", src)
        file_id = entry.file_id
        chunks_dir = (workspace.path / "kb1" / ".knowledge-space" / "chunks" / file_id)
        assert chunks_dir.exists()

        assert manager.remove_file("kb1", "doc.md") is True
        # Stato pulito
        assert "doc.md" not in workspace.bases["kb1"].files
        # Chroma vuoto
        col = manager._chroma_client().get_collection(name="ks_kb1")
        assert col.count() == 0
        # Cartella chunk rimossa
        assert not chunks_dir.exists()

    def test_remove_file_missing_returns_false(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        assert manager.remove_file("kb1", "ghost.md") is False


# --------------------------------------------------------------------------- #
# Sync mtime
# --------------------------------------------------------------------------- #


class TestSync:
    def test_sync_removes_missing_files(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        entry = manager.add_file("kb1", src)
        file_id = entry.file_id
        chunks_dir = (workspace.path / "kb1" / ".knowledge-space" / "chunks" / file_id)
        # Elimina il file sorgente
        src.unlink()

        manager.sync("kb1")
        # File scomparso → pulito da stato + Chroma
        assert "doc.md" not in workspace.bases["kb1"].files
        col = manager._chroma_client().get_collection(name="ks_kb1")
        assert col.count() == 0
        assert not chunks_dir.exists()

    def test_sync_keeps_present_files(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        manager.add_file("kb1", src)
        manager.sync("kb1")
        # Ancora presente
        assert "doc.md" in workspace.bases["kb1"].files
        col = manager._chroma_client().get_collection(name="ks_kb1")
        assert col.count() == 2


# --------------------------------------------------------------------------- #
# Move / rename senza recompute
# --------------------------------------------------------------------------- #


class TestRenameFile:
    def test_rename_updates_metadata_without_recompute(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "old.md", "p1\n\np2")
        entry = manager.add_file("kb1", src)
        file_id = entry.file_id
        old_chunk0_hash = entry.chunks[0].content_hash

        # Ora simula il rename effettivo su disco
        new_src = workspace.path / "kb1" / "new.md"
        src.rename(new_src)
        manager.rename_file("kb1", "old.md", new_src)

        # Stato: il file si chiama new.md
        assert "old.md" not in workspace.bases["kb1"].files
        assert "new.md" in workspace.bases["kb1"].files
        # file_id invariato (chunk_id stabile)
        assert workspace.bases["kb1"].files["new.md"].file_id == file_id
        # content_hash chunk invariato (no recompute)
        assert workspace.bases["kb1"].files["new.md"].chunks[0].content_hash == old_chunk0_hash
        # Chroma: metadati file_name aggiornati
        col = manager._chroma_client().get_collection(name="ks_kb1")
        rec0 = col.get(ids=[f"kb1::{file_id}::0"])
        assert rec0["metadatas"][0]["file_name"] == "new.md"
        assert rec0["metadatas"][0]["file_id"] == file_id
        # chunk_id invariato
        assert rec0["ids"][0] == f"kb1::{file_id}::0"

    def test_rename_unknown_file_raises(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        with pytest.raises(FileNotFoundError):
            manager.rename_file("kb1", "ghost.md", workspace.path / "kb1" / "x.md")

    def test_rename_to_existing_name_raises(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        manager.add(workspace.path / "kb1")
        src1 = _write_source(workspace.path / "kb1", "a.md", "p1\n\np2")
        _write_source(workspace.path / "kb1", "b.md", "p3\n\np4")
        manager.add_file("kb1", src1)
        manager.add_file("kb1", workspace.path / "kb1" / "b.md")
        with pytest.raises(Exception, match="già indicizzato"):
            manager.rename_file("kb1", "a.md", workspace.path / "kb1" / "b.md")


# --------------------------------------------------------------------------- #
# Errore max_context_tokens
# --------------------------------------------------------------------------- #


class TestChunkTooLongError:
    def test_chunk_exceeding_max_context_raises(
        self, workspace: Workspace, tmp_path: Path
    ):
        chroma_path = tmp_path / "chroma"
        def _config_path_for(ws_path: Path) -> Path:
            return Path(ws_path) / ".knowledge-space" / "config.json"
        cfg_path = _config_path_for(workspace.path)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)

        m = KnowledgeBaseManager(
            workspace=workspace,
            config_loader=_make_config_loader(),
            config_path_for=_config_path_for,
            chroma_path=chroma_path,
            ingestion_factory=_stub_ingestion_factory,
            chunking_factory=_stub_chunking_factory_large,  # chunk enorme
            embedder_factory=_stub_embedder_factory,
        )
        m.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "big.md", "testo qualsiasi")
        with pytest.raises(ChunkPersistError, match="supera il limite"):
            m.add_file("kb1", src)


# --------------------------------------------------------------------------- #
# Blocco cambio config (trigger 3/4/5)
# --------------------------------------------------------------------------- #


class TestConfigChangeBlocked:
    def _setup_with_chunks(self, manager: KnowledgeBaseManager, workspace: Workspace):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        manager.add_file("kb1", src)
        # Verifica che la collection è non vuota
        assert manager._collection_non_empty("kb1") is True

    def test_embedding_model_change_blocked(
        self, workspace: Workspace, tmp_path: Path
    ):
        """Cambiare il modello di embedding con collection non vuota → errore."""
        chroma_path = tmp_path / "chroma"
        def _config_path_for(ws_path: Path) -> Path:
            return Path(ws_path) / ".knowledge-space" / "config.json"
        cfg_path = _config_path_for(workspace.path)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        # Loader restituisce prima model A, poi model B
        calls = {"n": 0}
        def _loader(_b):
            calls["n"] += 1
            cfg = BaseConfig()
            cfg.embedding.model = "model-A" if calls["n"] == 1 else "model-B"
            cfg.chunking.method = "stub"
            cfg.ingestion.library = "stub"
            return cfg
        m = KnowledgeBaseManager(
            workspace=workspace,
            config_loader=_loader,
            config_path_for=_config_path_for,
            chroma_path=chroma_path,
            ingestion_factory=_stub_ingestion_factory,
            chunking_factory=_stub_chunking_factory,
            embedder_factory=_stub_embedder_factory,
        )
        m.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        m.add_file("kb1", src)  # registra model-A

        # Ora loader restituisce model-B → blocco
        with pytest.raises(ConfigChangeBlockedError, match="model-change"):
            m.add_file("kb1", src)

    def test_chunking_method_change_blocked(
        self, workspace: Workspace, tmp_path: Path
    ):
        chroma_path = tmp_path / "chroma"
        def _config_path_for(ws_path: Path) -> Path:
            return Path(ws_path) / ".knowledge-space" / "config.json"
        cfg_path = _config_path_for(workspace.path)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        calls = {"n": 0}
        def _loader(_b):
            calls["n"] += 1
            cfg = BaseConfig()
            cfg.embedding.model = "stub-embedder"
            cfg.chunking.method = "stub-A" if calls["n"] == 1 else "stub-B"
            cfg.ingestion.library = "stub"
            return cfg
        m = KnowledgeBaseManager(
            workspace=workspace,
            config_loader=_loader,
            config_path_for=_config_path_for,
            chroma_path=chroma_path,
            ingestion_factory=_stub_ingestion_factory,
            chunking_factory=_stub_chunking_factory,
            embedder_factory=_stub_embedder_factory,
        )
        m.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        m.add_file("kb1", src)

        with pytest.raises(ConfigChangeBlockedError, match="chunking-change"):
            m.add_file("kb1", src)

    def test_change_allowed_when_collection_empty(
        self, manager: KnowledgeBaseManager, workspace: Workspace
    ):
        """Base registrata ma nessun file → collection vuota → cambio Ok."""
        manager.add(workspace.path / "kb1")
        # base vuota: collection vuota → check_config_change non solleva
        # anche se i valori registrati differiscono (tutti None).
        manager.check_config_change("kb1")  # no raise


# --------------------------------------------------------------------------- #
# Migrazione retroattiva state.json
# --------------------------------------------------------------------------- #


class TestMigrateState:
    def test_migrate_assigns_file_id_and_hashes(self, manager: KnowledgeBaseManager, workspace: Workspace):
        manager.add(workspace.path / "kb1")
        # Crea un FileEntry legacy (senza file_id, senza content_hash)
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        legacy_entry = FileEntry(
            mtime=src.stat().st_mtime,
            added="2026-01-01T00:00:00+00:00",
            chunks=[ChunkRef(index=0), ChunkRef(index=1)],
        )
        # Simula availability dei chunk su disco
        file_id_placeholder = "legacy"
        chunks_dir = (workspace.path / "kb1" / ".knowledge-space" / "chunks" / file_id_placeholder)
        chunks_dir.mkdir(parents=True, exist_ok=True)
        (chunks_dir / "legacy_chunk_0.md").write_text("p1", encoding="utf-8")
        (chunks_dir / "legacy_chunk_1.md").write_text("p2", encoding="utf-8")
        legacy_entry.file_id = file_id_placeholder
        workspace.bases["kb1"].files["doc.md"] = legacy_entry

        manager.migrate_state()

        # Dopo: content_hash calcolato per il file e per i chunk
        entry = workspace.bases["kb1"].files["doc.md"]
        assert entry.content_hash is not None
        assert entry.name == "doc.md"
        assert all(c.content_hash is not None for c in entry.chunks)
        # Rieseguire non cambia (idempotente)
        first_hash = entry.content_hash
        manager.migrate_state()
        assert entry.content_hash == first_hash

    def test_migrate_idempotent_assigned_existing(self, manager: KnowledgeBaseManager, workspace: Workspace):
        manager.add(workspace.path / "kb1")
        src = _write_source(workspace.path / "kb1", "doc.md", "p1\n\np2")
        entry = manager.add_file("kb1", src)
        file_id = entry.file_id
        content_hash = entry.content_hash
        manager.migrate_state()
        # non cambia
        assert entry.file_id == file_id
        assert entry.content_hash == content_hash