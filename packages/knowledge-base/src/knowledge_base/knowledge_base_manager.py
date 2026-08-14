"""Logica operativa sulle basi di conoscenza: indicizzazione vettoriale.

Il :class:`KnowledgeBaseManager` orchestra la pipeline
``ingestion → chunking → embedding → Chroma`` su un singolo file e
mantiene lo stato (:class:`WorkspaceConfig` ↔ ``state.json``). Incapsula
 Chroma e le strategie: nessuna variabile globale, tutto iniettato al
costruttore. Dipendenze strette: :class:`BaseConfig`, i registry delle
strategie (Step 4/5/6) e un embedder factory.

ID deterministico (Spec ``docs/91a-roadmap-fase1-ingestione.md`` Step 7):

- ``file_id`` (UUID4) assegnato alla prima indicizzazione, stabile per
  la vita del file (disaccoppia dal nome sorgente → rename/rename non
  cambia chunk_id, vedi ``docs/45-indexing-incrementale.md`` trigger 2).
- ``chunk_id = f"{base_name}::{file_id}::{i}"`` → chiave Chroma.

Persistenza chunk su disco (prodotto derivato, non editabile):

``<base>/.knowledge-space/chunks/<file_id>/<file_id>_chunk_<i>.md``

Il manager riscrive solo i chunk con ``content_hash`` cambiato (trigger
1, approccio B per insert in mezzo).

Blocco cambio config (trigger 3/4/5): all'avvio ``check_config_change``
confronta ``BaseConfig`` con i valori registrati ``KnowledgeBase.embedding_model``
/ ``chunking_method`` / ``ingestion_library`` se la collection Chroma
non è vuota.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from knowledge_base.base_config import (
    BaseConfig,
    ConfigChangeBlockedError,
    check_config_change_blocked,
)
from knowledge_base.models import (
    ChunkRef,
    FileEntry,
    KnowledgeBase,
    Workspace,
)
from knowledge_base.persistence import WorkspaceConfig
from knowledge_base.strategies import (
    EmbeddingStrategy,
    chunking_registry,
    embedding_registry,
    ingestion_registry,
)
from knowledge_base.strategies.ingestion import IdentityIngestion
from knowledge_base.strategies.embedding import (
    ChunkTooLongError,
    validate_chunk_context,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Tipi factory iniettabili
# --------------------------------------------------------------------------- #


# Dato BaseConfig, restituisce la strategy di ingestion istanziata.
IngestionFactory = Callable[[BaseConfig], Any]
ChunkingFactory = Callable[[BaseConfig, Optional[EmbeddingStrategy]], Any]
EmbedderFactory = Callable[[str], EmbeddingStrategy]

ConfigPathFor = Callable[[Path], Path]


# --------------------------------------------------------------------------- #
# Eccezioni
# --------------------------------------------------------------------------- #


class BaseNotFoundError(KeyError):
    """Sollevata quando una base non è presente nel workspace."""


class FileAlreadyIndexedError(ValueError):
    """Sollevata quando ``add_file`` riceve un path già indicizzato."""


class ChunkPersistError(RuntimeError):
    """Sollevata quando un chunk supera il limite ``max_context_tokens``."""


# Chroma: 3–512 char, [a-zA-Z0-9._-], start/end alnum.
_CHROMA_NAME_RE = re.compile(
    r"^(?:[a-zA-Z0-9]{1,2}|[a-zA-Z0-9][a-zA-Z0-9._-]{0,510}[a-zA-Z0-9])$"
)


def chroma_collection_name(base_name: str) -> str:
    """Deriva un nome collection Chroma valido dal nome della base.

    Se ``ks_<base_name>`` è già conforme alle regole Chroma, lo restituisce
    invariato (retrocompatibilità). Altrimenti slugifica i caratteri non
    ammessi e aggiunge un suffisso hash a 8 hex del nome originale per
    evitare collisioni (es. ``A B`` vs ``A_B``).
    """
    candidate = f"ks_{base_name}"
    if 3 <= len(candidate) <= 512 and _CHROMA_NAME_RE.match(candidate):
        return candidate

    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", base_name)
    slug = re.sub(r"_+", "_", slug).strip(".-_")
    if not slug:
        slug = "base"
    if not slug[0].isalnum():
        slug = f"b{slug}"
    if not slug[-1].isalnum():
        slug = f"{slug}0"

    digest = hashlib.sha1(base_name.encode("utf-8")).hexdigest()[:8]
    # ks_ (3) + slug + _ (1) + digest (8)
    max_slug = 512 - 3 - 1 - 8
    slug = slug[:max_slug]
    if not slug[-1].isalnum():
        slug = f"{slug.rstrip('._-')}0" or "base"
    name = f"ks_{slug}_{digest}"
    # digest è hex → fine alnum garantita; inizio ks_ + slug alnum garantito
    assert _CHROMA_NAME_RE.match(name), name
    return name


# --------------------------------------------------------------------------- #
# KnowledgeBaseManager
# --------------------------------------------------------------------------- #


def _default_ingestion_factory(config: BaseConfig) -> Any:
    """Costruisce la strategy di ingestion dal registry (Step 4)."""
    cls = ingestion_registry.get(config.ingestion.library)
    return cls(**(config.ingestion.params or {}))


def _default_chunking_factory(
    config: BaseConfig,
    embedder: Optional[EmbeddingStrategy],
) -> Any:
    """Costruisce la strategy di chunking dal registry (Step 5).

    Per strategie con ``requires_embedding=True`` passa l'embedder (es.
    ``semantic``); altrimenti ``embedder`` è ignorato.
    """
    cls = chunking_registry.get(config.chunking.method)
    chunk_params: Dict[str, Any] = {
        "chunk_size": config.chunking.chunk_size,
        "chunk_overlap": config.chunking.chunk_overlap,
        "separator": config.chunking.separator,
    }
    chunk_params.update(config.chunking.params or {})
    if cls.requires_embedding:
        chunk_params["embedder"] = embedder
    return cls(**chunk_params)


def _default_embedder_factory(model_name: str) -> EmbeddingStrategy:
    """Costruisce l'embedder dal registry (Step 6).

    Risolve il caso ``device``/``api_base`` via env var del modello
    specifico: per semplicità la factory di default non implementa questi
    override (gestiti da ``AppContext`` Step 8-ter). L'istanza è creata
    dal registry come già fatto per i test di embedding.
    """
    cls = embedding_registry.get(model_name)
    return cls()


class KnowledgeBaseManager:
    """Pipeline ingestion → chunking → embedding → Chroma per una base.

    Il manager opera su un singolo :class:`Workspace` e persiste lo stato
    via ``WorkspaceConfig`` (``config.json`` del workspace). L'istanza di
    Chroma è creata on demand per base e incapsulata: nessuna variabile
    globale.

    Le factory (ingestion/chunking/embedder) sono iniettabili per
    agevolare i test con mock; i default usano i registry di Step 4/5/6.
    """

    def __init__(
        self,
        workspace: Workspace,
        config_loader: Optional[Callable[[str], BaseConfig]] = None,
        *,
        config_path_for: ConfigPathFor,
        chroma_path: Optional[Path] = None,
        ingestion_factory: IngestionFactory = _default_ingestion_factory,
        chunking_factory: ChunkingFactory = _default_chunking_factory,
        embedder_factory: EmbedderFactory = _default_embedder_factory,
        dot_folder_name: str = ".knowledge-space",
    ) -> None:
        self._workspace = workspace
        self._config_loader = config_loader
        self._config_path_for = config_path_for
        self._chroma_path = Path(chroma_path) if chroma_path else None
        self._ingestion_factory = ingestion_factory
        self._chunking_factory = chunking_factory
        self._embedder_factory = embedder_factory
        self._dot = dot_folder_name
        # cache embedder per model_name (retry dalla factory)
        self._embedder_cache: Dict[str, EmbeddingStrategy] = {}

    # ..................................................................... #
    # Helper persistenza
    # ..................................................................... #

    def _ws_config(self) -> WorkspaceConfig:
        return WorkspaceConfig(
            config_path=self._config_path_for(Path(self._workspace.path)),
            workspace_path=Path(self._workspace.path),
        )

    def _save(self) -> None:
        from knowledge_base.models import WorkspaceConfigData

        self._ws_config().save(
            WorkspaceConfigData(
                version=1,
                domains=self._workspace.domains,
                bases=self._workspace.bases,
            )
        )

    def _select_ingestion(self, config: BaseConfig, src: Path) -> Any:
        """Seleziona la strategy di ingestion con fallback per testo semplice.

        Se la library configurata non supporta l'estensione del file ma
        questa è ``.md``/``.txt``, usa :class:`IdentityIngestion` (lettura
        diretta, nessuna conversione). Altrimenti lascia che sia la library
        configurata a sollevare :class:`UnsupportedFormatError` con il
        messaggio corretto.
        """
        ingestion = self._ingestion_factory(config)
        ext = src.suffix.lower()
        if (
            ext not in ingestion.supported_extensions
            and ext in IdentityIngestion.supported_extensions
        ):
            logger.info(
                "Estensione %s non supportata da '%s': fallback a identity",
                ext,
                config.ingestion.library,
            )
            return IdentityIngestion()
        return ingestion

    def _load_base_by_name(self, base_name: str) -> KnowledgeBase:
        if base_name not in self._workspace.bases:
            raise BaseNotFoundError(base_name)
        return self._workspace.bases[base_name]

    def _load_base_config(self, base_name: str) -> BaseConfig:
        if self._config_loader is None:
            raise RuntimeError(
                "Nessun config_loader fornito a KnowledgeBaseManager: "
                "non posso leggere BaseConfig."
            )
        return self._config_loader(base_name)

    def _get_embedder(self, model_name: str) -> EmbeddingStrategy:
        if model_name in self._embedder_cache:
            return self._embedder_cache[model_name]
        emb = self._embedder_factory(model_name)
        self._embedder_cache[model_name] = emb
        return emb

    # ..................................................................... #
    # Path helpers (chroma + chunk su disco)
    # ..................................................................... #

    def _chroma_client(self):
        from chromadb import PersistentClient

        path = self._chroma_path or self._default_chroma_path()
        path.mkdir(parents=True, exist_ok=True)
        return PersistentClient(path=str(path))

    def _default_chroma_path(self) -> Path:
        return Path(self._workspace.path) / self._dot / "chroma"

    def _base_dot_dir(self, base_name: str) -> Path:
        return Path(self._workspace.path) / base_name / self._dot

    def _chunks_dir(self, base_name: str, file_id: str) -> Path:
        return self._base_dot_dir(base_name) / "chunks" / file_id

    def _documents_dir(self, base_name: str) -> Path:
        """Cartella dei Markdown salvati dopo l'ingestione (feat-007)."""
        return self._base_dot_dir(base_name) / "documents"

    def _doc_path(self, base_name: str, file_id: str) -> Path:
        return self._documents_dir(base_name) / f"{file_id}.md"

    def _chunk_path(self, base_name: str, file_id: str, index: int) -> Path:
        return self._chunks_dir(base_name, file_id) / f"{file_id}_chunk_{index}.md"

    # ...................................................................... #
    # Conversione langchain → Chroma nativo
    # ...................................................................... #
    #
    # Per mantenere il blockrate di test basso, accediamo alla collection
    # nativa di ChromaDB (``client.get_or_create_collection``) anziché alla
    # wrapper langchain: così il manager controlla direttamente metadata e
    # IDs in upsert/delete.

    def _collection_name(self, base_name: str) -> str:
        """Nome collection Chroma valido per la base.

        Chroma richiede 3–512 caratteri in ``[a-zA-Z0-9._-]``, con inizio e
        fine alfanumerici. I nomi base con spazi (es. ``Paper Accademici``)
        non sono ammessi grezzi: vengono slugificati e disambiguati con un
        hash corto del nome originale. I nomi già validi restano
        ``ks_<base_name>`` (retrocompatibilità con le collection esistenti).
        """
        return chroma_collection_name(base_name)

    def _get_collection(self, base_name: str, dim: int):
        client = self._chroma_client()
        metadata = {"hnsw:space": "cosine"}
        return client.get_or_create_collection(
            name=self._collection_name(base_name),
            metadata=metadata,
        )

    def _collection_count(self, base_name: str) -> int:
        try:
            client = self._chroma_client()
            col = client.get_collection(name=self._collection_name(base_name))
            return col.count()
        except Exception:
            return 0

    def _collection_non_empty(self, base_name: str) -> bool:
        return self._collection_count(base_name) > 0

    def rename_chroma_collection(
        self,
        old_base_name: str,
        new_base_name: str,
        *,
        drop_old: bool = True,
    ) -> int:
        """Rinomina la collection Chroma di una base riscrivendo i chunk_id.

        Usato quando una base viene spostata/copiata dentro il workspace
        (bug 020): gli embedding esistenti vengono riusati, solo id e
        metadata vengono riscritti col nuovo ``base_name``. Nessun
        ricalcolo di embedding.

        Args:
            old_base_name: nome della base sorgente.
            new_base_name: nuovo nome della base.
            drop_old: se ``True`` elimina la collection sorgente (caso
                move/rename); se ``False`` la lascia intatta (caso copia).

        Returns:
            Numero di chunk migrati (0 se la collection non esiste).
        """
        client = self._chroma_client()
        old_name = self._collection_name(old_base_name)
        new_name = self._collection_name(new_base_name)
        if old_name == new_name:
            return 0

        try:
            col_old = client.get_collection(old_name)
        except Exception:
            logger.info("Collection %s non trovata, nessun rename", old_name)
            return 0

        data = col_old.get(include=["documents", "embeddings", "metadatas"])
        ids = data.get("ids") or []
        if not ids:
            if drop_old:
                try:
                    client.delete_collection(old_name)
                except Exception:
                    pass
            return 0

        new_ids: List[str] = []
        new_metas: List[Dict[str, Any]] = []
        for rec_id, meta in zip(ids, data.get("metadatas") or []):
            meta = dict(meta or {})
            parts = str(rec_id).rsplit("::", 2)
            if len(parts) == 3:
                file_id, index = parts[1], parts[2]
            else:
                file_id = str(meta.get("file_id", ""))
                index = str(meta.get("chunk_index", ""))
            new_ids.append(f"{new_base_name}::{file_id}::{index}")
            meta["chunk_id"] = new_ids[-1]
            meta["base_name"] = new_base_name
            new_metas.append(meta)

        if drop_old:
            client.delete_collection(old_name)
        col_new = client.get_or_create_collection(
            name=new_name,
            metadata={"hnsw:space": "cosine"},
        )
        kwargs: Dict[str, Any] = {
            "ids": new_ids,
            "metadatas": new_metas,
        }
        documents = data.get("documents")
        if documents is not None:
            kwargs["documents"] = documents
        embeddings = data.get("embeddings")
        if embeddings is not None:
            kwargs["embeddings"] = embeddings
        col_new.upsert(**kwargs)
        logger.info(
            "Collection %s → %s: %d chunk migrati",
            old_name, new_name, len(new_ids),
        )
        return len(new_ids)

    def copy_chroma_collection_from(
        self,
        other_workspace: Path,
        other_base_name: str,
        new_base_name: str,
    ) -> int:
        """Copia la collection Chroma di una base da un altro workspace.

        Bug 020 (copia tra workspace): quando una base viene copiata con
        ``cp -r`` da un workspace a un altro, i chunk su disco arrivano
        con la copia ma modello e Chroma restano nel workspace sorgente.
        Questo metodo riusa gli embedding esistenti: legge la collection
        dal client Chroma del workspace sorgente e la riscrive nel client
        del workspace corrente (chunk_id e metadata col nuovo
        ``base_name`` se diverso). Il workspace target è nuovo → nessun
        drop della sorgente.

        Args:
            other_workspace: path del workspace sorgente.
            other_base_name: nome della base nel workspace sorgente.
            new_base_name: nome della base nel workspace corrente.

        Returns:
            Numero di chunk copiati (0 se il Chroma sorgente non esiste
            o la collection non c'è).
        """
        from chromadb import PersistentClient

        src_path = Path(other_workspace) / self._dot / "chroma"
        if not src_path.is_dir():
            logger.info(
                "Chroma sorgente non trovato: %s", src_path
            )
            return 0

        src_name = chroma_collection_name(other_base_name)
        client_src = PersistentClient(path=str(src_path))
        try:
            col_src = client_src.get_collection(src_name)
        except Exception:
            logger.info(
                "Collection %s non trovata in %s, nessuna copia",
                src_name, src_path,
            )
            return 0

        data = col_src.get(include=["documents", "embeddings", "metadatas"])
        ids = data.get("ids") or []
        if not ids:
            return 0

        new_ids: List[str] = []
        new_metas: List[Dict[str, Any]] = []
        for rec_id, meta in zip(ids, data.get("metadatas") or []):
            meta = dict(meta or {})
            parts = str(rec_id).rsplit("::", 2)
            if len(parts) == 3:
                file_id, index = parts[1], parts[2]
            else:
                file_id = str(meta.get("file_id", ""))
                index = str(meta.get("chunk_index", ""))
            new_ids.append(f"{new_base_name}::{file_id}::{index}")
            meta["chunk_id"] = new_ids[-1]
            meta["base_name"] = new_base_name
            new_metas.append(meta)

        client_dst = self._chroma_client()
        col_dst = client_dst.get_or_create_collection(
            name=chroma_collection_name(new_base_name),
            metadata={"hnsw:space": "cosine"},
        )
        kwargs: Dict[str, Any] = {
            "ids": new_ids,
            "metadatas": new_metas,
        }
        documents = data.get("documents")
        if documents is not None:
            kwargs["documents"] = documents
        embeddings = data.get("embeddings")
        if embeddings is not None:
            kwargs["embeddings"] = embeddings
        col_dst.upsert(**kwargs)
        logger.info(
            "Collection %s copiata da %s: %d chunk migrati",
            src_name, src_path, len(new_ids),
        )
        return len(new_ids)

    # ..................................................................... #
    # CRUD base
    # ..................................................................... #

    def add(self, base_path: Path) -> KnowledgeBase:
        """Registra una nuova base (cartella). Restituisce il modello.

        Solleva :class:`ValueError` se la cartella non esiste o la base è
        già registrata."""
        p = Path(base_path)
        logger.info("Aggiunta base: %s", p)
        if not p.is_dir():
            raise ValueError(f"La cartella base non esiste: {p}")
        name = p.name
        if name in self._workspace.bases:
            raise ValueError(f"Base '{name}' già registrata")
        kb = KnowledgeBase(path=p)
        self._workspace.bases[name] = kb
        self._save()
        logger.info("Base aggiunta: %s", name)
        return kb

    def remove(self, base_name: str) -> bool:
        """Rimuove una base dal workspace, cancella collection Chroma e chunk su disco.

        Restituisce ``True`` se era presente.
        """
        logger.info("Rimozione base: %s", base_name)
        if base_name not in self._workspace.bases:
            logger.warning("Base non trovata: %s", base_name)
            return False
        # Drop collection Chroma (no-op se non è mai stata creata / già assente).
        try:
            client = self._chroma_client()
            client.delete_collection(name=self._collection_name(base_name))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "does not exist" in msg or "not found" in msg:
                logger.debug(
                    "Collection Chroma assente per %s (ok): %s", base_name, exc
                )
            else:
                logger.warning("Delete collection %s fallito: %s", base_name, exc)
        # Elimina chunk su disco per tutti i file della base
        kb = self._workspace.bases[base_name]
        for file_entry in kb.files.values():
            if file_entry.file_id:
                chunks_dir = self._chunks_dir(base_name, file_entry.file_id)
                if chunks_dir.exists():
                    shutil.rmtree(chunks_dir)
        # Rimuovi la dotfolder della base se vuota
        try:
            shutil.rmtree(self._base_dot_dir(base_name))
        except Exception:
            pass
        del self._workspace.bases[base_name]
        self._save()
        logger.info("Base rimossa: %s", base_name)
        return True

    # ..................................................................... #
    # Blocco cambio config (trigger 3/4/5)
    # ..................................................................... #

    def check_config_change(
        self, base_name: str, *, config: Optional[BaseConfig] = None
    ) -> None:
        """Verifica il blocco cambio config all'avvio.

        Confronta ``BaseConfig`` caricata con i valori registrati
        ``embedding_model``/``chunking_method``/``ingestion_library`` se la
        collection Chroma della base non è vuota. Solleva
        :class:`ConfigChangeBlockedError` se il cambio richiede reindex
        esplicito.

        Args:
            base_name: nome della base.
            config: configurazione già caricata. Se ``None``, viene caricata
                dal config_loader (retro-compatibilità).
        """
        kb = self._load_base_by_name(base_name)
        if config is None:
            config = self._load_base_config(base_name)
        check_config_change_blocked(
            base_name,
            config,
            registered_embedding_model=kb.embedding_model,
            registered_chunking_method=kb.chunking_method,
            registered_ingestion_library=kb.ingestion_library,
            collection_non_empty=self._collection_non_empty(base_name),
        )

    # ..................................................................... #
    # Pipeline principale: add_file
    # ..................................................................... #

    def add_file(
        self,
        base_name: str,
        source_path: Path,
        *,
        markdown_mode: str = "auto",
    ) -> FileEntry:
        """Esegue la pipeline completa su un file: ingestion → chunking →
        embedding → upsert Chroma. Persiste chunk su disco e stato su
        ``config.json``.

        Idempotente: se il file è già indicizzato con stesso ``content_hash``
        → no-op (restituisce il ``FileEntry`` esistente). Se il contenuto è
        cambiato, esegue il diff incrementale (trigger 1, approccio B).

        Genera ``file_id`` alla prima indicizzazione (UUID4, stabile).

        Il Markdown prodotto dalla conversione (feat-007) viene salvato in
        ``.knowledge-space/documents/{file_id}.md`` e riusato nei reindex che
        non richiedono riconversione. La fonte del Markdown dipende da
        ``markdown_mode``:

        - ``"auto"`` (default): usa il Markdown salvato se il sorgente è
          invariato (stesso ``mtime``), altrimenti riconverte con docling.
        - ``"reuse"`` (``--chunking-change`` / ``--model-change``): rilegge
          il Markdown salvato senza riconvertire (fallback: riconversione se
          il file non ha ancora un ``doc_path``).
        - ``"reconvert"`` (``--ingestion-change``): riconverte sempre il
          sorgente.

        Solleva :class:`ChunkPersistError` (wrap
        :class:`ChunkTooLongError`) se un chunk eccede il ``max_context_tokens``
        del modello di embedding.
        """
        if markdown_mode not in ("auto", "reuse", "reconvert"):
            raise ValueError(f"markdown_mode non valido: {markdown_mode}")
        kb = self._load_base_by_name(base_name)
        src = Path(source_path)
        logger.info(
            "Pipeline ingestion per file %s nella base %s (markdown_mode=%s)",
            src.name, base_name, markdown_mode,
        )
        if not src.is_file():
            raise FileNotFoundError(f"File sorgente non trovato: {src}")

        config = self._load_base_config(base_name)
        # Blocco cambio config (trigger 3/4/5) — controlla prima di operare.
        self.check_config_change(base_name, config=config)

        key = src.name
        existing = kb.files.get(key)

        # 1. Ingestion: Markdown da docling o dal documento salvato (feat-007).
        saved_md = self._load_saved_markdown(kb, existing, src, markdown_mode)
        if saved_md is not None:
            markdown, md_reused = saved_md, True
        else:
            ingestion = self._select_ingestion(config, src)
            markdown = ingestion.convert(src)
            md_reused = False
        new_md_hash = _sha256(markdown)

        # Short-circuit: file già indicizzato e contenuto invariato → no-op.
        # Feat-007: se la base è pre-feature (doc_path mancante), salva il
        # Markdown retroattivamente per i prossimi reindex.
        if existing is not None and existing.content_hash == new_md_hash:
            if not existing.doc_path:
                file_id = existing.file_id or uuid.uuid4().hex
                self._save_markdown(base_name, file_id, markdown)
                existing.file_id = file_id
                existing.doc_path = f".knowledge-space/documents/{file_id}.md"
                self._save()
            return existing

        # 2. Chunking (embedder serve solo per strategie semantic)
        embedder = self._get_embedder(config.embedding.model)
        chunker = self._chunking_factory(config, embedder)
        raw_chunks = chunker.split(markdown)
        new_chunk_hashes = [_sha256(c["text"]) for c in raw_chunks]

        # 3. Validazione lunghezza chunk (Step 7 bullet + embedding.validate)
        for i, c in enumerate(raw_chunks):
            try:
                validate_chunk_context(
                    c["text"],
                    embedder.metadata.max_context_tokens,
                    base_name=base_name,
                    file_name=src.name,
                    chunk_index=i,
                )
            except ChunkTooLongError as exc:
                raise ChunkPersistError(str(exc)) from exc

        # 4. Determina file_id: nuovo se è prima indicizzazione.
        if existing is not None and existing.file_id:
            file_id = existing.file_id
        else:
            file_id = uuid.uuid4().hex

        # 4-bis. Salva il Markdown prodotto (feat-007), se non riusato.
        if not md_reused:
            self._save_markdown(base_name, file_id, markdown)

        # 5. Persistenza chunk su disco + Chroma upsert (diff incrementale)
        self._persist_chunks(base_name, file_id, src.name, raw_chunks, new_chunk_hashes, existing, config=config)

        # 6. Update modello FileEntry
        if existing is None:
            existing = FileEntry(
                mtime=src.stat().st_mtime,
                added=_now_iso(),
                file_id=file_id,
                name=src.name,
                content_hash=new_md_hash,
                doc_path=f".knowledge-space/documents/{file_id}.md",
                active=True,
                chunks=[
                    ChunkRef(index=i, active=True, content_hash=new_chunk_hashes[i])
                    for i in range(len(raw_chunks))
                ],
            )
            kb.files[key] = existing
        else:
            existing.mtime = src.stat().st_mtime
            existing.file_id = file_id
            existing.name = src.name
            existing.content_hash = new_md_hash
            existing.doc_path = f".knowledge-space/documents/{file_id}.md"
            existing.chunks = [
                ChunkRef(index=i, active=True, content_hash=new_chunk_hashes[i])
                for i in range(len(raw_chunks))
            ]

        # 7. Registrazione config attiva nella base (per il blocco cambio config).
        kb.embedding_model = config.embedding.model
        kb.chunking_method = config.chunking.method
        kb.ingestion_library = config.ingestion.library

        self._save()
        logger.info("File %s indicizzato: %d chunk", src.name, len(existing.chunks))
        return existing

    def _load_saved_markdown(
        self,
        kb: KnowledgeBase,
        existing: Optional[FileEntry],
        src: Path,
        markdown_mode: str,
    ) -> Optional[str]:
        """Restituisce il Markdown salvato (feat-007) se riusabile, altrimenti
        ``None`` (il chiamante riconverte).

        ``"auto"``: riusa solo se il sorgente è invariato (stesso ``mtime``)
        e l'hash del documento salvato coincide con ``content_hash``.
        ``"reuse"``: riusa senza controllare il ``mtime`` (reindex
        ``--chunking-change`` / ``--model-change``).
        ``"reconvert"``: non riusa mai.
        """
        if markdown_mode == "reconvert":
            return None
        if existing is None or not existing.doc_path or not existing.content_hash:
            return None
        if markdown_mode == "auto" and src.stat().st_mtime != existing.mtime:
            return None
        doc = kb.path / existing.doc_path
        if not doc.is_file():
            return None
        try:
            markdown = doc.read_text(encoding="utf-8")
        except OSError:
            return None
        if _sha256(markdown) != existing.content_hash:
            # Documento salvato manomesso/corrotto → riconverti.
            return None
        logger.info("Markdown riusato da %s (senza riconversione)", doc)
        return markdown

    def _save_markdown(self, base_name: str, file_id: str, markdown: str) -> Path:
        """Salva il Markdown prodotto dall'ingestione (feat-007)."""
        doc_dir = self._documents_dir(base_name)
        doc_dir.mkdir(parents=True, exist_ok=True)
        doc = self._doc_path(base_name, file_id)
        doc.write_text(markdown, encoding="utf-8")
        logger.info("Markdown salvato: %s", doc)
        return doc

    # ..................................................................... #
    # Persistenza chunk su disco + Chroma upsert diff
    # ..................................................................... #

    def _persist_chunks(
        self,
        base_name: str,
        file_id: str,
        file_name: str,
        new_chunks: List[Dict[str, Any]],
        new_hashes: List[str],
        existing: Optional[FileEntry],
        *,
        config: BaseConfig,
    ) -> None:
        """Scrive i chunk su disco, fa upsert Chroma (solo cambiati) e
        cancella chunk/record Chroma scomparsi.

        Implementa il **diff incrementale** (trigger 1): un chunk è
        ri-embeddato/upsertato solo se il ``content_hash`` differisce da
        quello registrato per lo stesso indice. Approscc B per insert in
        mezzo (shift accettato).
        """
        # Mappa indice→content_hash dei vecchi chunk (se presenti).
        old_hashes: Dict[int, str] = {}
        if existing is not None:
            for c in existing.chunks:
                if c.content_hash is not None:
                    old_hashes[c.index] = c.content_hash

        # Prepara testi + ids + metadati per Chroma.
        texts_to_upsert: List[str] = []
        ids_to_upsert: List[str] = []
        metas_to_upsert: List[Dict[str, Any]] = []
        # Embedding via embedder (richiede lo stesso vector space del modello
        # registrato — l'embedder cache garantisce consistenza intra-run).
        embedder = self._get_embedder(config.embedding.model)
        col = self._get_collection(base_name, dim=embedder.metadata.dim)

        new_count = len(new_chunks)
        old_max_index = max(old_hashes) if old_hashes else -1

        # 1. Upsert dei chunk nuovi/cambiati
        for i, chunk in enumerate(new_chunks):
            new_hash = new_hashes[i]
            old_hash = old_hashes.get(i)

            # Scrive su disco solo se cambiato (o nuovo).
            chunk_path = self._chunk_path(base_name, file_id, i)
            if old_hash != new_hash:
                chunk_path.parent.mkdir(parents=True, exist_ok=True)
                chunk_path.write_text(chunk["text"], encoding="utf-8")

                chunk_id = f"{base_name}::{file_id}::{i}"
                metadata = {
                    "chunk_id": chunk_id,
                    "base_name": base_name,
                    "file_name": file_name,
                    "file_id": file_id,
                    "chunk_index": i,
                    "content_hash": new_hash,
                }
                texts_to_upsert.append(chunk["text"])
                ids_to_upsert.append(chunk_id)
                metas_to_upsert.append(metadata)

        # Embedding + upsert Chroma batch (se ci sono chunk cambiati).
        if texts_to_upsert:
            vectors = embedder.embed(texts_to_upsert)
            col.upsert(
                ids=ids_to_upsert,
                embeddings=vectors,
                documents=texts_to_upsert,
                metadatas=metas_to_upsert,
            )

        # 2. Cancella chunk oltre la nuova lunghezza (file accorciato)
        if old_max_index >= new_count:
            ids_to_delete = [
                f"{base_name}::{file_id}::{i}"
                for i in range(new_count, old_max_index + 1)
            ]
            try:
                col.delete(ids=ids_to_delete)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Delete chunk %s fallito: %s", ids_to_delete, exc)
            for i in range(new_count, old_max_index + 1):
                p = self._chunk_path(base_name, file_id, i)
                if p.exists():
                    p.unlink()

    # ..................................................................... #
    # Remove file
    # ..................................................................... #

    def remove_file(self, base_name: str, source_name: str) -> bool:
        """Rimuove un file dalla base: cancella chunk da disco e i suoi
        record Chroma. Restituisce ``True`` se era presente.
        """
        logger.info("Rimozione file %s dalla base %s", source_name, base_name)
        kb = self._load_base_by_name(base_name)
        if source_name not in kb.files:
            logger.warning("File non trovato: %s", source_name)
            return False
        entry = kb.files[source_name]
        file_id = entry.file_id
        if file_id:
            # Cancella record Chroma
            try:
                col = self._chroma_client().get_collection(
                    name=self._collection_name(base_name)
                )
                ids = [f"{base_name}::{file_id}::{i}" for i in range(len(entry.chunks))]
                if ids:
                    col.delete(ids=ids)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Delete Chroma records fallito: %s", exc)
            # Cancella cartella chunk
            chunks_dir = self._chunks_dir(base_name, file_id)
            if chunks_dir.exists():
                for p in chunks_dir.iterdir():
                    p.unlink()
                chunks_dir.rmdir()
            # Cancella documento Markdown salvato (feat-007)
            doc = kb.path / entry.doc_path if entry.doc_path else self._doc_path(base_name, file_id)
            if doc.is_file():
                doc.unlink()
        del kb.files[source_name]
        self._save()
        logger.info("File rimosso: %s", source_name)
        return True

    # ..................................................................... #
    # Sync (mtime check)
    # ..................................................................... #

    def sync(self, base_name: str) -> KnowledgeBase:
        """Allinea una base col filesystem:

        - Aggiunge (in ``pending``) i file nuovi registrandone il path
          (l'effettiva indicizzazione avviene con :meth:`add_file`).
        - Rimuove i file la cui origine su disco è scomparsa.
        - Rileva file modificati (mtime cambiato) e li marca per re-index.

        Per la Fase 1A questo sync opera solo a livello ``mtime``/presenza:
        l'azione di re-ingest esplicita è delegata a ``add_file``
        (chiamato esplicitamente dalla CLI o dal watcher). La sync registra
        lo stato ma non attiva pipeline pesanti.
        """
        logger.info("Sync base: %s", base_name)
        kb = self._load_base_by_name(base_name)
        base_path = kb.path
        if not base_path.is_dir():
            return kb

        # 1. File nuovi
        seen: set[str] = set()
        for entry in base_path.iterdir():
            if not entry.is_file() or entry.name.startswith("."):
                continue
            seen.add(entry.name)
            if entry.name not in kb.files:
                # Nuovo file: lasciamo la registrazione all'add_file esplicito.
                # Qui ci limitiamo a loggare.
                logger.info("File nuovo scoperto in %s: %s", base_name, entry.name)
                continue
            # 2. File esistente: mtime check
            file_entry = kb.files[entry.name]
            try:
                current_mtime = entry.stat().st_mtime
            except OSError:
                continue
            if file_entry.mtime != current_mtime:
                logger.info(
                    "File modificato (mtime) in %s: %s — re-index suggerito",
                    base_name,
                    entry.name,
                )
                # Non attiviamo pipeline qui: l'utente/CLI chiamerà add_file.

        # 3. File scomparsi
        for name in list(kb.files):
            if name not in seen:
                # Cancella chunk + Chroma records
                self._remove_file_internal(kb, base_name, name)

        self._save()
        return kb

    def _remove_file_internal(
        self, kb: KnowledgeBase, base_name: str, source_name: str
    ) -> None:
        """Come :meth:`remove_file` ma opera in-place sul modello senza
        ``_save()`` — usato da :meth:`sync` per batch."""
        entry = kb.files.get(source_name)
        if entry is None:
            return
        file_id = entry.file_id
        if file_id:
            try:
                col = self._chroma_client().get_collection(
                    name=self._collection_name(base_name)
                )
                ids = [f"{base_name}::{file_id}::{i}" for i in range(len(entry.chunks))]
                if ids:
                    col.delete(ids=ids)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Delete Chroma records (sync) fallito: %s", exc)
            chunks_dir = self._chunks_dir(base_name, file_id)
            if chunks_dir.exists():
                for p in chunks_dir.iterdir():
                    p.unlink()
                chunks_dir.rmdir()
        del kb.files[source_name]

    # ..................................................................... #
    # Move / rename senza recompute (trigger 2)
    # ..................................................................... #

    def rename_file(
        self,
        base_name: str,
        old_name: str,
        new_path: Path,
    ) -> FileEntry:
        """Aggiorna path/nome di un file già indicizzato senza ricalcolare
        embedding (trigger 2 di ``docs/45-indexing-incrementale.md``).

        Aggiorna ``FileEntry.name`` nello stato e i metadati Chroma
        (``file_name``) dei chunk del file. ``chunk_id`` immutato (basato
        su ``file_id``). Zero re-embed.

        Solleva :class:`FileAlreadyIndexedError` se il nuovo nome coincide
        con un file già presente nella base (gestito come add separato).
        """
        kb = self._load_base_by_name(base_name)
        if old_name not in kb.files:
            raise FileNotFoundError(
                f"File '{old_name}' non indicizzato nella base '{base_name}'"
            )
        entry = kb.files[old_name]
        new_name = Path(new_path).name
        if new_name != old_name and new_name in kb.files:
            raise FileAlreadyIndexedError(
                f"Il nome target '{new_name}' è già indicizzato nella base"
            )

        # 1. Update metadati Chroma (file_name) — chunk_id immutato
        file_id = entry.file_id
        if file_id:
            try:
                col = self._chroma_client().get_collection(
                    name=self._collection_name(base_name)
                )
                ids = [f"{base_name}::{file_id}::{i}" for i in range(len(entry.chunks))]
                if ids:
                    col.update(
                        ids=ids,
                        metadatas=[{"file_name": new_name}] * len(ids),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Update metadata Chroma (rename) fallito: %s", exc)

        # 2. Update modello
        entry.name = new_name
        entry.mtime = Path(new_path).stat().st_mtime if Path(new_path).exists() else entry.mtime
        if new_name != old_name:
            del kb.files[old_name]
            kb.files[new_name] = entry
        self._save()
        return entry

    # ..................................................................... #
    # Migrazione retroattiva state.json
    # ..................................................................... #

    def migrate_state(self) -> None:
        """Migra un ``config.json`` legacy (pre-Step 7) al nuovo schema:
        - genera ``file_id`` mancanti (UUID4);
        - rigenera ``chunk_id`` registro (invarianti: basati su ``file_id``);
        - calcola ``content_hash`` per i file senza;
        - propaga ``embedding_model``/``chunking_method``/``ingestion_library``
          registrati (se mancanti, restano ``None``: la prima ``add_file``
          provvede a popolarli);
        - garantisce la sezione ``graph`` esiste (default placeholder).

        Idempotente: rieseguire non cambia i dati già migrati.
        """
        # Garantisce la sezione graph a livello workspace (placeholder)
        # (gestita dal WorkspaceConfig stesso in Fase 1C — qui ci limitiamo
        # ai campi base.)
        for kb in self._workspace.bases.values():
            for name, entry in kb.files.items():
                if not entry.file_id:
                    entry.file_id = uuid.uuid4().hex
                if not entry.name:
                    entry.name = name
                # content_hash: se manca e il chunk su disco è presente, lo
                # ricalcoliamo dal testo — altrimenti resta None (add_file lo
                # ricalcolerà).
                if entry.content_hash is None:
                    md = self._read_chunked_markdown(kb, entry.file_id, len(entry.chunks))
                    if md is not None:
                        entry.content_hash = _sha256(md)
                # ChunkRef: garantisce content_hash presente (se possibile).
                for c in entry.chunks:
                    if c.content_hash is None and entry.file_id:
                        chunk_p = self._chunk_path(
                            kb.path.name, entry.file_id, c.index
                        )
                        if chunk_p.exists():
                            c.content_hash = _sha256(chunk_p.read_text(encoding="utf-8"))
        self._save()

    def _read_chunked_markdown(
        self, kb: KnowledgeBase, file_id: Optional[str], n_chunks: int
    ) -> Optional[str]:
        """Ricostruisce il markdown originale concatenando i chunk su
        disco (per la migrazione ``content_hash`` a livello file)."""
        if not file_id or n_chunks == 0:
            return None
        base_name = kb.path.name
        parts: List[str] = []
        for i in range(n_chunks):
            p = self._chunk_path(base_name, file_id, i)
            if not p.exists():
                return None
            parts.append(p.read_text(encoding="utf-8"))
        return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")