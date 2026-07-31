"""Comando search.

``ks search <query>`` — ricerca vettoriale su tutte le basi attive
``ks search <query> --json`` — output JSON
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import typer

logger = logging.getLogger(__name__)

from knowledge_base.knowledge_base_manager import chroma_collection_name
from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    output_json,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _in_active_domain(base_name: str, domains: List[Any]) -> bool:
    """``True`` se la base appartiene ad almeno un dominio attivo,
    oppure se non ci sono domini (tutte le basi sono considerate attive)."""
    if not domains:
        return True
    for d in domains:
        if base_name in d.base_names:
            return d.active        # base in un dominio → dipende se attivo
    return True                    # base non in nessun dominio → sempre ok


# --------------------------------------------------------------------------- #
# Comando
# --------------------------------------------------------------------------- #


def search_command(
    query: str = typer.Argument(help="Query di ricerca."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
) -> None:
    """Esegue una ricerca vettoriale sulle basi del workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Ricerca: query='%s'", query)

    if not ws.bases:
        logger.warning("Nessuna base nel workspace per la ricerca")
        typer.echo("Nessuna base nel workspace. Aggiungi una base prima di cercare.", err=True)
        raise typer.Exit(1)

    config_loader = ctx.base_config_loader_factory(ws.path)
    chroma_path = ws.path / ctx.runtime_paths.dot_folder_name / "chroma"

    # Unico client Chroma condiviso tra tutte le basi
    chroma_client = None
    if chroma_path.exists():
        from chromadb import PersistentClient

        chroma_client = PersistentClient(path=str(chroma_path))
        logger.info("Chroma path: %s", chroma_path)
    else:
        logger.warning("Directory Chroma non trovata: %s", chroma_path)

    all_results: list[dict] = []

    for bname, kb in ws.bases.items():
        # --- Filtro pre-retrieval ---
        if not kb.active:
            logger.debug("Base '%s' disattivata, salto", bname)
            continue
        if not _in_active_domain(bname, ws.domains):
            logger.debug("Base '%s' non in un dominio attivo, salto", bname)
            continue

        if not kb.files or chroma_client is None:
            continue

        # Carica config TOML
        try:
            base_config = config_loader.load(bname)
        except Exception as exc:
            logger.warning("Config non caricabile per %s: %s", bname, exc)
            continue

        # Verifica che la collection esista
        collection_name = chroma_collection_name(bname)
        try:
            collection = chroma_client.get_collection(name=collection_name)
        except Exception:
            logger.info("Collection '%s' non trovata per base '%s', salto", collection_name, bname)
            continue

        logger.info("Ricerca in base '%s' (collection=%s)...", bname, collection_name)

        # Costruisci SearchService con collection factory per questa base
        from knowledge_base.search_service import SearchService

        service = SearchService(
            llm_factory=ctx.llm_factory,
            embedder_factory=ctx.embedder_factory,
            collection_factory=lambda cn=collection_name: chroma_client.get_collection(name=cn),
        )

        try:
            results = service.search(
                query, config=base_config.to_search_config(), kb=kb
            )
        except Exception as exc:
            logger.error("Ricerca fallita per base %s: %s", bname, exc)
            typer.echo(f"Warning: ricerca fallita per {bname}: {exc}", err=True)
            continue

        for r in results:
            all_results.append({
                "chunk_id": r.chunk_id,
                "base": bname,
                "file_name": r.metadata.get("file_name", ""),
                "score": round(r.score, 4),
                "text": r.text[:200] if r.text else "",
            })

    all_results.sort(key=lambda r: r["score"], reverse=True)
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
