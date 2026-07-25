"""Configurazione per-base (TOML).

``BaseConfig`` racchiude le tre sezioni di configurazione di una base di
conoscenza: ``ingestion``, ``chunking`` e ``embedding``. I valori vengono
caricati da file TOML con una cascata di default (hardcoded → workspace →
base). La libreria non scrive mai i TOML: li legge soltanto.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Sotto-sezioni
# --------------------------------------------------------------------------- #


class IngestionConfig(BaseModel):
    """Sezione ``[ingestion]`` del TOML."""

    library: str = "docling"
    params: Dict[str, Any] = Field(default_factory=dict)


class ChunkingConfig(BaseModel):
    """Sezione ``[chunking]`` del TOML."""

    method: str = "fixed_size"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    separator: str = "\n\n"
    params: Dict[str, Any] = Field(default_factory=dict)


class EmbeddingConfig(BaseModel):
    """Sezione ``[embedding]`` del TOML."""

    model: str = "sentence-transformers/all-mpnet-base-v2"
    device: Optional[str] = None
    api_base: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class PreRetrievalStageConfig(BaseModel):
    """Singolo stadio nella sezione ``[pre_retrieval]`` del TOML."""

    method: str = "identity"
    params: Dict[str, Any] = Field(default_factory=dict)


class PreRetrievalConfig(BaseModel):
    """Sezione ``[pre_retrieval]`` del TOML."""

    stages: List[PreRetrievalStageConfig] = Field(
        default_factory=lambda: [PreRetrievalStageConfig()]
    )


class RetrievalConfig(BaseModel):
    """Sezione ``[retrieval]`` del TOML."""

    method: str = "dense"
    query_mode: str = "original"
    top_k: int = 10
    params: Dict[str, Any] = Field(default_factory=dict)


class PostRetrievalConfig(BaseModel):
    """Sezione ``[post_retrieval]`` del TOML."""

    method: str = "identity"
    params: Dict[str, Any] = Field(default_factory=dict)


class GraphConfig(BaseModel):
    """Sezione ``[graph]`` del TOML per-base (Fase 1C)."""

    enabled: bool = False
    on_chunk_change: str = "lazy"  # "eager" | "lazy"
    retriever: str = "hybrid_cypher"
    schema_mode: str = "FREE"  # "FREE" | "EXTRACTED" | "manuale"
    resolver: str = "exact"  # "exact" | "semantic" | "none"
    extraction_model: Optional[str] = None
    schema_model: Optional[str] = None
    top_k: int = 5
    vector_index: str = "chunk-embeddings"
    fulltext_index: str = "chunk-text"
    retrieval_query: str = ""
    return_properties: List[str] = Field(default_factory=lambda: ["chunk_id", "text"])
    chunk_embedding_property: str = "embedding"
    params: Dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# BaseConfig
# --------------------------------------------------------------------------- #


class BaseConfig(BaseModel):
    """Configurazione completa di una base di conoscenza.

    Le sotto-sezioni possono essere sovrascritte indipendentemente dai
    file TOML della cascata. Il metodo :meth:`override` fonde un'altra
    ``BaseConfig`` (parziale) sopra questa, restituendo una nuova istanza.
    """

    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    pre_retrieval: PreRetrievalConfig = Field(default_factory=PreRetrievalConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    post_retrieval: PostRetrievalConfig = Field(default_factory=PostRetrievalConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)

    # .................................................................... #
    # Merge / override
    # .................................................................... #

    def override(self, other: "BaseConfig") -> "BaseConfig":
        """Fonde ``other`` sopra questa configurazione.

        Per ogni sotto-sezione, solo i campi di ``other`` che sono stati
        **esplicitamente impostati** (``model_fields_set``, tipicamente
        presenti nel TOML) sovrascrivono quelli di ``self``. Restituisce
        una nuova ``BaseConfig``.
        """
        return BaseConfig(
            ingestion=self._merge_section(self.ingestion, other.ingestion),
            chunking=self._merge_section(self.chunking, other.chunking),
            embedding=self._merge_section(self.embedding, other.embedding),
            pre_retrieval=self._merge_section(
                self.pre_retrieval, other.pre_retrieval
            ),
            retrieval=self._merge_section(self.retrieval, other.retrieval),
            post_retrieval=self._merge_section(
                self.post_retrieval, other.post_retrieval
            ),
            graph=self._merge_section(self.graph, other.graph),
        )

    @staticmethod
    def _merge_section(base: BaseModel, override: BaseModel) -> BaseModel:
        """Fonde due istanze della stessa sotto-sezione.

        I campi di ``override`` esplicitamente impostati (presenti nel TOML
        di provenienza) sovrascrivono quelli di ``base``; gli altri ereditano.
        """
        updates = {
            name: getattr(override, name) for name in override.model_fields_set
        }
        return base.model_copy(update=updates)

    # .................................................................... #
    # Caricamento da TOML
    # .................................................................... #

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> "BaseConfig":
        """Costruisce una ``BaseConfig`` da un dizionario già parsato da TOML.

        Solo i campi presenti nel TOML vengono marcati come "esplicitamente
        impostati" (``model_fields_set``), in modo che :meth:`override` li
        applichi nella cascata. I campi sconosciuti vengono ignorati con un
        warning; i valori con tipo invalido fanno cadere l'intera sezione ai
        default, sempre con un warning (regola "valida il TOML all'avvio").
        """
        ingestion = IngestionConfig()
        chunking = ChunkingConfig()
        embedding = EmbeddingConfig()

        if "ingestion" in data:
            section = data["ingestion"]
            known = {"library", "params"}
            for key in section:
                if key not in known:
                    logger.warning(
                        "[ingestion] campo sconosciuto '%s' ignorato", key
                    )
            kwargs = {k: v for k, v in section.items() if k in known}
            if "params" in kwargs and not isinstance(kwargs["params"], dict):
                logger.warning("[ingestion].params non è un dict, ignorato")
                del kwargs["params"]
            try:
                ingestion = IngestionConfig(**kwargs)
            except ValidationError as exc:
                logger.warning(
                    "[ingestion] valori invalidi (%s): sezione ai default", exc
                )

        if "chunking" in data:
            section = data["chunking"]
            known = {"method", "chunk_size", "chunk_overlap", "separator", "params"}
            for key in section:
                if key not in known:
                    logger.warning(
                        "[chunking] campo sconosciuto '%s' ignorato", key
                    )
            kwargs = {k: v for k, v in section.items() if k in known}
            if "params" in kwargs and not isinstance(kwargs["params"], dict):
                logger.warning("[chunking].params non è un dict, ignorato")
                del kwargs["params"]
            try:
                chunking = ChunkingConfig(**kwargs)
            except ValidationError as exc:
                logger.warning(
                    "[chunking] valori invalidi (%s): sezione ai default", exc
                )

        if "embedding" in data:
            section = data["embedding"]
            known = {"model", "device", "api_base", "params"}
            for key in section:
                if key not in known:
                    logger.warning(
                        "[embedding] campo sconosciuto '%s' ignorato", key
                    )
            kwargs = {k: v for k, v in section.items() if k in known}
            if "params" in kwargs and not isinstance(kwargs["params"], dict):
                logger.warning("[embedding].params non è un dict, ignorato")
                del kwargs["params"]
            try:
                embedding = EmbeddingConfig(**kwargs)
            except ValidationError as exc:
                logger.warning(
                    "[embedding] valori invalidi (%s): sezione ai default", exc
                )

        pre_retrieval = PreRetrievalConfig()
        retrieval = RetrievalConfig()
        post_retrieval = PostRetrievalConfig()

        if "pre_retrieval" in data:
            section = data["pre_retrieval"]
            known = {"stages"}
            for key in section:
                if key not in known:
                    logger.warning(
                        "[pre_retrieval] campo sconosciuto '%s' ignorato", key
                    )
            if "stages" in section:
                stages = section["stages"]
                if isinstance(stages, list):
                    parsed_stages = []
                    for s in stages:
                        if isinstance(s, dict):
                            try:
                                parsed_stages.append(
                                    PreRetrievalStageConfig(**s)
                                )
                            except ValidationError as exc:
                                logger.warning(
                                    "[pre_retrieval] stage invalido (%s): ignorato",
                                    exc,
                                )
                        else:
                            logger.warning(
                                "[pre_retrieval] stage non è un dict: ignorato"
                            )
                    if parsed_stages:
                        pre_retrieval = PreRetrievalConfig(stages=parsed_stages)
                else:
                    logger.warning(
                        "[pre_retrieval].stages non è una lista: ignorato"
                    )

        if "retrieval" in data:
            section = data["retrieval"]
            known = {"method", "query_mode", "top_k", "params"}
            for key in section:
                if key not in known:
                    logger.warning(
                        "[retrieval] campo sconosciuto '%s' ignorato", key
                    )
            kwargs = {k: v for k, v in section.items() if k in known}
            if "params" in kwargs and not isinstance(kwargs["params"], dict):
                logger.warning("[retrieval].params non è un dict, ignorato")
                del kwargs["params"]
            try:
                retrieval = RetrievalConfig(**kwargs)
            except ValidationError as exc:
                logger.warning(
                    "[retrieval] valori invalidi (%s): sezione ai default", exc
                )

        if "post_retrieval" in data:
            section = data["post_retrieval"]
            known = {"method", "params"}
            for key in section:
                if key not in known:
                    logger.warning(
                        "[post_retrieval] campo sconosciuto '%s' ignorato", key
                    )
            kwargs = {k: v for k, v in section.items() if k in known}
            if "params" in kwargs and not isinstance(kwargs["params"], dict):
                logger.warning("[post_retrieval].params non è un dict, ignorato")
                del kwargs["params"]
            try:
                post_retrieval = PostRetrievalConfig(**kwargs)
            except ValidationError as exc:
                logger.warning(
                    "[post_retrieval] valori invalidi (%s): sezione ai default",
                    exc,
                )

        graph = GraphConfig()

        if "graph" in data:
            section = data["graph"]
            known = {
                "enabled", "on_chunk_change", "retriever", "schema",
                "resolver", "extraction_model", "schema_model", "top_k",
                "vector_index", "fulltext_index", "retrieval_query",
                "return_properties", "chunk_embedding_property", "params",
            }
            for key in section:
                if key not in known:
                    logger.warning(
                        "[graph] campo sconosciuto '%s' ignorato", key
                    )
            kwargs = {}
            for k, v in section.items():
                if k not in known:
                    continue
                # TOML usa "schema", il modello Pydantic "schema_mode"
                if k == "schema":
                    kwargs["schema_mode"] = v
                else:
                    kwargs[k] = v
            if "params" in kwargs and not isinstance(kwargs["params"], dict):
                logger.warning("[graph].params non è un dict, ignorato")
                del kwargs["params"]
            if "return_properties" in kwargs and not isinstance(
                kwargs["return_properties"], list
            ):
                logger.warning(
                    "[graph].return_properties non è una lista, ignorato"
                )
                del kwargs["return_properties"]
            try:
                graph = GraphConfig(**kwargs)
            except ValidationError as exc:
                logger.warning(
                    "[graph] valori invalidi (%s): sezione ai default", exc
                )

        return cls(
            ingestion=ingestion,
            chunking=chunking,
            embedding=embedding,
            pre_retrieval=pre_retrieval,
            retrieval=retrieval,
            post_retrieval=post_retrieval,
            graph=graph,
        )


# --------------------------------------------------------------------------- #
# BaseConfigLoader — cascata di default
# --------------------------------------------------------------------------- #


class BaseConfigLoader:
    """Carica la ``BaseConfig`` di una base seguendo la cascata di default.

    Ordine di precedenza (dal più basso al più alto):

    1. **Default hardcoded** — i valori di default delle classi Pydantic.
    2. **``<workspace>/.knowledge-space/defaults.toml``** — default per
       tutte le basi del workspace. Se manca, warning all'avvio.
    3. **``<base>/.knowledge-space/base.toml``** — configurazione specifica
       della base. Se manca, nessun warning (comportamento legittimo).

    Il loader **non scrive mai** i file TOML: li legge soltanto.
    """

    def __init__(
        self,
        workspace_path: Path,
        dot_folder_name: str = ".knowledge-space",
    ) -> None:
        self._workspace_path = Path(workspace_path)
        self._dot = dot_folder_name

    # .................................................................... #
    # Path helpers
    # .................................................................... #

    @property
    def workspace_dot_dir(self) -> Path:
        return self._workspace_path / self._dot

    @property
    def defaults_toml_path(self) -> Path:
        return self.workspace_dot_dir / "defaults.toml"

    def base_toml_path(self, base_name: str) -> Path:
        return self._workspace_path / base_name / self._dot / "base.toml"

    # .................................................................... #
    # Caricamento
    # .................................................................... #

    def load(self, base_name: str) -> BaseConfig:
        """Carica la configurazione di una base con la cascata completa."""
        # 1. Default hardcoded
        config = BaseConfig()

        # 2. Override con defaults.toml del workspace
        defaults_path = self.defaults_toml_path
        if defaults_path.exists():
            with open(defaults_path, "rb") as f:
                config = config.override(BaseConfig.from_toml(tomllib.load(f)))
        else:
            logger.warning(
                "defaults.toml non trovato in %s: uso default hardcoded",
                defaults_path,
            )

        # 3. Override con base.toml della base specifica
        base_path = self.base_toml_path(base_name)
        if base_path.exists():
            with open(base_path, "rb") as f:
                config = config.override(BaseConfig.from_toml(tomllib.load(f)))
        # base.toml mancante → comportamento legittimo, nessun warning

        return config

    def load_hardcoded_only(self) -> BaseConfig:
        """Restituisce la configurazione con i soli default hardcoded."""
        return BaseConfig()

    def load_workspace_defaults(self) -> BaseConfig:
        """Carica hardcoded + defaults.toml (senza override base-specifico)."""
        config = BaseConfig()
        defaults_path = self.defaults_toml_path
        if defaults_path.exists():
            with open(defaults_path, "rb") as f:
                config = config.override(BaseConfig.from_toml(tomllib.load(f)))
        return config


# --------------------------------------------------------------------------- #
# Blocco cambio config (trigger 3/4/5 di 45-indexing-incrementale.md)
# --------------------------------------------------------------------------- #


class ConfigChangeBlockedError(RuntimeError):
    """Sollevata quando la configurazione di una base è cambiata rispetto a
    quanto registrato nello stato, ma la collection Chroma non è vuota.

    Il messaggio suggerisce il comando ``ks reindex <base> --<reason>``
    necessario per sbloccare la base.
    """

    def __init__(
        self,
        base_name: str,
        changes: List[Tuple[str, Optional[str], str, str]],
    ) -> None:
        self.base_name = base_name
        self.changes = changes
        lines = [
            f"Configurazione della base '{base_name}' cambiata, ma la "
            "collection Chroma non è vuota. Modifiche rilevate:"
        ]
        for field, old, new, reason_flag in changes:
            lines.append(f"  - {field}: '{old}' -> '{new}'")
        reasons = " ".join(
            f"'ks reindex {base_name} {flag}'" for _, _, _, flag in changes
        )
        lines.append(
            f"Eseguire il reindex esplicito: {reasons}"
        )
        super().__init__("\n".join(lines))


def check_config_change_blocked(
    base_name: str,
    config: BaseConfig,
    *,
    registered_embedding_model: Optional[str] = None,
    registered_chunking_method: Optional[str] = None,
    registered_ingestion_library: Optional[str] = None,
    collection_non_empty: bool = False,
) -> None:
    """Verifica il blocco cambio config all'avvio (trigger 3/4/5).

    Confronta la ``BaseConfig`` caricata con i valori registrati in
    ``state.json`` per la base. Se un valore critico differisce **e** la
    collection Chroma non è vuota, solleva :class:`ConfigChangeBlockedError`.

    I valori registrati possono essere ``None`` (base mai indicizzata):
    in tal caso non c'è blocco, perché non esiste nulla da invalidare.

    ``collection_non_empty`` è iniettato dal chiamante (Step 7 lo calcolerà
    da Chroma); in questo step non esiste ancora un vector store cablato.
    """
    if not collection_non_empty:
        return

    changes: List[Tuple[str, Optional[str], str, str]] = []

    if (
        registered_embedding_model is not None
        and config.embedding.model != registered_embedding_model
    ):
        changes.append(
            (
                "[embedding].model",
                registered_embedding_model,
                config.embedding.model,
                "--model-change",
            )
        )

    if (
        registered_chunking_method is not None
        and config.chunking.method != registered_chunking_method
    ):
        changes.append(
            (
                "[chunking].method",
                registered_chunking_method,
                config.chunking.method,
                "--chunking-change",
            )
        )

    if (
        registered_ingestion_library is not None
        and config.ingestion.library != registered_ingestion_library
    ):
        changes.append(
            (
                "[ingestion].library",
                registered_ingestion_library,
                config.ingestion.library,
                "--ingestion-change",
            )
        )

    if changes:
        raise ConfigChangeBlockedError(base_name, changes)
