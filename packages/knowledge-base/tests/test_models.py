"""Test dei modelli Pydantic di dominio."""

from pathlib import Path

from knowledge_base.models import (
    ChunkRef,
    Domain,
    FileEntry,
    GlobalIndexData,
    KnowledgeBase,
    Workspace,
    WorkspaceConfigData,
)


def test_chunkref_defaults():
    chunk = ChunkRef(index=0)
    assert chunk.index == 0
    assert chunk.active is True


def test_file_entry_with_chunks():
    file_entry = FileEntry(
        mtime=1783699858.842,
        added="2026-07-13T20:04:44",
        chunks=[ChunkRef(index=0), ChunkRef(index=1, active=False)],
    )
    assert file_entry.active is True
    assert len(file_entry.chunks) == 2
    assert file_entry.chunks[1].active is False


def test_knowledge_base_serialization_roundtrip(tmp_path):
    kb = KnowledgeBase(
        path=tmp_path / "test_kb1",
        files={
            "doc.pdf": FileEntry(
                mtime=1783699858.842,
                added="2026-07-13T20:04:44",
                chunks=[ChunkRef(index=0), ChunkRef(index=1)],
            )
        },
    )
    json_text = kb.model_dump_json()
    restored = KnowledgeBase.model_validate_json(json_text)
    assert restored.path == kb.path
    assert restored.active is True
    assert "doc.pdf" in restored.files
    assert restored.files["doc.pdf"].chunks[1].index == 1


def test_domain_serialization():
    domain = Domain(name="domain1", base_names=["kb1", "kb2"])
    restored = Domain.model_validate_json(domain.model_dump_json())
    assert restored.name == "domain1"
    assert restored.base_names == ["kb1", "kb2"]
    assert restored.active is True


def test_workspace_serialization_roundtrip(tmp_path):
    ws = Workspace(
        path=tmp_path,
        domains=[Domain(name="domain1", base_names=["test_kb1"])],
        bases={
            "test_kb1": KnowledgeBase(
                path=tmp_path / "test_kb1",
                files={
                    "file.pdf": FileEntry(
                        mtime=1.0,
                        added="2026-07-13T20:04:44",
                        chunks=[ChunkRef(index=0)],
                    )
                },
            )
        },
    )
    json_text = ws.model_dump_json()
    restored = Workspace.model_validate_json(json_text)
    assert restored.path == ws.path
    assert restored.domains[0].base_names == ["test_kb1"]
    assert "test_kb1" in restored.bases
    assert restored.bases["test_kb1"].files["file.pdf"].chunks[0].active is True


def test_global_index_data_defaults():
    index = GlobalIndexData()
    assert index.version == 1
    assert index.last_workspace is None
    assert index.workspaces == []


def test_workspace_config_data_roundtrip():
    data = WorkspaceConfigData(
        domains=[Domain(name="domain1")],
        bases={"kb1": KnowledgeBase(path=Path("/ws/kb1"))},
    )
    restored = WorkspaceConfigData.model_validate_json(data.model_dump_json())
    assert restored.version == 1
    assert len(restored.domains) == 1
    assert "kb1" in restored.bases