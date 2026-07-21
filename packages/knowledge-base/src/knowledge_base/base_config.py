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


# --------------------------------------------------------------------------- #
# BaseConfig
# --------------------------------------------------------------------------- #


class BaseConfig(BaseModel):
    """Configurazione completa di una base di conoscenza.

    Le tre sotto-sezioni possono essere sovrascritte indipendentemente dai
    file TOML della cascata. Il metodo :meth:`override` fonde un'altra
    ``BaseConfig`` (parziale) sopra questa, restituendo una nuova istanza.
    """

    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

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

        return cls(ingestion=ingestion, chunking=chunking, embedding=embedding)


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
