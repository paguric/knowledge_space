"""Comando search.

``ks search <query>`` — ricerca vettoriale
``ks search <query> --base <name>`` — filtra per base
``ks search <query> --top-k N`` — override risultati
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import typer

logger = logging.getLogger(__name__)

from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    output_json,
    resolve_base_name,
)


# --------------------------------------------------------------------------- #
# Helpers per il filtro active
# --------------------------------------------------------------------------- #


def _in_active_domain(base_name: str, domains: List[Any]) -> bool:
    """``True`` se la base appartiene ad almeno un dominio attivo,
    oppure se non ci sono domini (tutte le basi sono considerate attive)."""
    if not domains:
        return True
    for d in domains:
        if d.active and base_name in d.base_names:
            return True
    return False


def _chunk_is_active(chunk_id: str, base_name: str, kb: Any) -> bool:
    """``True`` se il chunk e il suo file sono entrambi attivi.

    Parsa ``chunk_id`` (formato ``"{base_name}::{file_id}::{i}"``) per
    risalire a :class:`FileEntry` e :class:`ChunkRef`."""
    # Estrai file_id e indice dal chunk_id
    parts = chunk_id.rsplit("::", 2)
    if len(parts) != 3:
        return False
    _, file_id_str, index_str = parts
    try:
        idx = int(index_str)
    except ValueError:
        return False

    # Cerca FileEntry per file_id (le chiavi di kb.files sono filename, non file_id)
    file_entry = None
    for fe in kb.files.values():
        if fe.file_id == file_id_str:
            file_entry = fe
            break
    if file_entry is None or not file_entry.active:
        return False

    # Controlla ChunkRef
    if idx >= len(file_entry.chunks):
        return False
    return file_entry.chunks[idx].active


# --------------------------------------------------------------------------- #
# Comando
# --------------------------------------------------------------------------- #


def search_command(
    query: str = typer.Argument(help="Query di ricerca."),
    base_name: Optional[str] = typer.Option(None, "--base", "-b", help="Filtra per base."),
    top_k: int = typer.Option(10, "--top-k", "-k", help="Numero massimo di risultati."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Esegue una ricerca vettoriale sulle basi del workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Ricerca: query='%s', base=%s, top_k=%d", query, base_name, top_k)

    # Verifica che esistano basi
    if not ws.bases:
        logger.warning("Nessuna base nel workspace per la ricerca")
        typer.echo("Nessuna base nel workspace. Aggiungi una base prima di cercare.", err=True)
        raise typer.Exit(1)

    # Costruisci la collection factory
    bases_to_search = {}
    if base_name:
        base_name = resolve_base_name(base_name, workspace=ws)
        if base_name not in ws.bases:
            typer.echo(f"Base non trovata: {base_name}", err=True)
            raise typer.Exit(1)
        bases_to_search[base_name] = ws.bases[base_name]
    else:
        bases_to_search = ws.bases

    # Raccogli tutti i risultati da tutte le basi
    all_results = []

    for bname, kb in bases_to_search.items():
        # --- Filtro pre-retrieval: basi e domini non attivi ---
        if not kb.active:
            logger.debug("Base '%s' disattivata, salto", bname)
            continue
        if not _in_active_domain(bname, ws.domains):
            logger.debug("Base '%s' non in un dominio attivo, salto", bname)
            continue
        # --- Fine filtro pre-retrieval ---
        if not kb.files:
            continue

        # Carica config per ottenere il modello embedding
        try:
            config_loader = ctx.base_config_loader_factory(ws.path)
            config = config_loader.load(bname)
            model_name = config.embedding.model
        except Exception:
            model_name = "sentence-transformers/all-mpnet-base-v2"

        # Crea embedder e collection
        try:
            embedder = ctx.embedder_factory(model_name)
        except Exception as exc:
            typer.echo(f"Warning: embedder non disponibile per {bname}: {exc}", err=True)
            continue

        # Accedi alla collection Chroma
        try:
            from chromadb import PersistentClient

            chroma_path = ws.path / ctx.runtime_paths.dot_folder_name / "chroma"
            if not chroma_path.exists():
                continue
            client = PersistentClient(path=str(chroma_path))
            collection = client.get_collection(name=f"ks_{bname}")
        except Exception:
            continue

        # Esegui ricerca
        try:
            query_vector = embedder.embed([query])[0]
            results = collection.query(
                query_embeddings=[query_vector],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )

            if results and results["ids"] and results["ids"][0]:
                for i, chunk_id in enumerate(results["ids"][0]):
                    document = results["documents"][0][i] if results["documents"] else ""
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 0.0
                    score = 1.0 - distance

                    # --- Filtro post-retrieval: chunk/file non attivi ---
                    if not _chunk_is_active(chunk_id, bname, kb):
                        logger.debug("Chunk '%s' disattivato, salto", chunk_id)
                        continue
                    # --- Fine filtro post-retrieval ---

                    all_results.append({
                        "chunk_id": chunk_id,
                        "base": bname,
                        "file_name": metadata.get("file_name", ""),
                        "score": round(score, 4),
                        "text": document[:200] if document else "",
                    })
        except Exception as exc:
            logger.error("Ricerca fallita per base %s: %s", bname, exc)
            typer.echo(f"Warning: ricerca fallita per {bname}: {exc}", err=True)

    # Ordina per score e limita
    all_results.sort(key=lambda r: r["score"], reverse=True)
    all_results = all_results[:top_k]
    logger.info("Ricerca completata: %d risultati", len(all_results))

    if json_output:
        output_json(all_results)
    else:
        if not all_results:
            typer.echo("Nessun risultato trovato.")
            return
        typer.echo(f"Trovati {len(all_results)} risultati:\n")
        for i, r in enumerate(all_results, 1):
            typer.echo(f"{i}. [{r['base']}] {r['file_name']} (score={r['score']})")
            typer.echo(f"   {r['chunk_id']}")
            if r["text"]:
                typer.echo(f"   {r['text']}...")
            typer.echo()
