"""Test per BaseConfig, BaseConfigLoader, registry strategie e blocco cambio config."""

import logging

import pytest

from knowledge_base.base_config import (
    BASE_TOML_TEMPLATE,
    DEFAULTS_TOML_TEMPLATE,
    BaseConfig,
    BaseConfigLoader,
    ConfigChangeBlockedError,
    check_config_change_blocked,
    ensure_base_toml,
    ensure_defaults_toml,
    write_toml,
)
from knowledge_base.strategies import (
    StrategyRegistry,
    chunking_registry,
    embedding_registry,
    ingestion_registry,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


DEFAULTS_TOML = """\
[ingestion]
library = "markitdown"
params.use_gpu = true

[chunking]
method = "recursive"
chunk_size = 500
chunk_overlap = 100

[embedding]
model = "sentence-transformers/all-MiniLM-L6-v2"
"""

BASE_TOML = """\
[chunking]
chunk_size = 250

[embedding]
model = "BAAI/bge-m3"
device = "cpu"
"""


def _make_workspace(tmp_path, *, defaults=None, base_toml=None, base_name="kb1"):
    """Crea la struttura <workspace>/.knowledge-space/ e <base>/.knowledge-space/."""
    ws = tmp_path / "ws"
    ws.mkdir()
    if defaults is not None:
        _write(ws / ".knowledge-space" / "defaults.toml", defaults)
    if base_toml is not None:
        _write(ws / base_name / ".knowledge-space" / "base.toml", base_toml)
    return ws


# --------------------------------------------------------------------------- #
# BaseConfig — default hardcoded
# --------------------------------------------------------------------------- #


def test_base_config_hardcoded_defaults():
    cfg = BaseConfig()
    assert cfg.ingestion.library == "pymupdf4llm"
    assert cfg.chunking.method == "fixed_size"
    assert cfg.chunking.chunk_size == 2048
    assert cfg.chunking.chunk_overlap == 64
    assert cfg.embedding.model == "BAAI/bge-m3"
    assert cfg.embedding.device is None


# --------------------------------------------------------------------------- #
# BaseConfigLoader — cascata
# --------------------------------------------------------------------------- #


def test_cascade_full_override(tmp_path):
    """defaults.toml + base.toml: la base sovrascrive solo i campi presenti."""
    ws = _make_workspace(tmp_path, defaults=DEFAULTS_TOML, base_toml=BASE_TOML)
    loader = BaseConfigLoader(workspace_path=ws)
    cfg = loader.load("kb1")

    # da defaults.toml, non toccati dalla base
    assert cfg.ingestion.library == "markitdown"
    assert cfg.ingestion.params == {"use_gpu": True}
    assert cfg.chunking.method == "recursive"
    assert cfg.chunking.chunk_overlap == 100
    # override della base
    assert cfg.chunking.chunk_size == 250
    assert cfg.embedding.model == "BAAI/bge-m3"
    assert cfg.embedding.device == "cpu"


def test_cascade_base_missing_uses_workspace_defaults(tmp_path, caplog):
    """base.toml mancante → default del workspace, nessun warning."""
    ws = _make_workspace(tmp_path, defaults=DEFAULTS_TOML)
    loader = BaseConfigLoader(workspace_path=ws)

    with caplog.at_level(logging.WARNING):
        cfg = loader.load("kb1")

    assert cfg.chunking.method == "recursive"
    assert cfg.embedding.model == "sentence-transformers/all-MiniLM-L6-v2"
    assert not caplog.records


def test_cascade_defaults_missing_warns_and_falls_back(tmp_path, caplog):
    """defaults.toml mancante → warning + default hardcoded."""
    ws = _make_workspace(tmp_path, base_toml=BASE_TOML)
    loader = BaseConfigLoader(workspace_path=ws)

    with caplog.at_level(logging.WARNING):
        cfg = loader.load("kb1")

    assert cfg.ingestion.library == "pymupdf4llm"  # hardcoded
    assert cfg.chunking.chunk_size == 250  # dalla base
    assert any("defaults.toml" in r.message for r in caplog.records)


def test_cascade_both_missing_hardcoded_only(tmp_path, caplog):
    """Nessun TOML → default hardcoded (con warning per defaults.toml)."""
    ws = _make_workspace(tmp_path)
    loader = BaseConfigLoader(workspace_path=ws)

    with caplog.at_level(logging.WARNING):
        cfg = loader.load("kb1")

    assert cfg == BaseConfig()
    assert any("defaults.toml" in r.message for r in caplog.records)


def test_override_explicit_value_equal_to_default(tmp_path):
    """Un override esplicito al valore di default deve comunque vincere
    sulla cascata (es. la base rimette chunk_size=1000 dopo che il
    workspace l'aveva cambiato a 500)."""
    ws = _make_workspace(
        tmp_path,
        defaults='[chunking]\nchunk_size = 500\n',
        base_toml='[chunking]\nchunk_size = 1000\n',
    )
    loader = BaseConfigLoader(workspace_path=ws)
    cfg = loader.load("kb1")
    assert cfg.chunking.chunk_size == 1000


def test_loader_does_not_write_toml(tmp_path):
    """Il loader non deve mai creare/scrivere i file TOML."""
    ws = _make_workspace(tmp_path)
    loader = BaseConfigLoader(workspace_path=ws)
    loader.load("kb1")
    assert not loader.defaults_toml_path.exists()
    assert not loader.base_toml_path("kb1").exists()


# --------------------------------------------------------------------------- #
# Validazione TOML
# --------------------------------------------------------------------------- #


def test_unknown_fields_warn_and_fall_back(tmp_path, caplog):
    """Campi sconosciuti → warning + ignorati."""
    ws = _make_workspace(
        tmp_path,
        defaults='[chunking]\nchunk_size = 500\nunknown_field = 1\n',
    )
    loader = BaseConfigLoader(workspace_path=ws)

    with caplog.at_level(logging.WARNING):
        cfg = loader.load("kb1")

    assert cfg.chunking.chunk_size == 500
    assert any("unknown_field" in r.message for r in caplog.records)


def test_invalid_type_warns_and_section_falls_back(tmp_path, caplog):
    """Tipo invalido (chunk_size stringa) → warning + sezione ai default."""
    ws = _make_workspace(
        tmp_path,
        defaults='[chunking]\nchunk_size = "abc"\nmethod = "recursive"\n',
    )
    loader = BaseConfigLoader(workspace_path=ws)

    with caplog.at_level(logging.WARNING):
        cfg = loader.load("kb1")

    # l'intera sezione cade ai default hardcoded
    assert cfg.chunking.chunk_size == 2048
    assert cfg.chunking.method == "fixed_size"
    assert any("invalidi" in r.message for r in caplog.records)


def test_malformed_toml_raises(tmp_path):
    """TOML sintatticamente invalido → errore esplicito (non ingoiato)."""
    import tomllib

    ws = _make_workspace(tmp_path, defaults="[chunking\nchunk_size = ")
    loader = BaseConfigLoader(workspace_path=ws)
    with pytest.raises(tomllib.TOMLDecodeError):
        loader.load("kb1")


# --------------------------------------------------------------------------- #
# Registry delle strategie
# --------------------------------------------------------------------------- #


def test_registries_populated_at_import():
    assert set(ingestion_registry.list_names()) == {
        "identity",
        "docling",
        "pymupdf4llm",
        "markitdown",
    }
    assert set(chunking_registry.list_names()) == {
        "fixed_size",
        "recursive",
        "semantic",
        "sentence",
        "paragraph",
        "markdown",
    }
    # modelli locali + remoti
    assert "sentence-transformers/all-mpnet-base-v2" in embedding_registry.list_names()
    assert "BAAI/bge-m3" in embedding_registry.list_names()
    assert "openai/text-embedding-3-small" in embedding_registry.list_names()
    assert "cohere/embed-multilingual-v3.0" in embedding_registry.list_names()
    assert "voyage/voyage-3" in embedding_registry.list_names()


def test_registry_get_unknown_raises():
    registry = StrategyRegistry()
    with pytest.raises(KeyError, match="non-esiste"):
        registry.get("non-esiste")


def test_registry_register_and_get():
    class Dummy:
        pass

    registry = StrategyRegistry()
    registry.register("dummy", Dummy)
    assert registry.contains("dummy")
    assert registry.get("dummy") is Dummy
    assert registry.get_or_default(None, "dummy") is Dummy


def test_embedding_metadata_discoverable():
    cls = embedding_registry.get("BAAI/bge-m3")
    instance = cls()
    assert instance.metadata.dim == 1024
    assert instance.metadata.max_context_tokens == 8192
    assert instance.metadata.requires_api is False
    assert "multilingual" in instance.metadata.languages


def test_chunking_instantiable_from_config():
    """Il chunker di default si istanzia con i parametri della BaseConfig."""
    cfg = BaseConfig()
    cls = chunking_registry.get(cfg.chunking.method)
    chunker = cls(
        chunk_size=cfg.chunking.chunk_size,
        chunk_overlap=cfg.chunking.chunk_overlap,
    )
    assert chunker.chunk_size == 2048
    chunks = chunker.split("paragrafo uno.\n\nparagrafo due.")
    assert len(chunks) >= 1


# --------------------------------------------------------------------------- #
# Blocco cambio config (trigger 3/4/5)
# --------------------------------------------------------------------------- #


def test_no_block_when_collection_empty(tmp_path):
    """Collection vuota → nessun blocco anche se la config è cambiata."""
    cfg = BaseConfig()
    check_config_change_blocked(
        "kb1",
        cfg,
        registered_embedding_model="altro-modello",
        registered_chunking_method="recursive",
        registered_ingestion_library="markitdown",
        collection_non_empty=False,
    )


def test_no_block_when_nothing_registered():
    """Valori registrati None (base mai indicizzata) → nessun blocco."""
    cfg = BaseConfig()
    check_config_change_blocked(
        "kb1",
        cfg,
        registered_embedding_model=None,
        registered_chunking_method=None,
        registered_ingestion_library=None,
        collection_non_empty=True,
    )


def test_no_block_when_config_unchanged():
    cfg = BaseConfig()
    check_config_change_blocked(
        "kb1",
        cfg,
        registered_embedding_model=cfg.embedding.model,
        registered_chunking_method=cfg.chunking.method,
        registered_ingestion_library=cfg.ingestion.library,
        collection_non_empty=True,
    )


def test_block_on_embedding_model_change():
    cfg = BaseConfig()
    with pytest.raises(ConfigChangeBlockedError) as exc_info:
        check_config_change_blocked(
            "kb1",
            cfg,
            registered_embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            registered_chunking_method=cfg.chunking.method,
            registered_ingestion_library=cfg.ingestion.library,
            collection_non_empty=True,
        )
    msg = str(exc_info.value)
    assert "--model-change" in msg
    assert "kb1" in msg
    assert "sentence-transformers/all-MiniLM-L6-v2" in msg


def test_block_on_chunking_method_change():
    cfg = BaseConfig()
    with pytest.raises(ConfigChangeBlockedError) as exc_info:
        check_config_change_blocked(
            "kb1",
            cfg,
            registered_chunking_method="recursive",
            collection_non_empty=True,
        )
    assert "--chunking-change" in str(exc_info.value)


def test_block_on_ingestion_library_change():
    cfg = BaseConfig()
    with pytest.raises(ConfigChangeBlockedError) as exc_info:
        check_config_change_blocked(
            "kb1",
            cfg,
            registered_ingestion_library="markitdown",
            collection_non_empty=True,
        )
    assert "--ingestion-change" in str(exc_info.value)


def test_block_reports_all_simultaneous_changes():
    """Più cambi contemporanei → un unico errore che li elenca tutti."""
    cfg = BaseConfig()
    with pytest.raises(ConfigChangeBlockedError) as exc_info:
        check_config_change_blocked(
            "kb1",
            cfg,
            registered_embedding_model="altro-modello",
            registered_chunking_method="recursive",
            registered_ingestion_library="docling",
            collection_non_empty=True,
        )
    err = exc_info.value
    assert len(err.changes) == 3
    msg = str(err)
    assert "--model-change" in msg
    assert "--chunking-change" in msg
    assert "--ingestion-change" in msg


# --------------------------------------------------------------------------- #
# from_toml su dict vuoto (template con soli commenti)
# --------------------------------------------------------------------------- #


def test_from_toml_empty_dict_returns_hardcoded_defaults():
    """``from_toml({})`` (file con soli commenti → dict vuoto) non solleva."""
    cfg = BaseConfig.from_toml({})
    assert cfg == BaseConfig()
    assert cfg.ingestion.library == "pymupdf4llm"
    assert cfg.chunking.chunk_size == 2048
    assert cfg.embedding.model == "BAAI/bge-m3"


# --------------------------------------------------------------------------- #
# ensure_defaults_toml / ensure_base_toml
# --------------------------------------------------------------------------- #


def test_ensure_defaults_toml_creates_file(tmp_path):
    """Crea defaults.toml se assente, ritorna (path, True)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    path, created = ensure_defaults_toml(ws)
    assert created is True
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content == DEFAULTS_TOML_TEMPLATE
    # La dotfolder è stata creata
    assert (ws / ".knowledge-space").is_dir()


def test_ensure_defaults_toml_idempotent(tmp_path):
    """Seconda chiamata non sovrascrive, ritorna (path, False)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    path1, created1 = ensure_defaults_toml(ws)
    path2, created2 = ensure_defaults_toml(ws)
    assert created1 is True
    assert created2 is False
    assert path1 == path2


def test_ensure_defaults_toml_preserves_existing(tmp_path):
    """Non sovrascrive un defaults.toml già presente (modificato dall'utente)."""
    ws = tmp_path / "ws"
    dot = ws / ".knowledge-space"
    dot.mkdir(parents=True)
    existing = dot / "defaults.toml"
    custom = "# custom config\n[chunking]\nchunk_size = 42\n"
    existing.write_text(custom, encoding="utf-8")

    path, created = ensure_defaults_toml(ws)
    assert created is False
    assert existing.read_text(encoding="utf-8") == custom


def test_ensure_base_toml_creates_file(tmp_path):
    """Crea base.toml se assente, ritorna (path, True)."""
    base = tmp_path / "base"
    base.mkdir()
    path, created = ensure_base_toml(base)
    assert created is True
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content == BASE_TOML_TEMPLATE
    assert (base / ".knowledge-space").is_dir()


def test_ensure_base_toml_idempotent(tmp_path):
    """Seconda chiamata non sovrascrive, ritorna (path, False)."""
    base = tmp_path / "base"
    base.mkdir()
    path1, created1 = ensure_base_toml(base)
    path2, created2 = ensure_base_toml(base)
    assert created1 is True
    assert created2 is False
    assert path1 == path2


def test_ensure_base_toml_preserves_existing(tmp_path):
    """Non sovrascrive un base.toml già presente."""
    base = tmp_path / "base"
    dot = base / ".knowledge-space"
    dot.mkdir(parents=True)
    existing = dot / "base.toml"
    custom = "[chunking]\nchunk_size = 999\n"
    existing.write_text(custom, encoding="utf-8")

    path, created = ensure_base_toml(base)
    assert created is False
    assert existing.read_text(encoding="utf-8") == custom


def test_base_toml_template_has_only_comments():
    """Il template base.toml contiene solo commenti, nessun valore attivo."""
    # Il template deve parsare come dict vuoto da TOML
    import tomllib

    data = tomllib.loads(BASE_TOML_TEMPLATE)
    assert data == {}


def test_defaults_toml_template_is_valid_toml():
    """Il template defaults.toml è TOML valido e imposta i campi attesi."""
    import tomllib

    data = tomllib.loads(DEFAULTS_TOML_TEMPLATE)
    assert data["ingestion"]["library"] == "pymupdf4llm"
    assert data["chunking"]["method"] == "fixed_size"
    assert data["chunking"]["chunk_size"] == 2048
    assert data["chunking"]["chunk_overlap"] == 64
    assert data["embedding"]["model"] == "BAAI/bge-m3"


# --------------------------------------------------------------------------- #
# write_toml — roundtrip e comportamento
# --------------------------------------------------------------------------- #


def test_write_toml_roundtrip(tmp_path):
    """Scrivi → leggi → i valori corrispondono."""
    import tomllib

    path = tmp_path / "test.toml"
    data = {
        "ingestion": {"library": "markitdown"},
        "chunking": {"method": "fixed_size", "chunk_size": 500},
    }
    write_toml(path, data)

    with open(path, "rb") as f:
        loaded = tomllib.load(f)
    assert loaded["ingestion"]["library"] == "markitdown"
    assert loaded["chunking"]["chunk_size"] == 500
    assert loaded["chunking"]["method"] == "fixed_size"


def test_write_toml_creates_parent_dirs(tmp_path):
    """La cartella padre viene creata se necessario."""
    path = tmp_path / "deep" / "nested" / "config.toml"
    write_toml(path, {"section": {"key": "value"}})
    assert path.exists()


def test_write_toml_overwrites_existing(tmp_path):
    """Sovrascrive un file esistente."""
    import tomllib

    path = tmp_path / "test.toml"
    write_toml(path, {"a": {"x": 1}})
    write_toml(path, {"a": {"x": 2}, "b": {"y": 3}})

    with open(path, "rb") as f:
        loaded = tomllib.load(f)
    assert loaded["a"]["x"] == 2
    assert loaded["b"]["y"] == 3


def test_write_toml_handles_various_types(tmp_path):
    """Gestisce tipi nativi: str, int, float, bool, list."""
    import tomllib

    path = tmp_path / "types.toml"
    data = {
        "s": {"str_val": "hello"},
        "i": {"int_val": 42},
        "f": {"float_val": 3.14},
        "b": {"bool_val": True},
        "l": {"list_val": ["a", "b", "c"]},
    }
    write_toml(path, data)

    with open(path, "rb") as f:
        loaded = tomllib.load(f)
    assert loaded["s"]["str_val"] == "hello"
    assert loaded["i"]["int_val"] == 42
    assert loaded["f"]["float_val"] == 3.14
    assert loaded["b"]["bool_val"] is True
    assert loaded["l"]["list_val"] == ["a", "b", "c"]
